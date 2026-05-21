import asyncio
import io
import logging
import os

import requests
from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from handlers.conversation import admin_only

logger = logging.getLogger("telegram_bot")

SIGHTENGINE_URL = "https://api.sightengine.com/1.0/check.json"
SIGHTENGINE_MODEL = "nudity-2.1"
# Trigger kick if any of these classes from nudity-2.1 exceeds the threshold.
NSFW_CLASSES = ("sexual_activity", "sexual_display", "erotica")
NSFW_THRESHOLD = 0.6
KICK_MESSAGE = "👋 get properly dressed first"


def _sightengine_check(image_bytes: bytes) -> dict | None:
    """Synchronous Sightengine call. Returns parsed JSON or None on failure."""
    api_user = os.getenv("SIGHTENGINE_USER")
    api_secret = os.getenv("SIGHTENGINE_SECRET")
    if not api_user or not api_secret:
        logger.error("NSFW guard: SIGHTENGINE_USER / SIGHTENGINE_SECRET not configured")
        return None

    try:
        response = requests.post(
            SIGHTENGINE_URL,
            files={"media": ("avatar.jpg", image_bytes)},
            data={
                "models": SIGHTENGINE_MODEL,
                "api_user": api_user,
                "api_secret": api_secret,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"NSFW guard: Sightengine request failed: {e}")
        return None


def _is_nsfw(result: dict) -> tuple[bool, str]:
    """Return (is_nsfw, reason) from a Sightengine nudity-2.1 response."""
    nudity = result.get("nudity") or {}
    for cls in NSFW_CLASSES:
        score = nudity.get(cls)
        if isinstance(score, (int, float)) and score >= NSFW_THRESHOLD:
            return True, f"{cls}={score:.2f}"
    return False, ""


async def _fetch_avatar_bytes(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bytes | None:
    """Download the user's current profile photo. Returns None if they have none."""
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
    except Exception as e:
        logger.error(f"NSFW guard: get_user_profile_photos failed for {user_id}: {e}")
        return None

    if not photos.photos:
        return None

    # photos.photos[0] is a list of PhotoSize for the most recent photo, biggest last.
    biggest = photos.photos[0][-1]
    try:
        tg_file = await context.bot.get_file(biggest.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"NSFW guard: failed to download avatar for {user_id}: {e}")
        return None


@admin_only
async def toggle_nsfw_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle NSFW profile picture guard for the chat."""
    current_state = context.chat_data.get("nsfwGuardEnabled", False)
    new_state = not current_state
    context.chat_data["nsfwGuardEnabled"] = new_state

    await context.application.update_persistence()

    status = "enabled" if new_state else "disabled"
    emoji = "✅" if new_state else "❌"
    await update.message.reply_text(
        f"{emoji} NSFW profile picture guard has been {status}.\n\n"
        f"When enabled, new members whose profile picture is flagged as NSFW "
        f"will be kicked (they can rejoin once they change their picture)."
    )
    logger.info(
        f"NSFW guard {status} in chat {update.effective_chat.id} by user {update.effective_user.id}"
    )


async def check_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inspect new members' profile photos and kick those with NSFW avatars."""
    if not context.chat_data.get("nsfwGuardEnabled", False):
        return

    message = update.effective_message
    if not message or not message.new_chat_members:
        return

    chat = update.effective_chat
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        # Don't try to kick the bot itself if it was just added.
        if member.id == context.bot.id:
            continue

        image_bytes = await _fetch_avatar_bytes(context, member.id)
        if image_bytes is None:
            logger.info(
                f"NSFW guard: user {member.id} has no profile photo in chat {chat.id}, skipping"
            )
            continue

        result = await asyncio.to_thread(_sightengine_check, image_bytes)
        if result is None or result.get("status") != "success":
            logger.warning(
                f"NSFW guard: skipping user {member.id} in chat {chat.id} due to API failure"
            )
            continue

        is_nsfw, reason = _is_nsfw(result)
        logger.info(
            f"NSFW guard: user {member.id} in chat {chat.id} → nsfw={is_nsfw} {reason or ''}"
        )
        if not is_nsfw:
            continue

        try:
            await context.bot.ban_chat_member(chat.id, member.id)
            await context.bot.unban_chat_member(chat.id, member.id, only_if_banned=True)
            who = f"@{member.username}" if member.username else (member.first_name or str(member.id))
            await chat.send_message(f"{KICK_MESSAGE} — {who}")
            logger.info(
                f"NSFW guard: kicked user {member.id} from chat {chat.id} (reason: {reason})"
            )
        except (BadRequest, Forbidden) as e:
            logger.error(
                f"NSFW guard: failed to kick user {member.id} from chat {chat.id}: {e} "
                f"(bot likely lacks ban permission)"
            )
        except Exception as e:
            logger.error(f"NSFW guard: unexpected error kicking user {member.id}: {e}")


def register_nsfw_guard_handlers(application):
    """Register NSFW profile picture guard handlers."""
    application.add_handler(CommandHandler("toggle_nsfw_guard", toggle_nsfw_guard))
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_new_member)
    )
    logger.info("NSFW guard handlers registered")
