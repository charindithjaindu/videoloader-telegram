import pytest

from app.errors import JobError, classify


@pytest.mark.parametrize("msg,code", [
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access", "private"),
    ("ERROR: [youtube] x: Video unavailable. This video has been removed by the uploader", "unavailable"),
    ("ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser", "blocked"),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "blocked"),
    ("ERROR: The uploader has not made this video available in your country", "blocked"),
    ("ERROR: Unsupported URL: https://example.com", "unsupported"),
    ("ERROR: [youtube] x: Requested format is not available", "no_format"),
    ("something odd happened", "unknown"),
])
def test_classify(msg, code):
    assert classify(Exception(msg)) == code


def test_job_error_passthrough():
    assert classify(JobError("too_big")) == "too_big"
