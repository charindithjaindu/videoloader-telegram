"""Bot factory: local Bot API server + Redis-backed send throttling + 429 retry."""
import asyncio
import logging
import time

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter
from redis.asyncio import Redis

from app.config import Settings

log = logging.getLogger(__name__)

# GCRA with reservation: every caller books the next free slot and is told how
# long to sleep until it, so callers are served in FIFO order (no starvation).
# At most `burst` requests at once, then one per `period` ms.
_GCRA = """
local now = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local tau = period * (tonumber(ARGV[3]) - 1)
local tat = tonumber(redis.call('GET', KEYS[1]) or now)
if tat < now then tat = now end
local wait = tat - tau - now
if wait < 0 then wait = 0 end
redis.call('SET', KEYS[1], tat + period, 'PX', math.ceil(tat + period - now + 1000))
return wait
"""

GLOBAL = ("vl:rl:global", 34, 30)  # ~30 msg/s across all processes
PRIVATE = (1000, 1)  # ~1 msg/s per private chat
GROUP = (3000, 1)  # 20 msg/min per group/channel
THROTTLED_PREFIXES = ("send", "edit", "copy", "forward")


class RateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def _take(self, key: str, period: int, burst: int) -> None:
        wait = await self.redis.eval(_GCRA, 1, key, int(time.time() * 1000), period, burst)
        if wait:
            await asyncio.sleep(int(wait) / 1000)

    async def acquire(self, chat_id: int | str | None) -> None:
        if isinstance(chat_id, int):
            period, burst = PRIVATE if chat_id > 0 else GROUP
            await self._take(f"vl:rl:chat:{chat_id}", period, burst)
        await self._take(*GLOBAL)


class ThrottleMiddleware(BaseRequestMiddleware):
    """Applies to every outgoing request from this Bot instance, in any process."""

    def __init__(self, limiter: RateLimiter, max_retries: int = 5):
        self.limiter = limiter
        self.max_retries = max_retries

    async def __call__(self, make_request, bot, method):
        throttled = method.__api_method__.startswith(THROTTLED_PREFIXES)
        for attempt in range(self.max_retries + 1):
            if throttled:
                await self.limiter.acquire(getattr(method, "chat_id", None))
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                if attempt == self.max_retries:
                    raise
                log.warning("429 on %s, retry in %ss", method.__api_method__, e.retry_after)
                await asyncio.sleep(e.retry_after + 0.5)


def make_bot(settings: Settings, redis: Redis) -> Bot:
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.telegram_api_base, is_local=True)
    )
    session.middleware(ThrottleMiddleware(RateLimiter(redis)))
    return Bot(
        settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
