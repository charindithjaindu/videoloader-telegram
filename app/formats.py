"""Format/quality presets offered as inline buttons, and the cache key."""
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    code: str  # short, goes into callback_data and the cache key
    label: str
    kind: str  # "video" | "audio"
    ytdlp: dict


def _video(height: int | None) -> dict:
    h = f"[height<={height}]" if height else ""
    return {
        # Prefer mp4/h264+m4a so Telegram can stream it; fall back to anything.
        "format": (
            f"bv*{h}[ext=mp4][vcodec^=avc]+ba[ext=m4a]/"
            f"bv*{h}[ext=mp4]+ba[ext=m4a]/"
            f"b{h}[ext=mp4]/bv*{h}+ba/b{h}/b"
        ),
        "merge_output_format": "mp4",
    }


PRESETS: dict[str, Preset] = {
    p.code: p
    for p in (
        Preset("v1080", "1080p", "video", _video(1080)),
        Preset("v720", "720p", "video", _video(720)),
        Preset("v480", "480p", "video", _video(480)),
        Preset("v360", "360p", "video", _video(360)),
        Preset("vbest", "Best", "video", _video(None)),
        Preset(
            "a_mp3", "MP3", "audio",
            {
                "format": "ba/b",
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ],
            },
        ),
        Preset(
            "a_m4a", "M4A", "audio",
            {
                "format": "ba[ext=m4a]/ba/b",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
            },
        ),
    )
}


def cache_key(normalized_url: str, preset_code: str) -> str:
    return hashlib.sha256(f"{normalized_url}|{preset_code}".encode()).hexdigest()
