import pytest

from app.formats import cache_key
from app.urls import detect_platform, extract_url, normalize_url


@pytest.mark.parametrize("a,b", [
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&t=10", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/abc_123", "https://youtube.com/watch?v=abc_123"),
    ("https://twitter.com/u/status/1?s=20&t=x", "https://x.com/u/status/1"),
    ("https://www.instagram.com/reel/XYZ/?igsh=foo&utm_source=ig", "https://instagram.com/reel/XYZ"),
    ("HTTPS://WWW.TikTok.com/@u/video/1?is_from_webapp=1#frag", "https://tiktok.com/@u/video/1"),
])
def test_same_media_same_key(a, b):
    assert normalize_url(a) == normalize_url(b)
    assert cache_key(normalize_url(a), "v720") == cache_key(normalize_url(b), "v720")


def test_meaningful_query_kept():
    assert normalize_url("https://example.com/v?id=5&utm_medium=x") == "https://example.com/v?id=5"


def test_format_changes_key():
    n = normalize_url("https://youtu.be/x")
    assert cache_key(n, "v720") != cache_key(n, "a_mp3")


def test_extract_url():
    assert extract_url("look (https://x.com/a/status/1).") == "https://x.com/a/status/1"
    assert extract_url("no link here") is None


def test_platform():
    assert detect_platform("https://vm.tiktok.com/abc") == "tiktok"
    assert detect_platform("https://mobile.twitter.com/a") == "twitter"
    assert detect_platform("https://example.com") is None
