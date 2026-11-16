"""yt-dlp / gallery-dl wrappers. Blocking: always run them via asyncio.to_thread from the worker.

yt-dlp handles everything with a video in it. Instagram posts (/p/...) can also be a
photo or an album of photos and videos, which yt-dlp can't fetch, so those go through
gallery-dl first.
"""
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import match_filter_func

from app.config import Settings
from app.errors import JobError
from app.formats import Preset
from app.urls import detect_platform, is_instagram_post

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png"}  # what Telegram takes as a photo as-is
IMAGE_EXTS = PHOTO_EXTS | {".webp", ".heic", ".avif"}  # the rest is converted to .jpg


@dataclass
class Downloaded:
    path: Path
    size: int
    media_type: str  # video | audio | photo | document
    title: str | None
    duration: int | None
    width: int | None
    height: int | None


def _cookiefile(settings: Settings, url: str) -> str | None:
    platform = detect_platform(url)
    if not platform:
        return None
    f = settings.cookies_dir / f"{platform}.txt"
    return str(f) if f.is_file() else None


def fetch(url: str, preset: Preset, workdir: Path, settings: Settings, progress: dict) -> list[Downloaded]:
    """Download everything a link points at: one file, or several for an Instagram album."""
    if preset.kind == "video" and is_instagram_post(url):
        try:
            return download_gallery(url, workdir, settings)
        except Exception as gallery_error:  # noqa: BLE001
            # gallery-dl needs a login more often than yt-dlp does; a video post may still work.
            log.info("gallery-dl failed for %s (%s), trying yt-dlp", url, str(gallery_error)[:200])
            shutil.rmtree(workdir, ignore_errors=True)
            try:
                return [download(url, preset, workdir, settings, progress)]
            except Exception:  # noqa: BLE001
                raise gallery_error from None
    return [download(url, preset, workdir, settings, progress)]


def download_gallery(url: str, workdir: Path, settings: Settings) -> list[Downloaded]:
    """Fetch every photo/video of an Instagram post with gallery-dl, in post order."""
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-mtime", "--no-part",
        "-D", str(workdir), "-f", "{num:>03}_{media_id}.{extension}",  # sorts in post order
        "--write-metadata", "--retries", "3", "--http-timeout", "30",
        "--filesize-max", str(settings.max_file_size),
        "-o", "audio=false",  # no separate music track for photo posts
    ]
    if settings.proxy_url:
        cmd += ["--proxy", settings.proxy_url]
    # Same as for yt-dlp: ./cookies is read-only, so pass a throwaway copy.
    with tempfile.TemporaryDirectory() as tmp:
        if cookiefile := _cookiefile(settings, url):
            cmd += ["--cookies", shutil.copy(cookiefile, Path(tmp) / "cookies.txt")]
        try:
            proc = subprocess.run(cmd + [url], capture_output=True, text=True,
                                  timeout=max(settings.job_timeout - 120, 60))
        except subprocess.TimeoutExpired:
            raise JobError("timeout") from None
    if proc.returncode != 0:
        raise RuntimeError(f"gallery-dl: {proc.stderr.strip()[-1000:] or proc.returncode}")

    title = None
    items: list[Downloaded] = []
    for path in sorted(p for p in workdir.iterdir() if p.is_file()):
        ext = path.suffix.lower()
        if ext == ".json":
            if title is None:
                title = _post_title(path)
            continue
        if ext in VIDEO_EXTS:
            duration, width, height = _probe_video(path)
            items.append(Downloaded(path, path.stat().st_size, "video", None, duration, width, height))
        elif ext in IMAGE_EXTS:
            if ext not in PHOTO_EXTS:
                path = _to_jpg(path)
            items.append(Downloaded(path, path.stat().st_size, "photo", None, None, None, None))
    if not items:
        raise JobError("too_big" if "filesize" in proc.stderr.lower() else "unavailable")
    for item in items:
        item.title = title
    return items


def _post_title(metadata_file: Path) -> str | None:
    try:
        meta = json.loads(metadata_file.read_text())
    except (OSError, ValueError):
        return None
    user = meta.get("username") or meta.get("fullname")
    return f"Post by {user}" if user else None


def _probe_video(path: Path) -> tuple[int | None, int | None, int | None]:
    """(duration, width, height) via ffprobe; all None if it can't be read."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
        data = json.loads(out)
        stream = (data.get("streams") or [{}])[0]
        return (round(float(data["format"]["duration"])), int(stream["width"]), int(stream["height"]))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None, None, None


def _to_jpg(path: Path) -> Path:
    """Convert webp/heic/avif to jpg so Telegram shows it as a photo; keep the original on failure."""
    target = path.with_suffix(".jpg")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-q:v", "2", str(target)],
                       capture_output=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError):
        return path
    return target


def download(url: str, preset: Preset, workdir: Path, settings: Settings, progress: dict) -> Downloaded:
    workdir.mkdir(parents=True, exist_ok=True)

    def on_progress(d: dict) -> None:
        if d.get("status") == "downloading":
            progress.update(
                stage="downloading",
                done=d.get("downloaded_bytes") or 0,
                total=d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                speed=d.get("speed") or 0,
            )

    def on_postprocess(d: dict) -> None:
        if d.get("status") == "started":
            progress["stage"] = "processing"

    opts = {
        "outtmpl": str(workdir / "%(id).60B.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "playlist_items": "1",  # carousels / multi-video posts: first item
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "max_filesize": settings.max_file_size,
        "match_filter": match_filter_func("!is_live"),
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [on_progress],
        "postprocessor_hooks": [on_postprocess],
        **preset.ytdlp,
    }
    if settings.proxy_url:
        opts["proxy"] = settings.proxy_url

    # yt-dlp writes the cookie jar back on close and ./cookies is mounted read-only,
    # so hand it a throwaway copy (kept out of workdir so it's never taken for the media).
    with tempfile.TemporaryDirectory() as tmp:
        if cookiefile := _cookiefile(settings, url):
            opts["cookiefile"] = shutil.copy(cookiefile, Path(tmp) / "cookies.txt")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

    if info and info.get("entries"):
        info = next((e for e in info["entries"] if e), {})
    info = info or {}

    files = [
        p for p in workdir.iterdir()
        if p.is_file() and not p.name.endswith((".part", ".ytdl", ".temp"))
    ]
    if not files:
        # yt-dlp skips silently when a filter rejects the video
        raise JobError("live" if info.get("is_live") else "too_big")
    path = max(files, key=lambda p: p.stat().st_size)
    size = path.stat().st_size
    if size > settings.max_file_size:
        raise JobError("too_big")

    ext = path.suffix.lower()
    if preset.kind == "audio" and ext in AUDIO_EXTS:
        media_type = "audio"
    elif preset.kind == "video" and ext in VIDEO_EXTS:
        media_type = "video"
    else:
        media_type = "document"

    def _int(k: str) -> int | None:
        v = info.get(k)
        return int(v) if isinstance(v, (int, float)) else None

    return Downloaded(
        path=path, size=size, media_type=media_type, title=info.get("title"),
        duration=_int("duration"), width=_int("width"), height=_int("height"),
    )
