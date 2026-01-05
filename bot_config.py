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

# Bot settings
BOT_NAME = "Video Downloader Bot"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (Telegram limit for bots is 50MB)

# Session file
SESSION_NAME = 'bot_session'
