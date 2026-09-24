# 📹 videoloader-telegram

Telegram bot that downloads media from YouTube, TikTok, Instagram, X/Twitter, Facebook and
anything else yt-dlp supports, and sends the file back. Built to scale past a few thousand
users: webhook ingress on the official Bot API, a Redis job queue, separate download workers,
and a self-hosted **local Bot API server** for 2 GB uploads.

## How it works

```
Telegram ⇄ telegram-bot-api (--local) ──webhook──▶ bot (aiogram 3, aiohttp)
                 ▲      ▲                              │  parse URL → buttons
                 │      │ file:///data/downloads/...   │  pick → cache lookup (Postgres)
                 │      │                              │    hit  → sendVideo(file_id), done
                 │   worker ×N (arq) ◀── Redis queue ──┘    miss → enqueue, "queued #N"
                 │      │ yt-dlp + ffmpeg (global semaphore)
                 └──────┘ upload → store file_id → send → delete temp files
```

- **bot** (`app/bot`): webhook handlers only. They parse, check the cache, enqueue and
  reply. They never run yt-dlp, ffmpeg or a file upload. The webhook replies 200 right away
  (`handle_in_background`).
- **worker** (`app/worker`): arq workers run yt-dlp in a thread, edit progress at most every
  `PROGRESS_INTERVAL` seconds, and upload through the local server with `file:///abs/path`
  from the shared volume. Then they store the `file_id`, send the file and delete the temp dir.
- **Cache**: `sha256(normalized_url | format)` → `{file_id, file_unique_id, size, mime, …}`
  in Postgres. The same video in the same format is uploaded once and then resent by
  `file_id`. URLs are normalized (tracking params stripped, `youtu.be`/shorts →
  `watch?v=`, `twitter.com` → `x.com`, …). If two users request the same video at the same
  time, a Redis lock makes sure it downloads once.
- **Limits**:
  - A Redis semaphore caps simultaneous downloads across all replicas (`DOWNLOAD_CONCURRENCY`).
  - Each user can have at most `MAX_JOBS_PER_USER` jobs queued or running.
  - Anti-flood: `LINKS_PER_MINUTE` links per user.
  - Outgoing messages pass through a Redis GCRA limiter in every process: ~1 msg/s per
    private chat, 20/min per group, ~30/s globally.
  - HTTP 429 is retried after `retry_after`.
- **Storage**: Postgres holds users, jobs and the file cache. Redis holds the queue, FSM
  storage, rate limits, per-user slots, queue positions and counters.

## Deploy (Docker Compose)

1. Get `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` from https://my.telegram.org/apps and a bot
   token from @BotFather.
2. `cp .env.example .env` and fill it in.
3. **Once, before the first start**, log the bot out of `api.telegram.org` so the local
   server can take it over:
   ```bash
   docker compose run --rm --no-deps bot python -m app.scripts.logout
   ```
   (After `logOut` the cloud API refuses the bot for ~10 minutes. That's expected.)
4. Start everything:
   ```bash
   docker compose up -d --build
   docker compose up -d --scale worker=4   # more download workers
   ```

Services: `telegram-bot-api` (local mode), `bot`, `worker`, `postgres`, `redis`. The bot sets
its webhook on the local server to `http://bot:8080/webhook`. The local server fetches updates
from Telegram itself, so **nothing needs to be exposed publicly and you don't need
nginx/Caddy/TLS**.

The `downloads` volume is mounted at the same absolute path (`/data/downloads`) in the worker
and in `telegram-bot-api`. That's what makes `file://` uploads work.

Cookies for sites that need a login go in `./cookies/<platform>.txt` (`youtube`, `tiktok`,
`instagram`, `twitter`, `facebook`, …). They're mounted read-only into the workers; each
job gives yt-dlp a temporary copy, so the files on disk are never rewritten.

### Server notes

- **Docker permissions**: if your user isn't in the `docker` group, prefix every compose
  command with `sudo`.
- **Host-only proxy (WARP)**: a proxy that listens on the host's `127.0.0.1` (such as
  Cloudflare WARP in proxy mode) can't be reached from containers. Copy
  `docker-compose.override.example.yml` to `docker-compose.override.yml` (git-ignored). It
  pins the compose network to `172.30.0.0/24` and adds a `warp-bridge` socat container that
  forwards `172.30.0.1:40001` to the host proxy. Then set
  `PROXY_URL=socks5://172.30.0.1:40001`. With ufw on, allow the bridge:
  `sudo ufw allow from 172.30.0.0/24 to 172.30.0.1 port 40001 proto tcp`.
- **Migrating from the old Pyrogram bot**: stop the old `bot.py` process first (only one
  client can run the bot). Reuse `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`/`HASH`, `ADMINS`
  and `LOGGER_CHANNEL_ID` from the old `.env`. `PROXY_HOST`/`PORT`/`TYPE` become one
  `PROXY_URL`. Keep the server's `cookies/` if they're newer than the repo's. The old
  `*.session` file is no longer used.
- **Updating**: `git pull && docker compose up -d --build`. The logout step is only needed
  once.
- **Checking**: `docker compose ps`, `docker compose logs -f worker bot`.

## Commands

- `/start`: short help
- send any link → pick 🎬 1080p/720p/480p/360p/Best or 🎵 MP3/M4A
- `/stats` (admins in `ADMINS` only): queue depth, active downloads, cache hit rate, jobs and
  errors in the last 24h

Status flow: `🕒 Queued (#N)` → `⬇️ Downloading 45% …` → `📤 Uploading` → `✅ Done`.
Failures show one short line: private video, expired/removed link, file too big, source
blocked, unsupported link, and so on. Users never see a stack trace.

## Configuration

See `.env.example`. Main knobs: `DOWNLOAD_CONCURRENCY` (8–20), `WORKER_MAX_JOBS`,
`WORKER_REPLICAS`, `MAX_JOBS_PER_USER`, `PROGRESS_INTERVAL`, `PROXY_URL`, `LOGGER_CHANNEL_ID`.

## Development

```bash
pip install -r requirements.txt pytest
pytest
```
