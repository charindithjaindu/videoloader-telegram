"""
Video downloader module using yt-dlp
"""
import os
import yt_dlp
from typing import Optional
from config import (
    DEFAULT_YT_DLP_OPTIONS,
    get_platform_for_url,
    ensure_directories,
    PLATFORMS
)


class VideoDownloader:
    """Simple video downloader using yt-dlp"""
    
    def __init__(self):
        """Initialize the downloader"""
        ensure_directories()
    
    def download(self, url: str, custom_options: Optional[dict] = None) -> bool:
        """
        Download a video from the given URL
        
        Args:
            url: The video URL to download
            custom_options: Optional custom yt-dlp options to override defaults
            
        Returns:
            True if download was successful, False otherwise
        """
        # Detect platform
        platform = get_platform_for_url(url)
        
        if platform:
            print(f"🎯 Detected platform: {platform['name']}")
            
            if not platform['enabled']:
                print(f"⚠️  {platform['name']} support is not enabled yet.")
                print(f"   Please add cookies to: {platform['cookies_file']}")
                return False
        else:
            print("⚠️  Platform not recognized, attempting generic download...")
        
        # Prepare yt-dlp options
        ydl_opts = DEFAULT_YT_DLP_OPTIONS.copy()
        
        # Add cookies if available for this platform
        if platform and platform['cookies_file']:
            cookies_file = platform['cookies_file']
            if os.path.exists(cookies_file):
                ydl_opts['cookiefile'] = cookies_file
                print(f"🍪 Using cookies from: {os.path.basename(cookies_file)}")
            else:
                print(f"⚠️  Cookies file not found: {cookies_file}")
                print("   Download may fail for private or restricted content")
        
        # Override with custom options if provided
        if custom_options:
            ydl_opts.update(custom_options)
        
        # Download the video
        try:
            print(f"📥 Starting download from: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    print(f"✅ Successfully downloaded: {info.get('title', 'Unknown title')}")
                    return True
        except Exception as e:
            print(f"❌ Download failed: {str(e)}")
            return False
        
        return False
    
    def get_video_info(self, url: str) -> Optional[dict]:
        """
        Get video information without downloading
        
        Args:
            url: The video URL
            
        Returns:
            Dictionary containing video information or None if failed
        """
        platform = get_platform_for_url(url)
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Add cookies if available
        if platform and platform['cookies_file'] and os.path.exists(platform['cookies_file']):
            ydl_opts['cookiefile'] = platform['cookies_file']
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'platform': platform['name'] if platform else 'Unknown'
                }
        except Exception as e:
            print(f"❌ Failed to get video info: {str(e)}")
            return None
    
    @staticmethod
    def list_platforms():
        """List all configured platforms and their status"""
        print("\n📋 Configured Platforms:")
        print("-" * 50)
        for key, platform in PLATFORMS.items():
            status = "✅ Enabled" if platform['enabled'] else "❌ Disabled"
            cookies_status = ""
            if platform['cookies_file']:
                if os.path.exists(platform['cookies_file']):
                    cookies_status = "🍪 Cookies available"
                else:
                    cookies_status = "⚠️  No cookies"
            else:
                cookies_status = "🚫 No cookies needed"
            
            print(f"{platform['name']:12} - {status:12} - {cookies_status}")
        print("-" * 50)
