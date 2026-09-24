"""One-time migration: log the bot out of api.telegram.org so the local
Bot API server can take over. Run ONCE, before the first start of the stack:

    docker compose run --rm bot python -m app.scripts.logout

After logOut the bot can't use the cloud API for 10 minutes, and the local
server is the only thing that talks to Telegram for it.
"""
import asyncio
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError

from app.config import get_settings


async def main() -> int:
    bot = Bot(get_settings().bot_token)  # default session = api.telegram.org
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.log_out()
        print("Logged out from api.telegram.org. Now start the stack: docker compose up -d")
        return 0
    except TelegramUnauthorizedError:
        print("Already logged out of the cloud API (or bad token). Nothing to do.")
        return 0
    finally:
        await bot.session.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
