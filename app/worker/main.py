"""Download worker (arq). Run as many replicas as you like:

    arq app.worker.main.WorkerSettings

Concurrency: each process runs up to WORKER_MAX_JOBS jobs, and a Redis semaphore
caps simultaneous yt-dlp/ffmpeg runs to DOWNLOAD_CONCURRENCY across all replicas.
"""
import asyncio
import logging
import shutil
import time
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramEntityTooLarge
from arq import cron, func
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app import db, state
from app.config import Settings, get_settings
from app.errors import JobError, classify, user_message
from app.formats import PRESETS
from app.media import cached_from_message, send_cached, send_media
from app.telegram import make_bot
from app.worker.download import download

log = logging.getLogger(__name__)
_background: set[asyncio.Task] = set()


async def edit_status(bot: Bot, chat_id: int, message_id: int | None, text: str) -> None:
    if not message_id:
        return
    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id,
                                    disable_web_page_preview=True)
    except TelegramBadRequest:
        pass  # "message is not modified" / deleted by user


async def delete_status(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass  # already deleted


def _mb(n: float) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def render_progress(label: str, p: dict) -> str:
    if p.get("stage") == "processing":
        return f"⚙️ Processing ({label})…"
    done, total, speed = p.get("done", 0), p.get("total", 0), p.get("speed", 0)
    text = f"⬇️ Downloading ({label})…"
    if total:
        text += f" {done / total:.0%} ({_mb(done)} / {_mb(total)})"
    elif done:
        text += f" {_mb(done)}"
    if speed:
        text += f" · {_mb(speed)}/s"
    return text


async def progress_loop(bot: Bot, chat_id: int, message_id: int, label: str,
                        progress: dict, interval: float) -> None:
    last = None
    while True:
        await asyncio.sleep(interval)  # at most one edit per interval
        text = render_progress(label, progress)
        if text != last:
            await edit_status(bot, chat_id, message_id, text)
            last = text


async def process_job(ctx: dict, job_id: str) -> str:
    s: Settings = ctx["settings"]
    pool, redis, bot = ctx["pool"], ctx["redis"], ctx["bot"]

    job = await db.get_job(pool, job_id)
    if job is None:
        return "missing"
    await state.unmark_waiting(redis, job_id)

    preset = PRESETS[job["format"]]
    chat_id, msg_id, key = job["chat_id"], job["status_message_id"], job["cache_key"]
    workdir = s.downloads_dir / job_id

    try:
        # Two users asking for the same url+format at once -> one download.
        async with state.inflight_lock(redis, key, timeout=s.job_timeout):
            cached = await db.get_cached(pool, key)
            if cached:
                await send_cached(bot, chat_id, cached, reply_to=job["reply_to_message_id"])
                await state.incr_stat(redis, "cache_hit_worker")
            else:
                await deliver_fresh(ctx, job, preset, workdir)
        await db.set_job_status(pool, job_id, "done")
        await delete_status(bot, chat_id, msg_id)  # the file itself is the result
        return "done"
    except Exception as e:  # noqa: BLE001 - every failure becomes a plain message
        code = classify(e)
        if code == "unknown":
            log.exception("job %s failed", job_id)
        else:
            log.info("job %s failed: %s (%s)", job_id, code, str(e)[:200])
        await state.incr_stat(redis, f"error:{code}")
        await db.set_job_status(pool, job_id, "failed", error_code=code)
        await edit_status(bot, chat_id, msg_id, user_message(code))
        if s.logger_channel_id:
            _spawn(log_error_to_channel(bot, s.logger_channel_id, job, code, e))
        return f"failed:{code}"
    finally:
        await state.release_user_slot(redis, job["user_id"], job_id)
        shutil.rmtree(workdir, ignore_errors=True)


async def deliver_fresh(ctx: dict, job, preset, workdir) -> None:
    s: Settings = ctx["settings"]
    pool, redis, bot = ctx["pool"], ctx["redis"], ctx["bot"]
    job_id, chat_id, msg_id = job["id"], job["chat_id"], job["status_message_id"]

    progress: dict = {}
    async with state.download_slot(redis, s.download_concurrency):
        await db.set_job_status(pool, job_id, "downloading")
        await edit_status(bot, chat_id, msg_id, f"⬇️ Downloading ({preset.label})…")
        ticker = asyncio.create_task(
            progress_loop(bot, chat_id, msg_id, preset.label, progress, s.progress_interval)
        )
        try:
            async with asyncio.timeout(s.job_timeout - 60):
                result = await asyncio.to_thread(download, job["url"], preset, workdir, s, progress)
        except TimeoutError:
            raise JobError("timeout") from None
        finally:
            ticker.cancel()

    await db.set_job_status(pool, job_id, "uploading", file_size=result.size)
    await edit_status(bot, chat_id, msg_id, f"📤 Uploading ({_mb(result.size)})…")
    try:
        # Local Bot API server reads the file straight from the shared volume.
        msg = await send_media(
            bot, chat_id, result.media_type, result.path.as_uri(),
            title=result.title, duration=result.duration,
            width=result.width, height=result.height,
            request_timeout=s.upload_timeout, reply_to=job["reply_to_message_id"],
        )
    except TelegramEntityTooLarge:
        raise JobError("too_big") from None
    except TelegramAPIError as e:
        log.warning("upload failed for %s: %s", job_id, e)
        raise JobError("upload_failed") from None

    cached = cached_from_message(msg, result.title)
    await db.store_cached(pool, job["cache_key"], job["normalized_url"], preset.code, cached)

    if s.logger_channel_id and not s.is_admin(job["user_id"]):
        _spawn(log_to_channel(bot, s.logger_channel_id, job, cached))


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _background.add(t)
    t.add_done_callback(_background.discard)


async def log_to_channel(bot: Bot, channel_id: int, job, cached) -> None:
    try:
        caption = (
            f"📥 <a href=\"tg://user?id={job['user_id']}\">{job['user_id']}</a> · {job['format']}\n"
            f"{escape(job['url'])}"
        )
        await send_media(bot, channel_id, cached.media_type, cached.file_id, caption=caption,
                         duration=cached.duration, width=cached.width, height=cached.height)
    except TelegramAPIError as e:
        log.warning("logger channel send failed: %s", e)


async def log_error_to_channel(bot: Bot, channel_id: int, job, code: str, exc: Exception) -> None:
    # JobError(...) from None hides the real cause in __context__; show that instead.
    cause = exc.__context__ if isinstance(exc, JobError) and exc.__context__ else exc
    detail = f"{type(cause).__name__}: {cause}"[:1500]
    text = (
        f"❌ <a href=\"tg://user?id={job['user_id']}\">{job['user_id']}</a> · {job['format']}"
        f" · <b>{code}</b>\n{escape(job['url'])}\n<pre>{escape(detail)}</pre>"
    )
    try:
        await bot.send_message(channel_id, text, disable_web_page_preview=True)
    except TelegramAPIError as e:
        log.warning("logger channel error send failed: %s", e)


async def cleanup_stale_files(ctx: dict) -> None:
    """Remove leftovers from crashed jobs."""
    root = ctx["settings"].downloads_dir
    cutoff = time.time() - 3 * 3600
    for d in root.iterdir() if root.exists() else ():
        if d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)


async def startup(ctx: dict) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = get_settings()
    s.downloads_dir.mkdir(parents=True, exist_ok=True)
    ctx["settings"] = s
    ctx["redis"] = Redis.from_url(s.redis_url, decode_responses=True)
    ctx["pool"] = await db.create_pool(s.database_url)
    ctx["bot"] = make_bot(s, ctx["redis"])


async def shutdown(ctx: dict) -> None:
    await ctx["bot"].session.close()
    await ctx["pool"].close()
    await ctx["redis"].aclose()


_s = get_settings()


class WorkerSettings:
    functions = [func(process_job, timeout=_s.job_timeout, max_tries=1)]
    cron_jobs = [cron(cleanup_stale_files, minute={0, 30})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_s.redis_url)
    max_jobs = _s.worker_max_jobs
    job_timeout = _s.job_timeout
    keep_result = 3600
