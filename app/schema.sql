CREATE TABLE IF NOT EXISTS users (
    id            BIGINT PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    language_code TEXT,
    is_banned     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Preset code used when the user sends a link (see /settings); 'ask' shows the buttons.
ALTER TABLE users ADD COLUMN IF NOT EXISTS default_format TEXT NOT NULL DEFAULT 'vbest';

-- One row per (normalized_url, format): the Telegram file we already uploaded.
CREATE TABLE IF NOT EXISTS file_cache (
    cache_key      TEXT PRIMARY KEY,
    normalized_url TEXT NOT NULL,
    format         TEXT NOT NULL,
    media_type     TEXT NOT NULL,          -- video | audio | document
    file_id        TEXT NOT NULL,
    file_unique_id TEXT NOT NULL,
    size           BIGINT,
    mime           TEXT,
    title          TEXT,
    duration       INTEGER,
    width          INTEGER,
    height         INTEGER,
    hits           BIGINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_hit_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id),
    chat_id           BIGINT NOT NULL,
    status_message_id BIGINT,
    url               TEXT NOT NULL,
    normalized_url    TEXT NOT NULL,
    format            TEXT NOT NULL,
    cache_key         TEXT NOT NULL,
    status            TEXT NOT NULL,       -- queued|downloading|uploading|done|cached|failed
    error_code        TEXT,
    file_size         BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_user_idx ON jobs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs (created_at DESC);
