"""yt-dlp wrapper. Blocking: always run it via asyncio.to_thread from the worker."""
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import match_filter_func

from app.config import Settings
from app.errors import JobError
from app.formats import Preset
from app.urls import detect_platform

VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}


@dataclass
class Downloaded:
    path: Path
    size: int
    media_type: str  # video | audio | document
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
