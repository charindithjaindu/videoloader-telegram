"""Update handlers. Rule: never await yt-dlp/ffmpeg/uploads here.

A handler does at most: parse, a Redis/Postgres lookup, one enqueue, one or two
small Bot API calls. Everything slow happens in the worker.
"""
import logging
import uuid

import asyncpg
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User
from arq import ArqRedis
from redis.asyncio import Redis

from app import db, state
from app.config import Settings
from app.formats import PRESETS, Preset, cache_key
from app.media import send_cached
from app.urls import detect_platform, extract_url, normalize_url

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

ASK = "ask"  # default_format value: show the format buttons for every link

START_TEXT = (
    "👋 Send me a link from YouTube, TikTok, Instagram, X/Twitter, Facebook, Reddit "
    "and many more sites.\n\n"
    "I'll download it in the best quality and send you the file. Files up to 2 GB.\n"
    "Use /settings to change the default quality or pick audio instead."
)


def _preset_text(code: str) -> str:
    if code == ASK:
        return "❓ Ask every time"
    p = PRESETS[code]
    return f"{'🎬' if p.kind == 'video' else '🎵'} {p.label}"


def formats_keyboard(token: str) -> InlineKeyboardMarkup:
    def btn(code: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=_preset_text(code), callback_data=f"dl:{token}:{code}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("v1080"), btn("v720"), btn("v480")],
        [btn("v360"), btn("vbest")],
        [btn("a_mp3"), btn("a_m4a")],
    ])


def settings_keyboard(current: str) -> InlineKeyboardMarkup:
    def btn(code: str) -> InlineKeyboardButton:
        mark = "✅ " if code == current else ""
        return InlineKeyboardButton(text=mark + _preset_text(code), callback_data=f"set:{code}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("vbest"), btn("v1080"), btn("v720")],
        [btn("v480"), btn("v360")],
        [btn("a_mp3"), btn("a_m4a")],
        [btn(ASK)],
    ])


def settings_text(current: str) -> str:
    return (
        "<b>⚙️ Settings</b>\n"
        f"Default format: {_preset_text(current)}\n\n"
        "Links you send are downloaded in this format. Choose another:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, pool: asyncpg.Pool) -> None:
    await db.upsert_user(pool, message.from_user)
    await message.answer(START_TEXT)


@router.message(Command("settings"))
async def cmd_settings(message: Message, pool: asyncpg.Pool) -> None:
    user = await db.upsert_user(pool, message.from_user)
    fmt = user["default_format"]
    await message.answer(settings_text(fmt), reply_markup=settings_keyboard(fmt))


@router.callback_query(F.data.startswith("set:"))
async def on_setting(cb: CallbackQuery, pool: asyncpg.Pool) -> None:
    code = cb.data.removeprefix("set:")
    if code != ASK and code not in PRESETS:
        await cb.answer("Unknown option", show_alert=True)
        return
    await db.upsert_user(pool, cb.from_user)
    await db.set_default_format(pool, cb.from_user.id, code)
    await cb.answer(f"Default: {_preset_text(code)}")
    try:
        await cb.message.edit_text(settings_text(code), reply_markup=settings_keyboard(code))
    except TelegramBadRequest:
        pass  # "message is not modified"


@router.message(Command("stats"))
async def cmd_stats(message: Message, pool: asyncpg.Pool, redis: Redis, settings: Settings) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    s = await db.stats(pool)
    counters = await state.get_stats(redis)
    hits, misses = counters.get("cache_hit", 0), counters.get("cache_miss", 0)
    ratio = f"{hits / (hits + misses):.0%}" if hits + misses else "n/a"
    lines = [
        "<b>📊 Stats</b>",
        f"Queue depth: {await state.queue_depth(redis)}",
        f"Active downloads: {await state.active_downloads(redis)} / {settings.download_concurrency}",
        f"Users: {s['users']}",
        f"Cached files: {s['cached_files']}",
        f"Cache hits / misses (all time): {hits} / {misses} ({ratio})",
        f"Jobs 24h: {s['jobs_24h']} " + ", ".join(f"{k}={v}" for k, v in s["by_status"].items()),
    ]
    if s["errors"]:
        lines.append("Errors 24h: " + ", ".join(f"{k}={v}" for k, v in s["errors"].items()))
    await message.answer("\n".join(lines))


@router.message(F.text | F.caption)
async def on_link(
    message: Message, pool: asyncpg.Pool, redis: Redis, arq: ArqRedis, settings: Settings
) -> None:
    url = extract_url(message.text or message.caption)
    if not url:
        await message.answer("Send me a link (http:// or https://).")
        return
    if not settings.is_admin(message.from_user.id) and await state.hit_flood_limit(
        redis, message.from_user.id, settings.links_per_minute
    ):
        await message.answer("⏳ Too many links. Wait a minute and try again.")
        return
    user = await db.upsert_user(pool, message.from_user)
    if user["is_banned"]:
        await message.answer("You are banned.")
        return

    platform = detect_platform(url)
    head = f"🔗 {platform.capitalize()} link" if platform else "🔗 Link"
    preset = PRESETS.get(user["default_format"])
    if preset is None:  # ASK
        token = await state.save_link(redis, url)
        await message.reply(f"{head}. Choose a format:", reply_markup=formats_keyboard(token),
                            disable_web_page_preview=True)
        return

    status = await message.reply(f"{head}. Starting ({preset.label})…",
                                 disable_web_page_preview=True)
    await start_download(message.bot, status, message.from_user, url, preset,
                         pool, redis, arq, settings)


@router.callback_query(F.data.startswith("dl:"))
async def on_format(
    cb: CallbackQuery, pool: asyncpg.Pool, redis: Redis, arq: ArqRedis, settings: Settings
) -> None:
    try:
        _, token, code = cb.data.split(":", 2)
        preset = PRESETS[code]
    except (ValueError, KeyError):
        await cb.answer("Unknown option", show_alert=True)
        return

    url = await state.load_link(redis, token)
    if not url:
        await cb.answer("This button expired. Send the link again.", show_alert=True)
        return

    if (await db.upsert_user(pool, cb.from_user))["is_banned"]:
        await cb.answer("You are banned.", show_alert=True)
        return

    await cb.answer()
    await start_download(cb.bot, cb.message, cb.from_user, url, preset, pool, redis, arq, settings)


async def start_download(
    bot: Bot, status: Message, user: User, url: str, preset: Preset,
    pool: asyncpg.Pool, redis: Redis, arq: ArqRedis, settings: Settings,
) -> None:
    """Send from cache or enqueue a job; `status` is the message the worker keeps editing.

    `status` is a reply to the user's link, so the file is sent as a reply to it too.
    """
    chat_id = status.chat.id
    reply_to = status.reply_to_message.message_id if status.reply_to_message else None
    norm = normalize_url(url)
    key = cache_key(norm, preset.code)

    # --- cache hit: resend the stored file_id, no download ---
    cached = await db.get_cached(pool, key)
    if cached:
        try:
            await send_cached(bot, chat_id, cached, reply_to=reply_to)
        except TelegramBadRequest:
            # file_id no longer valid (very rare): drop it and fall through to a fresh download
            log.warning("stale file_id for %s, re-downloading", key)
            await db.delete_cached(pool, key)
        else:
            await state.incr_stat(redis, "cache_hit")
            await db.create_job(
                pool, id=uuid.uuid4().hex, user_id=user.id, chat_id=chat_id, url=url,
                normalized_url=norm, format=preset.code, cache_key=key, status="cached",
            )
            await _safe_delete(status)
            return

    # --- cache miss: enqueue for a worker ---
    job_id = uuid.uuid4().hex
    # Admins skip the per-user cap (the global DOWNLOAD_CONCURRENCY still applies).
    if not settings.is_admin(user.id) and not await state.acquire_user_slot(
        redis, user.id, job_id, settings.max_jobs_per_user
    ):
        await _safe_edit(
            status,
            f"⏳ You already have {settings.max_jobs_per_user} downloads in progress. "
            "Wait for one to finish, then send the link again.",
        )
        return
    try:
        await state.incr_stat(redis, "cache_miss")
        await db.create_job(
            pool, id=job_id, user_id=user.id, chat_id=chat_id,
            status_message_id=status.message_id, reply_to_message_id=reply_to,
            url=url, normalized_url=norm,
            format=preset.code, cache_key=key, status="queued",
        )
        position = await state.mark_waiting(redis, job_id)
        # Edit before enqueueing so this can never overwrite the worker's later status.
        await _safe_edit(status, f"🕒 Queued ({preset.label}). Position in queue: #{position}")
        await arq.enqueue_job("process_job", job_id, _job_id=job_id)
    except Exception:
        await state.release_user_slot(redis, user.id, job_id)
        await state.unmark_waiting(redis, job_id)
        raise


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, disable_web_page_preview=True)
    except TelegramAPIError:
        pass


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
