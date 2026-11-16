"""Sending media by file_id / local path and reading back what Telegram stored."""
from html import escape

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo, Message, ReplyParameters

from app.db import CachedFile

ALBUM_MAX = 10  # Telegram's limit per media group; longer posts are sent as several groups


def caption_for(title: str | None, media_type: str = "video") -> str | None:
    if not title:
        return None
    icon = "🖼" if media_type in ("photo", "album") else "🎬"
    return f"{icon} {escape(title[:900])}"


def _reply(reply_to: int | None) -> ReplyParameters | None:
    # Still send if the user deleted the message we reply to.
    return ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None


async def send_media(
    bot: Bot, chat_id: int, media_type: str, file: str, *,
    title: str | None = None, duration: int | None = None,
    width: int | None = None, height: int | None = None,
    caption: str | None = None, request_timeout: int | None = None,
    reply_to: int | None = None,
) -> Message:
    """`file` is either a Telegram file_id or a file:///abs/path on the shared volume."""
    caption = caption or caption_for(title, media_type)
    reply = _reply(reply_to)
    if media_type == "video":
        return await bot.send_video(
            chat_id, file, caption=caption, duration=duration, width=width, height=height,
            supports_streaming=True, request_timeout=request_timeout, reply_parameters=reply,
        )
    if media_type == "audio":
        return await bot.send_audio(
            chat_id, file, caption=caption, duration=duration, title=title,
            request_timeout=request_timeout, reply_parameters=reply,
        )
    if media_type == "photo":
        return await bot.send_photo(chat_id, file, caption=caption,
                                    request_timeout=request_timeout, reply_parameters=reply)
    return await bot.send_document(chat_id, file, caption=caption, request_timeout=request_timeout,
                                   reply_parameters=reply)


async def send_album(
    bot: Bot, chat_id: int, items: list[dict], *,
    caption: str | None = None, request_timeout: int | None = None,
    reply_to: int | None = None,
) -> list[Message]:
    """Send photos/videos as Telegram albums, in order.

    Each item: {media_type: photo|video, file: file_id or file:// URI, duration, width, height}.
    The caption goes on the first item (Telegram shows it under the whole album).
    """
    messages: list[Message] = []
    for start in range(0, len(items), ALBUM_MAX):
        chunk = items[start:start + ALBUM_MAX]
        cap = caption if start == 0 else None
        if len(chunk) == 1:  # a media group needs at least 2 items
            it = chunk[0]
            messages.append(await send_media(
                bot, chat_id, it["media_type"], it["file"], caption=cap,
                duration=it.get("duration"), width=it.get("width"), height=it.get("height"),
                request_timeout=request_timeout, reply_to=reply_to,
            ))
            continue
        group = []
        for i, it in enumerate(chunk):
            item_cap = cap if i == 0 else None
            if it["media_type"] == "video":
                group.append(InputMediaVideo(
                    media=it["file"], caption=item_cap, duration=it.get("duration"),
                    width=it.get("width"), height=it.get("height"), supports_streaming=True,
                ))
            else:
                group.append(InputMediaPhoto(media=it["file"], caption=item_cap))
        messages += await bot.send_media_group(
            chat_id, group, request_timeout=request_timeout, reply_parameters=_reply(reply_to),
        )
    return messages


async def send_cached(
    bot: Bot, chat_id: int, f: CachedFile, reply_to: int | None = None,
    caption: str | None = None,
) -> None:
    caption = caption or caption_for(f.title, f.media_type)
    if f.items:
        await send_album(
            bot, chat_id, [{**it, "file": it["file_id"]} for it in f.items],
            caption=caption, reply_to=reply_to,
        )
    else:
        await send_media(
            bot, chat_id, f.media_type, f.file_id, caption=caption, title=f.title,
            duration=f.duration, width=f.width, height=f.height, reply_to=reply_to,
        )


def cached_from_message(msg: Message, title: str | None) -> CachedFile:
    photo = msg.photo[-1] if msg.photo else None  # largest size
    media = msg.video or msg.audio or photo or msg.document
    if media is None:
        raise ValueError("message has no media")
    media_type = (
        "video" if msg.video else "audio" if msg.audio else "photo" if photo else "document"
    )
    return CachedFile(
        media_type=media_type,
        file_id=media.file_id,
        file_unique_id=media.file_unique_id,
        size=media.file_size,
        mime=getattr(media, "mime_type", None),
        title=title,
        duration=getattr(media, "duration", None),
        width=getattr(media, "width", None),
        height=getattr(media, "height", None),
    )


def cached_from_album(messages: list[Message], title: str | None) -> CachedFile:
    parts = [cached_from_message(m, title) for m in messages]
    first = parts[0]
    return CachedFile(
        media_type="album", file_id=first.file_id, file_unique_id=first.file_unique_id,
        size=sum(p.size or 0 for p in parts), mime=None, title=title,
        duration=None, width=None, height=None,
        items=[
            {"media_type": p.media_type, "file_id": p.file_id, "duration": p.duration,
             "width": p.width, "height": p.height}
            for p in parts
        ],
    )
