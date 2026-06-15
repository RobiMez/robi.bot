import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

logger = logging.getLogger("telegram_bot")

import yt_dlp
import re
import os
import uuid
from telegram.ext import MessageHandler, filters

INSTAGRAM_REEL_REGEX = r"(https?://(?:www\.)?instagram\.com/reel/[A-Za-z0-9_\-]+)/?"

async def download_instagram_reel(url: str) -> str:
    loop = asyncio.get_running_loop()

    def _download():
        unique_id = uuid.uuid4().hex[:8]

        # Base options
        ydl_opts = {
            "outtmpl": f"reel_{unique_id}.%(ext)s",
            "format": "mp4/best",
            "quiet": True,
        }

        # Use cookies if available
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
            logger.info("Using cookies.txt for Instagram download")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    return await loop.run_in_executor(None, _download)


async def handle_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    match = re.search(INSTAGRAM_REEL_REGEX, text)

    if match:
        reel_url = match.group(1)
        logger.info(f"User {update.effective_user.id} sent Instagram link: {reel_url}")

        status_msg = await update.message.reply_text("Downloading reel...")

        file_path = None
        try:
            file_path = await download_instagram_reel(reel_url)

            with open(file_path, "rb") as video_file:
                await update.message.reply_video(video=video_file)

            await status_msg.delete()

        except Exception as e:
            logger.error(f"Download failed: {e}")
            await status_msg.edit_text("❌ Failed to download reel.")
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError as err:
                    logger.warning(f"Could not delete file {file_path}: {err}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    await update.message.reply_text(f'Hello {user.first_name}! I : bot.')

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info(f"User {user.id} used hello command")
    await update.message.reply_text(f'Hello {user.first_name}!')


def register_basic_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("hello", hello))
    allowed_chats = filters.Chat(chat_id=[2229651996]) | filters.Chat(username=["cmsv3"])
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(INSTAGRAM_REEL_REGEX) & filters.ChatType.GROUPS & allowed_chats, handle_instagram))

    logger.info("Basic handlers registered")
