# 📹 Video Downloader

A simple video downloader using yt-dlp that supports multiple platforms including TikTok, Instagram, Facebook, and YouTube.

## 🚀 Features

- ✅ Download videos from multiple platforms
- 🤖 **Telegram Bot** - Send links, get videos!
- 🍪 Cookie-based authentication for private content
- 🎯 Automatic platform detection
- 📊 Video information extraction
- 🔧 Easily extensible for new platforms

## 📦 Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## 🎯 Usage

### Download a video
```bash
python main.py <video_url>
```

### Get video information (without downloading)
```bash
python main.py --info <video_url>
```

### List supported platforms
```bash
python main.py --platforms
```

## 🤖 Telegram Bot Usage

### Setup

1. **Get Telegram API credentials:**
   - Go to https://my.telegram.org/apps
   - Create an application and note down your `API_ID` and `API_HASH`

2. **Create a bot with BotFather:**
   - Open Telegram and search for [@BotFather](https://t.me/BotFather)
   - Send `/newbot` and follow the instructions
   - Save your `BOT_TOKEN`

3. **Configure the bot:**
   ```bash
   cp .env.example .env
   # Edit .env and add your credentials
   ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

### Using the Bot

1. Start a chat with your bot on Telegram
2. Send `/start` to see the welcome message
3. Send any video link (TikTok, Instagram, Facebook, YouTube, etc.)
4. Wait for the bot to download and send back the video!

**Bot Commands:**
- `/start` - Welcome message
- `/help` - Show help
- `/platforms` - List supported platforms

## 🔒 Proxy Configuration (Optional)

You can configure a proxy for downloading videos. This is useful for bypassing geographic restrictions or rate limits.

### Setup Proxy

1. **Edit your `.env` file** and add:
   ```bash
   PROXY_HOST=localhost
   PROXY_PORT=40000
   PROXY_TYPE=socks5  # or 'http'
   ```

2. **Supported proxy types:**
   - `socks5` - SOCKS5 proxy (recommended)
   - `http` - HTTP/HTTPS proxy

3. **To disable proxy:**
   - Leave `PROXY_HOST` or `PROXY_PORT` empty in `.env`
   - Or remove these lines entirely

### Example Configurations

**SOCKS5 Proxy (Local):**
```bash
PROXY_HOST=localhost
PROXY_PORT=40000
PROXY_TYPE=socks5
```

**HTTP Proxy (Remote):**
```bash
PROXY_HOST=proxy.example.com
PROXY_PORT=8080
PROXY_TYPE=http
```

**No Proxy (Default):**
```bash
# Leave empty or comment out
# PROXY_HOST=
# PROXY_PORT=
```

The proxy will be used for all downloads in both the CLI (`main.py`) and the Telegram bot (`bot.py`).

## 🍪 Adding Cookies for New Platforms

### For Instagram:
1. Export your Instagram cookies to `cookies/instagram.txt`
2. Update `config.py` and set `'enabled': True` for Instagram

### For Facebook:
1. Export your Facebook cookies to `cookies/facebook.txt`
2. Update `config.py` and set `'enabled': True` for Facebook

### How to export cookies:

You can use browser extensions like:
- **Chrome/Edge**: "Get cookies.txt LOCALLY" or "cookies.txt"
- **Firefox**: "cookies.txt"

Export cookies in Netscape format and save to the `cookies/` folder.

## 📁 Project Structure

```
videoloader/
├── main.py           # CLI entry point
├── bot.py            # Telegram bot
├── downloader.py     # Core download logic
├── config.py         # Platform configurations
├── bot_config.py     # Bot-specific configuration
├── requirements.txt  # Python dependencies
├── .env              # Bot credentials (you create this)
├── .env.example      # Example environment file
├── cookies/          # Cookie files for different platforms
│   ├── tiktok.txt
│   ├── instagram.txt
│   └── facebook.txt
└── downloads/        # Downloaded videos (created automatically)
```

## 🛠️ Supported Platforms

| Platform  | Status | Cookies Required |
|-----------|--------|------------------|
| TikTok    | ✅ Ready | Yes |
| Instagram | ✅ Ready | Yes |
| Facebook  | ✅ Ready | Yes |
| YouTube   | ✅ Ready | No |

## 📝 Examples

```bash
# Download from TikTok
python main.py https://www.tiktok.com/@user/video/123456789

# Download from YouTube
python main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Get info about a video
python main.py --info https://www.tiktok.com/@user/video/123456789
```

## 🔧 Customization

Edit `config.py` to:
- Add new platforms
- Change download location
- Modify video quality settings
- Add custom yt-dlp options

## ⚠️ Notes

- Downloaded videos are saved in the `downloads/` folder
- Make sure you have permission to download the videos
- Some platforms may require valid cookies for access to private or restricted content
