"""Redis-backed shared state: link tokens, per-user slots, queue position,
anti-flood, the global download semaphore and counters.

Everything lives in Redis so any number of bot/worker processes agree on it.
"""
import asyncio
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from redis.asyncio import Redis

LINK_TTL = 3600
SLOT_TTL = 6 * 3600  # safety net if a worker dies without releasing
WAITING = "vl:waiting"  # zset job_id -> enqueue time (only jobs not yet started)
SEMAPHORE = "vl:dl_semaphore"
SEM_LEASE = 120  # seconds; refreshed while the download runs


def _slots(user_id: int) -> str:
    return f"vl:user_jobs:{user_id}"


# ---------- link tokens (callback_data is capped at 64 bytes) ----------

async def save_link(r: Redis, url: str) -> str:
    token = secrets.token_urlsafe(8)
    await r.set(f"vl:link:{token}", url, ex=LINK_TTL)
    return token


async def load_link(r: Redis, token: str) -> str | None:
    return await r.get(f"vl:link:{token}")


# ---------- anti-flood ----------

async def hit_flood_limit(r: Redis, user_id: int, per_minute: int) -> bool:
    key = f"vl:flood:{user_id}:{int(time.time() // 60)}"
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, 70)
    return n > per_minute


# ---------- per-user job slots ----------

_ACQUIRE_SLOT = """
if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""


async def acquire_user_slot(r: Redis, user_id: int, job_id: str, limit: int) -> bool:
    return bool(await r.eval(_ACQUIRE_SLOT, 1, _slots(user_id), job_id, limit, SLOT_TTL))


async def release_user_slot(r: Redis, user_id: int, job_id: str) -> None:
    await r.srem(_slots(user_id), job_id)


# ---------- queue position ----------

async def mark_waiting(r: Redis, job_id: str) -> int:
    """Add to the waiting set and return 1-based queue position."""
    await r.zadd(WAITING, {job_id: time.time()})
    rank = await r.zrank(WAITING, job_id)
    return (rank or 0) + 1


async def unmark_waiting(r: Redis, job_id: str) -> None:
    await r.zrem(WAITING, job_id)


async def queue_depth(r: Redis) -> int:
    return await r.zcard(WAITING)


# ---------- global download semaphore (across worker processes) ----------

_SEM_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1] - ARGV[4])
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[3]) then
  redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
  return 1
end
return 0
"""


@asynccontextmanager
async def download_slot(r: Redis, limit: int, poll: float = 1.0):
    token = uuid.uuid4().hex
    while not await r.eval(_SEM_ACQUIRE, 1, SEMAPHORE, time.time(), token, limit, SEM_LEASE):
        await asyncio.sleep(poll)

    async def keepalive():
        while True:
            await asyncio.sleep(SEM_LEASE / 4)
            await r.zadd(SEMAPHORE, {token: time.time()}, xx=True)

    task = asyncio.create_task(keepalive())
    try:
        yield
    finally:
        task.cancel()
        await r.zrem(SEMAPHORE, token)


async def active_downloads(r: Redis) -> int:
    await r.zremrangebyscore(SEMAPHORE, "-inf", time.time() - SEM_LEASE)
    return await r.zcard(SEMAPHORE)


# ---------- dedupe concurrent downloads of the same url+format ----------

@asynccontextmanager
async def inflight_lock(r: Redis, cache_key: str, timeout: int):
    async with r.lock(f"vl:inflight:{cache_key}", timeout=timeout, sleep=1.0):
        yield


# ---------- counters for /stats ----------

async def incr_stat(r: Redis, name: str) -> None:
    await r.hincrby("vl:stats", name, 1)


async def get_stats(r: Redis) -> dict:
    return {k: int(v) for k, v in (await r.hgetall("vl:stats")).items()}
