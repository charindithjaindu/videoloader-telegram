#!/usr/bin/env python3
"""
Telegram Video Downloader Bot using Telethon
User sends a video link, bot downloads and sends back the video
"""
import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
import yt_dlp

from bot_config import API_ID, API_HASH, BOT_TOKEN, SESSION_NAME, MAX_FILE_SIZE
from config import get_platform_for_url, ensure_directories, DOWNLOADS_DIR


class VideoDownloaderBot:
    """Telegram bot for downloading and sending videos"""
    
    def __init__(self):
        """Initialize the bot"""
        # Validate credentials
        if not all([API_ID, API_HASH, BOT_TOKEN]):
            raise ValueError(
                "Missing credentials! Please set TELEGRAM_API_ID, "
                "TELEGRAM_API_HASH, and TELEGRAM_BOT_TOKEN in .env file"
            )
        
        # Create Telegram client
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        ensure_directories()
        
        # Register event handlers
        self.client.add_event_handler(self.start_handler, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.help_handler, events.NewMessage(pattern='/help'))
        self.client.add_event_handler(self.platforms_handler, events.NewMessage(pattern='/platforms'))
        self.client.add_event_handler(self.message_handler, events.NewMessage())
    
    async def start_handler(self, event):
        """Handle /start command"""
        welcome_msg = """
🎬 **Welcome to Video Downloader Bot!**

Send me a video link from:
• TikTok 📱
• Instagram 📸
• Facebook 🔵
• YouTube ▶️

And I'll download and send it back to you!

**Commands:**
/help - Show help message
/platforms - List supported platforms
        """
        await event.respond(welcome_msg)
        raise events.StopPropagation
    
    async def help_handler(self, event):
        """Handle /help command"""
        help_msg = """
📖 **How to use:**

1️⃣ Send me a video link
2️⃣ Wait while I download it
3️⃣ Receive your video!

**Supported Platforms:**
✅ TikTok
✅ Instagram  
✅ Facebook
✅ YouTube
✅ And many more!

**Note:** Maximum file size is 50MB due to Telegram limits.
        """
        await event.respond(help_msg)
        raise events.StopPropagation
    
    async def platforms_handler(self, event):
        """Handle /platforms command"""
        platform_msg = """
🌐 **Supported Platforms:**

✅ **TikTok** - Full support with cookies
✅ **Instagram** - Full support with cookies
✅ **Facebook** - Full support with cookies  
✅ **YouTube** - Full support (no cookies needed)
📹 **And many more platforms supported by yt-dlp!**
        """
        await event.respond(platform_msg)
        raise events.StopPropagation
    
    async def message_handler(self, event):
        """Handle regular messages (video links)"""
        message = event.message.text
        
        # Ignore commands
        if message.startswith('/'):
            return
        
        # Check if message contains a URL
        if not message.startswith('http'):
            await event.respond(
                "⚠️ Please send a valid video URL starting with http:// or https://\n\n"
                "Use /help for more information."
            )
            return
        
        # Process the video link
        await self.download_and_send_video(event, message)
    
    async def download_and_send_video(self, event, url):
        """Download video and send it to user"""
        # Send initial processing message
        status_msg = await event.respond("🔍 Processing your link...")
        
        try:
            # Detect platform
            platform = get_platform_for_url(url)
            
            if platform:
                await status_msg.edit(f"🎯 Detected: {platform['name']}\n📥 Downloading...")
            else:
                await status_msg.edit("📥 Downloading video...")
            
            # Prepare download options
            temp_file = os.path.join(DOWNLOADS_DIR, f'temp_{event.chat_id}_%(title)s.%(ext)s')
            
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': temp_file,
                'quiet': True,
                'no_warnings': True,
            }
            
            # Add cookies if available
            if platform and platform['cookies_file'] and os.path.exists(platform['cookies_file']):
                ydl_opts['cookiefile'] = platform['cookies_file']
            
            # Download the video
            downloaded_file = None
            video_info = None
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_info = {
                    'title': info.get('title', 'Video'),
                    'duration': info.get('duration', 0),
                    'width': info.get('width', 0),
                    'height': info.get('height', 0),
                }
                downloaded_file = ydl.prepare_filename(info)
            
            # Check if file exists
            if not os.path.exists(downloaded_file):
                await status_msg.edit("❌ Download failed. Please try again or check the URL.")
                return
            
            # Check file size
            file_size = os.path.getsize(downloaded_file)
            if file_size > MAX_FILE_SIZE:
                os.remove(downloaded_file)
                await status_msg.edit(
                    f"❌ Video is too large ({file_size / 1024 / 1024:.1f}MB)\n"
                    f"Maximum size: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
                )
                return
            
            # Update status
            await status_msg.edit(
                f"✅ Downloaded! ({file_size / 1024 / 1024:.1f}MB)\n"
                f"📤 Uploading to Telegram..."
            )
            
            # Send the video
            await self.client.send_file(
                event.chat_id,
                downloaded_file,
                caption=f"🎬 **{video_info['title']}**",
                supports_streaming=True,
                attributes=[
                    DocumentAttributeVideo(
                        duration=int(video_info['duration']),
                        w=video_info['width'],
                        h=video_info['height'],
                        supports_streaming=True
                    )
                ]
            )
            
            # Delete status message and downloaded file
            await status_msg.delete()
            os.remove(downloaded_file)
            
            print(f"✅ Sent video to user {event.chat_id}: {video_info['title']}")
        
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error: {error_msg}")
            await status_msg.edit(
                f"❌ Error downloading video:\n`{error_msg[:200]}`\n\n"
                "Please check the URL and try again."
            )
            
            # Clean up any downloaded file
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                except:
                    pass
    
    async def start(self):
        """Start the bot"""
        print("🤖 Starting Video Downloader Bot...")
        print("=" * 60)
        
        # Start the client
        await self.client.start(bot_token=BOT_TOKEN)
        
        # Get bot info
        me = await self.client.get_me()
        print(f"✅ Bot started successfully!")
        print(f"📱 Username: @{me.username}")
        print(f"🆔 Bot ID: {me.id}")
        print("=" * 60)
        print("🎬 Bot is now running and ready to download videos!")
        print("Press Ctrl+C to stop the bot")
        print("=" * 60)
        
        # Run until disconnected
        await self.client.run_until_disconnected()
    
    def run(self):
        """Run the bot (blocking)"""
        with self.client:
            self.client.loop.run_until_complete(self.start())


def main():
    """Main entry point"""
    try:
        bot = VideoDownloaderBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you have set up your .env file with:")
        print("  - TELEGRAM_API_ID")
        print("  - TELEGRAM_API_HASH")
        print("  - TELEGRAM_BOT_TOKEN")


if __name__ == "__main__":
    main()
