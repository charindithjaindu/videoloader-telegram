"""PostgreSQL access (asyncpg): users, jobs, file_id cache."""
from dataclasses import dataclass
from pathlib import Path

import asyncpg

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()
_MIGRATION_LOCK = 0x76_64_6C  # arbitrary advisory lock id


async def create_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        # bot and workers start together; serialize schema creation
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK)
        try:
            await conn.execute(SCHEMA)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _MIGRATION_LOCK)
    return pool


@dataclass
class CachedFile:
    media_type: str
    file_id: str
    file_unique_id: str
    size: int | None
    mime: str | None
    title: str | None
    duration: int | None
    width: int | None
    height: int | None


async def upsert_user(pool: asyncpg.Pool, user) -> asyncpg.Record:
    """Returns the user's (is_banned, default_format)."""
    return await pool.fetchrow(
        """
        INSERT INTO users (id, username, first_name, language_code)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (id) DO UPDATE SET
            username = EXCLUDED.username, first_name = EXCLUDED.first_name,
            language_code = EXCLUDED.language_code, last_seen_at = now()
        RETURNING is_banned, default_format
        """,
        user.id, user.username, user.first_name, user.language_code,
    )


async def set_default_format(pool: asyncpg.Pool, user_id: int, fmt: str) -> None:
    await pool.execute("UPDATE users SET default_format = $2 WHERE id = $1", user_id, fmt)


async def get_cached(pool: asyncpg.Pool, key: str) -> CachedFile | None:
    row = await pool.fetchrow(
        """
        UPDATE file_cache SET hits = hits + 1, last_hit_at = now()
        WHERE cache_key = $1
        RETURNING media_type, file_id, file_unique_id, size, mime, title, duration, width, height
        """,
        key,
    )
    return CachedFile(**dict(row)) if row else None


async def delete_cached(pool: asyncpg.Pool, key: str) -> None:
    await pool.execute("DELETE FROM file_cache WHERE cache_key = $1", key)


async def store_cached(
    pool: asyncpg.Pool, key: str, normalized_url: str, fmt: str, f: CachedFile
) -> None:
    await pool.execute(
        """
        INSERT INTO file_cache (cache_key, normalized_url, format, media_type, file_id,
            file_unique_id, size, mime, title, duration, width, height)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (cache_key) DO UPDATE SET
            media_type = EXCLUDED.media_type, file_id = EXCLUDED.file_id,
            file_unique_id = EXCLUDED.file_unique_id, size = EXCLUDED.size,
            mime = EXCLUDED.mime, title = EXCLUDED.title, duration = EXCLUDED.duration,
            width = EXCLUDED.width, height = EXCLUDED.height
        """,
        key, normalized_url, fmt, f.media_type, f.file_id, f.file_unique_id,
        f.size, f.mime, f.title, f.duration, f.width, f.height,
    )


async def create_job(pool: asyncpg.Pool, **job) -> None:
    cols = ", ".join(job)
    params = ", ".join(f"${i}" for i in range(1, len(job) + 1))
    await pool.execute(f"INSERT INTO jobs ({cols}) VALUES ({params})", *job.values())


async def get_job(pool: asyncpg.Pool, job_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)


async def set_job_status(
    pool: asyncpg.Pool, job_id: str, status: str,
    error_code: str | None = None, file_size: int | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE jobs SET status = $2,
            error_code = COALESCE($3, error_code),
            file_size = COALESCE($4, file_size),
            started_at = CASE WHEN $2 = 'downloading' THEN now() ELSE started_at END,
            finished_at = CASE WHEN $2 IN ('done', 'failed') THEN now() ELSE finished_at END
        WHERE id = $1
        """,
        job_id, status, error_code, file_size,
    )


async def stats(pool: asyncpg.Pool) -> dict:
    row = await pool.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM file_cache) AS cached_files,
            (SELECT coalesce(sum(hits), 0) FROM file_cache) AS cache_hits_total,
            (SELECT count(*) FROM jobs WHERE created_at > now() - interval '24 hours') AS jobs_24h
        """
    )
    by_status = await pool.fetch(
        """
        SELECT status, count(*) AS n FROM jobs
        WHERE created_at > now() - interval '24 hours' GROUP BY status ORDER BY n DESC
        """
    )
    errors = await pool.fetch(
        """
        SELECT error_code, count(*) AS n FROM jobs
        WHERE status = 'failed' AND created_at > now() - interval '24 hours'
        GROUP BY error_code ORDER BY n DESC
        """
    )
    return {
        **dict(row),
        "by_status": {r["status"]: r["n"] for r in by_status},
        "errors": {r["error_code"]: r["n"] for r in errors},
    }
