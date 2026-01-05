#!/usr/bin/env python3
"""
Simple Video Downloader CLI
Download videos from TikTok, Instagram, Facebook, YouTube and more using yt-dlp
"""
import sys
from downloader import VideoDownloader


def print_banner():
    """Print application banner"""
    banner = """
╔══════════════════════════════════════════════════════╗
║          📹 Video Downloader using yt-dlp           ║
║     Supports: TikTok, Instagram, Facebook & more    ║
╚══════════════════════════════════════════════════════╝
    """
    print(banner)


def print_usage():
    """Print usage instructions"""
    print("\nUsage:")
    print("  python main.py <video_url>              # Download a video")
    print("  python main.py --info <video_url>       # Get video info without downloading")
    print("  python main.py --platforms              # List all supported platforms")
    print("\nExamples:")
    print("  python main.py https://www.tiktok.com/@user/video/123456789")
    print("  python main.py https://www.instagram.com/reel/abc123")
    print("  python main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    print()


def main():
    """Main entry point"""
    print_banner()
    
    # Initialize downloader
    downloader = VideoDownloader()
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("❌ No URL provided!")
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1]
    
    # Handle different commands
    if command == "--platforms" or command == "-p":
        downloader.list_platforms()
        return
    
    elif command == "--info" or command == "-i":
        if len(sys.argv) < 3:
            print("❌ No URL provided for info command!")
            print_usage()
            sys.exit(1)
        
        url = sys.argv[2]
        print(f"\n🔍 Fetching video information...")
        info = downloader.get_video_info(url)
        
        if info:
            print("\n" + "=" * 50)
            print(f"Title:      {info['title']}")
            print(f"Platform:   {info['platform']}")
            print(f"Uploader:   {info['uploader']}")
            print(f"Duration:   {info['duration']} seconds")
            print(f"Views:      {info['view_count']:,}")
            print("=" * 50 + "\n")
        else:
            print("❌ Failed to retrieve video information")
            sys.exit(1)
    
    elif command == "--help" or command == "-h":
        print_usage()
        return
    
    else:
        # Treat as URL for download
        url = command
        
        # Validate URL
        if not url.startswith('http'):
            print(f"❌ Invalid URL: {url}")
            print("   URL must start with http:// or https://")
            sys.exit(1)
        
        # Download the video
        print(f"\n{'=' * 60}")
        success = downloader.download(url)
        print(f"{'=' * 60}\n")
        
        if success:
            print("🎉 Download completed successfully!")
            print(f"📁 Videos are saved in the 'downloads' folder\n")
        else:
            print("❌ Download failed. Please check the URL and try again.\n")
            sys.exit(1)


if __name__ == "__main__":
    main()
