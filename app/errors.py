"""Map yt-dlp / Telegram failures to short user-facing messages (no stack traces)."""


class JobError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


MESSAGES = {
    "private": "🔒 This video is private or needs a login.",
    "unavailable": "🚫 This link is expired, deleted or unavailable.",
    "blocked": "⛔ The source blocked the download (geo/age restriction or rate limit). Try again later.",
    "too_big": "📦 The file is too big (over 2 GB). Try a lower quality or audio only.",
    "unsupported": "❓ This link is not supported.",
    "no_format": "🎞 That quality is not available for this video. Pick another one.",
    "live": "📡 Live streams can't be downloaded.",
    "upload_failed": "📤 Upload to Telegram failed. Please try again.",
    "timeout": "⏱ The download took too long and was cancelled.",
    "unknown": "❌ Download failed. Please try again later.",
}

# Order matters: first match wins.
_PATTERNS = [
    ("too_big", ("larger than max-filesize", "file is larger than")),
    ("live", ("is live", "live event", "premieres in", "is_live")),
    ("blocked", (
        "http error 403", "http error 429", "sign in to confirm", "available in your country",
        "geo restrict", "geo-restrict", "age-restricted", "confirm your age", "inappropriate",
        "blocked", "rate-limit", "rate limit", "too many requests",
    )),
    ("private", (
        "private video", "video is private", "login required", "log in", "sign in to view",
        "requires authentication", "--cookies", "members-only", "join this channel",
    )),
    ("no_format", ("requested format is not available", "format is not available")),
    ("unsupported", ("unsupported url", "no video could be found", "no video formats found")),
    ("unavailable", (
        "video unavailable", "has been removed", "no longer available", "not found",
        "http error 404", "http error 410", "deleted", "expired", "does not exist",
    )),
]


def classify(exc: BaseException) -> str:
    if isinstance(exc, JobError):
        return exc.code
    text = str(exc).lower()
    for code, needles in _PATTERNS:
        if any(n in text for n in needles):
            return code
    return "unknown"


def user_message(code: str) -> str:
    return MESSAGES.get(code, MESSAGES["unknown"])
