"""Settings shared by the bot and worker processes (read from env / .env)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = Field(validation_alias="TELEGRAM_BOT_TOKEN")

    # Local Bot API server (tdlib/telegram-bot-api --local). The bot never talks
    # to api.telegram.org at runtime; only scripts/logout.py does, once.
    telegram_api_base: str = "http://telegram-bot-api:8081"

    # Where the local API server delivers updates. With a local server this can
    # be plain HTTP on the internal Docker network: no public HTTPS needed.
    webhook_url: str = "http://bot:8080/webhook"
    webhook_path: str = "/webhook"
    webhook_secret: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    database_url: str = "postgresql://videoloader:videoloader@postgres:5432/videoloader"
    redis_url: str = "redis://redis:6379/0"

    # Shared volume, mounted at the SAME absolute path in worker and telegram-bot-api
    downloads_dir: Path = Path("/data/downloads")
    cookies_dir: Path = Path("/app/cookies")
    proxy_url: str = ""

    # Limits
    download_concurrency: int = 10  # global across all worker processes
    worker_max_jobs: int = 10  # arq jobs per worker process
    max_jobs_per_user: int = 3
    links_per_minute: int = 10  # anti-flood per user
    max_file_size: int = 2000 * 1024 * 1024  # local Bot API upload limit
    progress_interval: float = 4.0  # seconds between progress edits
    job_timeout: int = 3600
    upload_timeout: int = 1800

    admins: Annotated[list[int], NoDecode] = []
    logger_channel_id: int | None = None

    @field_validator("admins", mode="before")
    @classmethod
    def _split_admins(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        return v

    def is_admin(self, user_id: int) -> bool:
        """Admins (ADMINS in .env) can use /stats, aren't logged and skip per-user limits."""
        return user_id in self.admins

    @field_validator("logger_channel_id", mode="before")
    @classmethod
    def _empty_channel(cls, v):
        return None if v in ("", None) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
