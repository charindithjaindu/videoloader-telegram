"""Sending media by file_id / local path and reading back what Telegram stored."""
from html import escape

from aiogram import Bot
from aiogram.types import Message

from app.db import CachedFile


def caption_for(title: str | None) -> str | None:
    return f"🎬 {escape(title[:900])}" if title else None


async def send_media(
    bot: Bot, chat_id: int, media_type: str, file: str, *,
    title: str | None = None, duration: int | None = None,
    width: int | None = None, height: int | None = None,
    caption: str | None = None, request_timeout: int | None = None,
) -> Message:
    """`file` is either a Telegram file_id or a file:///abs/path on the shared volume."""
    caption = caption or caption_for(title)
    if media_type == "video":
        return await bot.send_video(
            chat_id, file, caption=caption, duration=duration, width=width, height=height,
            supports_streaming=True, request_timeout=request_timeout,
        )
    if media_type == "audio":
        return await bot.send_audio(
            chat_id, file, caption=caption, duration=duration, title=title,
            request_timeout=request_timeout,
        )
    return await bot.send_document(chat_id, file, caption=caption, request_timeout=request_timeout)


async def send_cached(bot: Bot, chat_id: int, f: CachedFile) -> Message:
    return await send_media(
        bot, chat_id, f.media_type, f.file_id,
        title=f.title, duration=f.duration, width=f.width, height=f.height,
    )


def cached_from_message(msg: Message, title: str | None) -> CachedFile:
    media = msg.video or msg.audio or msg.document
    if media is None:
        raise ValueError("message has no media")
    media_type = "video" if msg.video else "audio" if msg.audio else "document"
    return CachedFile(
        media_type=media_type,
        file_id=media.file_id,
        file_unique_id=media.file_unique_id,
        size=media.file_size,
        mime=media.mime_type,
        title=title,
        duration=getattr(media, "duration", None),
        width=getattr(media, "width", None),
        height=getattr(media, "height", None),
    )
