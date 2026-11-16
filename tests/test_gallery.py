import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.errors import JobError, classify
from app.media import ALBUM_MAX, send_album
from app.worker import download as dl

SETTINGS = SimpleNamespace(max_file_size=10**9, proxy_url="", job_timeout=3600,
                           cookies_dir=Path("/nonexistent"))


def fake_gallery(files: dict[str, bytes], returncode=0, stderr=""):
    real_run = subprocess.run

    def run(cmd, **kw):
        if "gallery_dl" not in cmd:
            return real_run(cmd, **kw)
        workdir = cmd[cmd.index("-D") + 1]
        for name, data in files.items():
            with open(f"{workdir}/{name}", "wb") as f:
                f.write(data)
        return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")

    return run


def test_album_in_post_order(tmp_path, monkeypatch):
    meta = json.dumps({"username": "someone"}).encode()
    monkeypatch.setattr(dl.subprocess, "run", fake_gallery({
        "002_b.mp4": b"v", "002_b.mp4.json": meta,
        "001_a.jpg": b"p", "001_a.jpg.json": meta,
        "003_c.png": b"pp",
    }))
    items = dl.download_gallery("https://www.instagram.com/p/X/", tmp_path, SETTINGS)
    assert [(i.path.name, i.media_type) for i in items] == [
        ("001_a.jpg", "photo"), ("002_b.mp4", "video"), ("003_c.png", "photo"),
    ]
    assert {i.title for i in items} == {"Post by someone"}


def test_gallery_error_is_classified(tmp_path, monkeypatch):
    monkeypatch.setattr(dl.subprocess, "run", fake_gallery(
        {}, returncode=4, stderr="[instagram][error] HTTP redirect to login page (https://...)"))
    with pytest.raises(RuntimeError) as e:
        dl.download_gallery("https://www.instagram.com/p/X/", tmp_path, SETTINGS)
    assert classify(e.value) == "private"


def test_gallery_nothing_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(dl.subprocess, "run", fake_gallery({}))
    with pytest.raises(JobError):
        dl.download_gallery("https://www.instagram.com/p/X/", tmp_path, SETTINGS)


def test_fetch_falls_back_to_ytdlp(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("login page")

    monkeypatch.setattr(dl, "download_gallery", boom)
    monkeypatch.setattr(dl, "download", lambda *a, **kw: "video")
    preset = SimpleNamespace(kind="video")
    assert dl.fetch("https://www.instagram.com/p/X/", preset, tmp_path, SETTINGS, {}) == ["video"]
    # both fail -> the gallery-dl error is the one reported
    monkeypatch.setattr(dl, "download", lambda *a, **kw: 1 / 0)
    with pytest.raises(RuntimeError, match="login page"):
        dl.fetch("https://www.instagram.com/p/X/", preset, tmp_path, SETTINGS, {})


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_media_group(self, chat_id, media, **kw):
        self.calls.append(("group", media))
        return [f"m{i}" for i in range(len(media))]

    async def send_photo(self, chat_id, file, **kw):
        self.calls.append(("photo", kw.get("caption")))
        return "single"


def test_send_album_chunks():
    bot = FakeBot()
    items = [{"media_type": "video" if i == 1 else "photo", "file": f"id{i}"}
             for i in range(ALBUM_MAX + 1)]
    msgs = asyncio.run(send_album(bot, 1, items, caption="cap"))
    assert len(msgs) == ALBUM_MAX + 1
    kind, group = bot.calls[0]
    assert kind == "group" and len(group) == ALBUM_MAX
    assert [m.type for m in group[:3]] == ["photo", "video", "photo"]
    assert group[0].caption == "cap" and group[1].caption is None
    assert bot.calls[1] == ("photo", None)  # the 11th item goes alone, without the caption
