"""URL extraction, normalization and platform detection."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Query params that never change which media a URL points at.
TRACKING_PARAMS = {
    "si", "feature", "pp", "ab_channel", "igshid", "igsh", "img_index", "fbclid",
    "gclid", "ref", "ref_src", "ref_url", "is_from_webapp", "sender_device",
    "_r", "_t", "share_app_id", "share_link_id", "mibextid", "rdid", "utm_source",
}
TRACKING_PREFIXES = ("utm_",)

HOST_ALIASES = {
    "m.youtube.com": "youtube.com",
    "music.youtube.com": "youtube.com",
    "mobile.twitter.com": "x.com",
    "twitter.com": "x.com",
    "m.facebook.com": "facebook.com",
    "web.facebook.com": "facebook.com",
    "instagr.am": "instagram.com",
}

PLATFORMS = {
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "twitter": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
    "reddit": ("reddit.com", "redd.it"),
    "vimeo": ("vimeo.com",),
}


def extract_url(text: str | None) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    return m.group(0).rstrip(").,!?]}>") if m else None


def _host(netloc: str) -> str:
    host = netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return HOST_ALIASES.get(host, host)


def normalize_url(url: str) -> str:
    """Canonical form used for the cache key: same media -> same string."""
    parts = urlsplit(url.strip())
    host = _host(parts.netloc)
    path = parts.path or "/"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]

    if host == "youtu.be":
        host, query, path = "youtube.com", [("v", path.strip("/"))], "/watch"
    elif host == "youtube.com":
        m = re.match(r"^/(shorts|embed|live|v)/([\w-]+)", path)
        if m:
            path, query = "/watch", [("v", m.group(2))]
        elif path == "/watch":
            query = [(k, v) for k, v in query if k == "v"]
    elif host == "x.com":
        query = [(k, v) for k, v in query if k not in ("s", "t")]

    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def detect_platform(url: str) -> str | None:
    host = _host(urlsplit(url).netloc)
    for name, domains in PLATFORMS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    return None
