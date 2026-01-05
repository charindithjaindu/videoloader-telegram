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
