"""Ingress process: aiogram 3 webhook server (aiohttp). No downloads here."""
import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from arq import create_pool as create_arq_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app import db
from app.bot.handlers import router
from app.config import get_settings
from app.telegram import make_bot

log = logging.getLogger(__name__)


async def on_startup(dispatcher: Dispatcher, bot, settings) -> None:
    dispatcher["pool"] = await db.create_pool(settings.database_url)
    dispatcher["arq"] = await create_arq_pool(RedisSettings.from_dsn(settings.redis_url))
    await bot.set_webhook(
        settings.webhook_url,
        secret_token=settings.webhook_secret or None,
        allowed_updates=dispatcher.resolve_used_update_types(),
        max_connections=100,
    )
    await bot.set_my_commands([BotCommand(command="start", description="How to use the bot")])
    log.info("webhook set to %s via %s", settings.webhook_url, settings.telegram_api_base)


async def on_shutdown(dispatcher: Dispatcher) -> None:
    await dispatcher["pool"].close()
    await dispatcher["arq"].aclose()
    await dispatcher["redis"].aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = make_bot(settings, redis)

    dp = Dispatcher(storage=RedisStorage(Redis.from_url(settings.redis_url)))
    dp["settings"] = settings
    dp["redis"] = redis
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    # handle_in_background=True: reply 200 to the Bot API immediately, process after.
    SimpleRequestHandler(
        dispatcher=dp, bot=bot, secret_token=settings.webhook_secret or None,
        handle_in_background=True,
    ).register(app, path=settings.webhook_path)
    app.router.add_get("/healthz", lambda _: web.Response(text="ok"))
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=settings.webhook_host, port=settings.webhook_port)


if __name__ == "__main__":
    main()
