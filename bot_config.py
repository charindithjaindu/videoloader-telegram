"""
Telegram Bot Configuration
Get your API credentials from: https://my.telegram.org/apps
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram API credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Proxy settings (optional)
PROXY_HOST = os.getenv('PROXY_HOST', '')
PROXY_PORT = os.getenv('PROXY_PORT', '')
PROXY_TYPE = os.getenv('PROXY_TYPE', 'socks5')  # socks5 or http

# Build proxy URL if configured
PROXY_URL = None
if PROXY_HOST and PROXY_PORT:
    PROXY_URL = f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"
    print(f"🔒 Proxy configured: {PROXY_URL}")

# Bot settings
BOT_NAME = "Video Downloader Bot"
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2000 MB (Increased from default 50MB Telegram limit)

# Session file
SESSION_NAME = 'bot_session'

# Logger channel (for forwarding downloads, except admins)
LOGGER_CHANNEL_ID = os.getenv('LOGGER_CHANNEL_ID', '')
if LOGGER_CHANNEL_ID:
    try:
        LOGGER_CHANNEL_ID = int(LOGGER_CHANNEL_ID)
        print(f"📋 Logger channel configured: {LOGGER_CHANNEL_ID}")
    except ValueError:
        print("⚠️  Invalid LOGGER_CHANNEL_ID format, logging disabled")
        LOGGER_CHANNEL_ID = None
else:
    LOGGER_CHANNEL_ID = None

# Admin user IDs (won't be logged)
ADMINS = os.getenv('ADMINS', '')
if ADMINS:
    try:
        ADMINS = [int(admin_id.strip()) for admin_id in ADMINS.split(',') if admin_id.strip()]
        print(f"👑 Admin users: {ADMINS}")
    except ValueError:
        print("⚠️  Invalid ADMINS format, using empty list")
        ADMINS = []
else:
    ADMINS = []
