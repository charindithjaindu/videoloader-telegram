"""
Configuration for different video platforms
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_DIR = os.path.join(BASE_DIR, 'cookies')
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')

# Proxy configuration
PROXY_HOST = os.getenv('PROXY_HOST', '')
PROXY_PORT = os.getenv('PROXY_PORT', '')
PROXY_TYPE = os.getenv('PROXY_TYPE', 'socks5')

# Build proxy URL if configured
PROXY_URL = None
if PROXY_HOST and PROXY_PORT:
    PROXY_URL = f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"

# Platform configurations
PLATFORMS = {
    'tiktok': {
        'name': 'TikTok',
        'cookies_file': os.path.join(COOKIES_DIR, 'tiktok.txt'),
        'enabled': True,
        'domains': ['tiktok.com', 'vm.tiktok.com']
    },
    'instagram': {
        'name': 'Instagram',
        'cookies_file': os.path.join(COOKIES_DIR, 'instagram.txt'),
        'enabled': True,  # Enabled with cookies
        'domains': ['instagram.com', 'instagr.am']
    },
    'facebook': {
        'name': 'Facebook',
        'cookies_file': os.path.join(COOKIES_DIR, 'facebook.txt'),
        'enabled': True,  # Enabled with cookies
        'domains': ['facebook.com', 'fb.watch', 'fb.com']
    },
    'youtube': {
        'name': 'YouTube',
        'cookies_file': None,  # YouTube usually doesn't need cookies for public videos
        'enabled': True,
        'domains': ['youtube.com', 'youtu.be']
    }
}

# yt-dlp default options
DEFAULT_YT_DLP_OPTIONS = {
    # Updated format to fix Instagram audio issues
    # Priority: best mp4 with audio > merge best video+audio > fallback to best
    'format': 'best[ext=mp4]/bestvideo*+bestaudio*/best',
    'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
    'quiet': False,
    'no_warnings': False,
    'extract_flat': False,
    # Ensure audio is merged properly
    'merge_output_format': 'mp4',
    # Prefer formats with audio
    'prefer_free_formats': False,
}

# Add proxy if configured
if PROXY_URL:
    DEFAULT_YT_DLP_OPTIONS['proxy'] = PROXY_URL
    print(f"🔒 Using proxy: {PROXY_URL}")


def get_platform_for_url(url: str) -> dict | None:
    """
    Determine which platform a URL belongs to
    
    Args:
        url: The video URL
        
    Returns:
        Platform configuration dict or None if not found
    """
    url_lower = url.lower()
    for platform_key, platform_config in PLATFORMS.items():
        if any(domain in url_lower for domain in platform_config['domains']):
            return {
                'key': platform_key,
                **platform_config
            }
    return None


def ensure_directories():
    """Create necessary directories if they don't exist"""
    os.makedirs(COOKIES_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
