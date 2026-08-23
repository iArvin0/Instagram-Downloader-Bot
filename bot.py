from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import instaloader
import requests
import yt_dlp
from dotenv import load_dotenv
from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("instagram_bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/[^\s?#]+(?:\?[^\s]*)?",
    re.IGNORECASE,
)
POST_PATH_RE = re.compile(r"^/(?:p|reel|reels|tv)/([\w-]+)", re.IGNORECASE)
MAX_CAPTION = 1024
MAX_BOT_FILE = int(os.getenv("MAX_UPLOAD_MB", "49")) * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm"}
ALLOWED_USERS = {
    int(value.strip())
    for value in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if value.strip().isdigit()
}


@dataclass(slots=True)
class DownloadResult:
    files: list[Path]
    caption: str
    source_url: str


class OpenGraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attributes = {key.lower(): value or "" for key, value in attrs}
        key = (attributes.get("property") or attributes.get("name") or "").lower()
        content = html.unescape(attributes.get("content", "")).strip()
        if key and content:
            self.values.setdefault(key, []).append(content)


class InstagramDownloader:
    def __init__(self) -> None:
        self._instaloader_blocked_until = 0.0
        self.loader = instaloader.Instaloader(
            dirname_pattern="{target}",
            filename_pattern="{date_utc:%Y%m%d_%H%M%S}_{shortcode}",
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            storyitem_metadata_txt_pattern="",
            max_connection_attempts=1,
            request_timeout=30,
            quiet=True,
        )

    def download(self, url: str, directory: Path) -> DownloadResult:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") + "/"
        post_match = POST_PATH_RE.match(path)
        if post_match:
            if time.monotonic() >= self._instaloader_blocked_until:
                try:
                    return self._download_post(post_match.group(1), url, directory)
                except instaloader.InstaloaderException as exc:
                    self._instaloader_blocked_until = time.monotonic() + 15 * 60
                    logger.warning("Instaloader was blocked; trying anonymous fallback: %s", exc)
            return self._download_with_ytdlp(url, directory)
        raise ValueError("This Instagram link type is not supported.")

    def _download_post(self, shortcode: str, url: str, directory: Path) -> DownloadResult:
        post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
        sources: list[tuple[str, str]] = []
        if post.typename == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                media_url = node.video_url if node.is_video else node.display_url
                if media_url:
                    sources.append((media_url, ".mp4" if node.is_video else ".jpg"))
        elif post.is_video:
            if post.video_url:
                sources.append((post.video_url, ".mp4"))
        else:
            sources.append((post.url, ".jpg"))

        if not sources:
            raise LookupError("Media not found or temporarily unavailable. Please try again later.")

        files: list[Path] = []
        for index, (media_url, suffix) in enumerate(sources, start=1):
            destination = directory / f"{index:02d}{suffix}"
            self.loader.context.get_and_write_raw(media_url, str(destination))
            if destination.is_file() and destination.stat().st_size > 0:
                files.append(destination)

        logger.info("Downloaded %d/%d media files for %s", len(files), len(sources), shortcode)
        if not files:
            raise LookupError("Media not found or temporarily unavailable. Please try again later.")
        caption = post.caption or ""
        return DownloadResult(files, caption, url)

    @staticmethod
    def _download_with_ytdlp(url: str, directory: Path) -> DownloadResult:
        options = {
            "outtmpl": str(directory / "fallback_%(autonumber)02d_%(id)s.%(ext)s"),
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "nopart": True,
            "overwrites": True,
            "retries": 2,
            "socket_timeout": 30,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            logger.warning("Anonymous yt-dlp fallback failed: %s", exc)
            try:
                return InstagramDownloader._download_with_embed_service(url, directory)
            except (LookupError, requests.RequestException, OSError) as embed_exc:
                logger.warning("Public embed fallback failed: %s", embed_exc)
                raise LookupError(
                    "Media not found or temporarily unavailable. Please try again later."
                ) from embed_exc

        files = sorted(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".mp4", ".m4v", ".mov", ".webm", ".jpg", ".jpeg", ".png"}
            and path.stat().st_size > 0
        )
        if not files:
            raise LookupError("Media not found or temporarily unavailable. Please try again later.")

        caption = ""
        if isinstance(info, dict):
            caption = str(info.get("description") or info.get("title") or "")
        logger.info("Anonymous fallback downloaded %d media file(s)", len(files))
        return DownloadResult(files, caption, url)

    @staticmethod
    def _download_with_embed_service(url: str, directory: Path) -> DownloadResult:
        parsed_url = urlparse(url)
        service_url = f"https://oginstagram.com{parsed_url.path}"
        headers = {
            "User-Agent": "TelegramBot (compatible; InstagramMediaDownloader/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        page = requests.get(service_url, headers=headers, timeout=(15, 45))
        page.raise_for_status()

        parser = OpenGraphParser()
        parser.feed(page.text)
        video_urls = InstagramDownloader._unique_meta_values(
            parser, "og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"
        )
        image_urls = InstagramDownloader._unique_meta_values(
            parser, "og:image", "og:image:url", "og:image:secure_url", "twitter:image"
        )
        media_urls = video_urls or image_urls
        if not media_urls:
            raise LookupError("Media not found or temporarily unavailable. Please try again later.")

        files: list[Path] = []
        for index, media_url in enumerate(media_urls[:10], start=1):
            InstagramDownloader._validate_public_media_url(media_url)
            media = requests.get(media_url, headers=headers, stream=True, timeout=(15, 120))
            media.raise_for_status()
            InstagramDownloader._validate_public_media_url(str(media.url))
            content_type = media.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type.startswith("video/"):
                suffix = ".mp4"
            elif content_type == "image/png":
                suffix = ".png"
            elif content_type.startswith("image/"):
                suffix = ".jpg"
            else:
                raise LookupError("The downloaded media format is not supported.")
            destination = directory / f"embed_{index:02d}{suffix}"
            with destination.open("wb") as output:
                for chunk in media.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        output.write(chunk)
            if destination.stat().st_size > 0:
                files.append(destination)

        if not files:
            raise LookupError("Media not found or temporarily unavailable. Please try again later.")
        caption_values = InstagramDownloader._unique_meta_values(parser, "og:description")
        caption = caption_values[0] if caption_values else ""
        logger.info("Public embed fallback downloaded %d media file(s)", len(files))
        return DownloadResult(files, caption, url)

    @staticmethod
    def _unique_meta_values(parser: OpenGraphParser, *keys: str) -> list[str]:
        values: list[str] = []
        for key in keys:
            for value in parser.values.get(key, []):
                if value not in values:
                    values.append(value)
        return values

    @staticmethod
    def _validate_public_media_url(url: str) -> None:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        allowed_hosts = (
            "oginstagram.com",
            "cdninstagram.com",
            "fbcdn.net",
            "fbsbx.com",
        )
        if parsed.scheme != "https" or not any(
            hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts
        ):
            raise LookupError("The media source returned an invalid URL.")


downloader: InstagramDownloader | None = None
download_lock = asyncio.Lock()


def authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and (not ALLOWED_USERS or user.id in ALLOWED_USERS))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
        return
    await update.message.reply_text(
        "👋 Welcome to Instagram Downloader!\n\n"
        "Send me a public Instagram post, Reel, or IGTV link. I’ll download the available "
        "photos or videos and send them here with the original caption.\n\n"
        "• Public content only\n"
        "• No Instagram login required\n"
        "• Works in private chat"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return
    if not authorized(update):
        await message.reply_text("You are not allowed to use this bot.")
        return

    match = INSTAGRAM_URL_RE.search(message.text)
    if not match:
        await message.reply_text("Please send a valid public Instagram post or Reel link.")
        return

    status = await message.reply_text("⏳ Downloading media…")
    temp_dir = Path(tempfile.mkdtemp(prefix="igbot_"))
    try:
        await context.bot.send_chat_action(message.chat_id, ChatAction.UPLOAD_DOCUMENT)
        if downloader is None:
            raise RuntimeError("The downloader is not ready.")
        async with download_lock:
            result = await asyncio.to_thread(downloader.download, match.group(0), temp_dir)
        await status.edit_text("📤 Uploading media…")
        await send_result(update, context, result)
        await status.delete()
    except (ValueError, LookupError, PermissionError) as exc:
        await status.edit_text(f"❌ {exc}")
    except (instaloader.InstaloaderException, BadRequest) as exc:
        logger.warning("Instagram/Telegram error: %s", exc)
        await status.edit_text("❌ Media not found or temporarily unavailable. Please try again later.")
    except (NetworkError, TimedOut):
        await status.edit_text("❌ A network error occurred. Please try again later.")
    except Exception:
        logger.exception("Unhandled download error")
        await status.edit_text("❌ Something went wrong. Please try again later.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def send_result(
    update: Update, context: ContextTypes.DEFAULT_TYPE, result: DownloadResult
) -> None:
    message = update.message
    assert message is not None
    valid = [path for path in result.files if path.stat().st_size <= MAX_BOT_FILE]
    skipped = len(result.files) - len(valid)
    if not valid:
        raise BadRequest("All downloaded files exceed the configured upload limit")

    caption = result.caption.strip()
    first_caption = caption[:MAX_CAPTION] if caption else None
    for offset in range(0, len(valid), 10):
        batch = valid[offset : offset + 10]
        if len(batch) == 1:
            path = batch[0]
            with path.open("rb") as media:
                if path.suffix.lower() in VIDEO_SUFFIXES:
                    await message.reply_video(media, caption=first_caption if offset == 0 else None)
                else:
                    await message.reply_photo(media, caption=first_caption if offset == 0 else None)
        else:
            handles = [path.open("rb") for path in batch]
            try:
                group = []
                for index, (path, handle) in enumerate(zip(batch, handles)):
                    kwargs = {"caption": first_caption} if offset == 0 and index == 0 and first_caption else {}
                    if path.suffix.lower() in VIDEO_SUFFIXES:
                        group.append(InputMediaVideo(handle, **kwargs))
                    else:
                        group.append(InputMediaPhoto(handle, **kwargs))
                await message.reply_media_group(group)
            finally:
                for handle in handles:
                    handle.close()

    if caption and len(caption) > MAX_CAPTION:
        for start in range(MAX_CAPTION, len(caption), 4000):
            await message.reply_text(caption[start : start + 4000])
    if skipped:
        await message.reply_text(
            f"⚠️ {skipped} file(s) could not be sent because they exceed the upload size limit."
        )


async def post_init(application: Application) -> None:
    global downloader
    downloader = await asyncio.to_thread(InstagramDownloader)
    logger.info("Bot initialized as @%s", (await application.bot.get_me()).username)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and set it.")
    application = Application.builder().token(token).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
