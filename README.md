# Instagram Telegram Downloader Bot

[فارسی](#فارسی) | [English](#english)

## فارسی

یک بات تلگرام برای دریافت لینک عمومی اینستاگرام و ارسال عکس، ویدیو و کپشن در چت خصوصی. این پروژه از پست، ریل و IGTV عمومی پشتیبانی می‌کند و هیچ نام کاربری، رمز عبور، cookie یا session اینستاگرامی دریافت یا ذخیره نمی‌کند.

### امکانات

- دانلود عکس و ویدیو از پست‌ها و ریل‌های عمومی
- پشتیبانی از پست‌های چنداسلایدی
- ارسال کپشن اصلی همراه مدیا
- تقسیم آلبوم‌های بزرگ به گروه‌های حداکثر ۱۰تایی
- فعالیت فقط در private chat
- امکان محدودکردن کاربران با Telegram User ID
- پاک‌سازی خودکار فایل‌های موقت
- استفاده از Instaloader به‌عنوان دانلودر اصلی
- استفاده خودکار از yt-dlp و OGInstagram هنگام محدودشدن دانلودر اصلی

### راه‌اندازی در ویندوز

1. Python 3.11 یا جدیدتر را نصب کنید.
2. در `@BotFather` یک بات بسازید و توکن آن را بگیرید.
3. PowerShell را در پوشه پروژه باز کرده و اجرا کنید:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --upgrade -r requirements.txt
Copy-Item .env.example .env
```

4. فایل `.env` را باز کنید و توکن جدید بات را قرار دهید:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_NEW_BOT_TOKEN
```

5. بات را اجرا کنید:

```powershell
python bot.py
```

### تنظیمات `.env`

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_NEW_BOT_TOKEN

# خالی یعنی همه کاربران اجازه دارند.
# نمونه: 123456789,987654321
ALLOWED_USER_IDS=

# حداکثر حجم فایل برای ارسال با Bot API
MAX_UPLOAD_MB=49
LOG_LEVEL=INFO
```

### نکات و محدودیت‌ها

- بات پیام‌های گروه و کانال را نادیده می‌گیرد و فقط در چت خصوصی کار می‌کند.
- استوری، هایلایت و محتوای private پشتیبانی نمی‌شوند؛ این موارد به ورود اینستاگرام نیاز دارند.
- دسترسی ناشناس به اینستاگرام تضمینی نیست. هنگام خطای 401 یا 403، بات دو مسیر جایگزین را خودکار امتحان می‌کند.
- در آخرین fallback فقط URL عمومی پست برای `oginstagram.com` ارسال می‌شود؛ توکن تلگرام و اطلاعات کاربر ارسال نمی‌شوند.
- اگر هر سه مسیر محدود باشند، بعداً یا با اینترنت/IP دیگری دوباره امتحان کنید.
- توکن بات را در پیام، تصویر یا لاگ عمومی منتشر نکنید. اگر منتشر شد، فوراً با `/revoke` در BotFather آن را عوض کنید.
- فقط محتوایی را دانلود یا بازنشر کنید که اجازه استفاده از آن را دارید.

### خطاهای متداول

- `Media not found or temporarily unavailable`: محتوا ممکن است حذف‌شده، private، محدودشده یا موقتاً خارج از دسترس باشد. بعداً دوباره امتحان کنید.
- `A network error occurred`: اتصال اینترنت و دسترسی به Telegram Bot API را بررسی کنید.
- خطای نصب پکیج‌ها: ابتدا `python -m pip install --upgrade pip` و سپس نصب requirements را دوباره اجرا کنید.

---

## English

A Telegram bot that accepts public Instagram links and sends the available photos, videos, and original captions in private chat. It supports public posts, Reels, and IGTV without collecting or storing an Instagram username, password, cookie, or session.

### Features

- Downloads photos and videos from public posts and Reels
- Supports multi-item carousel posts
- Sends the original caption with the media
- Splits large albums into groups of up to 10 items
- Works only in private chats
- Optional access restriction using Telegram User IDs
- Automatically removes temporary files
- Uses Instaloader as the primary downloader
- Automatically falls back to yt-dlp and OGInstagram when the primary method is blocked

### Windows setup

1. Install Python 3.11 or newer.
2. Create a bot with `@BotFather` and copy its token.
3. Open PowerShell in the project directory and run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --upgrade -r requirements.txt
Copy-Item .env.example .env
```

4. Open `.env` and set your new bot token:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_NEW_BOT_TOKEN
```

5. Start the bot:

```powershell
python bot.py
```

### `.env` configuration

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_NEW_BOT_TOKEN

# Leave empty to allow everyone.
# Example: 123456789,987654321
ALLOWED_USER_IDS=

# Maximum file size sent through the standard Bot API
MAX_UPLOAD_MB=49
LOG_LEVEL=INFO
```

### Notes and limitations

- Group and channel messages are ignored; the bot works only in private chats.
- Stories, Highlights, and private content are not supported because they require Instagram authentication.
- Anonymous Instagram access is not guaranteed. When Instagram returns 401 or 403, the bot automatically tries two fallback methods.
- The final fallback sends only the public post URL to `oginstagram.com`; Telegram tokens and user information are not shared.
- If all three methods are blocked, try again later or use a different internet connection/IP.
- Never publish the bot token in messages, screenshots, or public logs. If exposed, immediately replace it with `/revoke` in BotFather.
- Download or redistribute only content you are authorized to use.

### Common errors

- `Media not found or temporarily unavailable`: The content may be deleted, private, restricted, or temporarily unavailable. Try again later.
- `A network error occurred`: Check the internet connection and access to the Telegram Bot API.
- Package installation errors: Run `python -m pip install --upgrade pip`, then install the requirements again.
