import logging
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from functools import wraps
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("telegram_bot")

async def is_user_admin(update: Update) -> bool:
    """Check if the user is an admin in the chat."""
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # For private chats, consider the user as admin
        if update.effective_chat.type == "private":
            logger.debug(f"User {user_id} automatically admin in private chat")
            return True
            
        # Get chat administrators
        chat_admins = await update.effective_chat.get_administrators()
        admin_ids = [admin.user.id for admin in chat_admins]
        
        is_admin = user_id in admin_ids
        logger.debug(f"Admin check for user {user_id} in chat {chat_id}: {is_admin}")
        logger.debug(f"Admin IDs in chat: {admin_ids}")
        
        return is_admin
    except Exception as e:
        logger.error(f"Error checking admin status: {str(e)}")
        # Default to not admin if there's an error
        return False


def admin_only(func):
    """Decorator to restrict commands to admins only."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            if not await is_user_admin(update):
                logger.warning(f"Unauthorized access attempt by user {update.effective_user.id} in chat {update.effective_chat.id}")
                await update.message.reply_text("⚠️ This command is restricted to admins only.")
                return
            logger.info(f"Admin access granted to user {update.effective_user.id} in chat {update.effective_chat.id}")
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in admin_only wrapper: {str(e)}")
            await update.message.reply_text("An error occurred while checking permissions.")
    return wrapped


@admin_only
async def enable_janitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable the janitor feature in this chat."""
    context.chat_data["janitorEnabled"] = True
    
    await update.message.reply_text("Janitor has been enabled for this chat!")
    logger.info(f"Janitor enabled in chat {update.effective_chat.id}")


@admin_only
async def disable_janitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable the janitor feature in this chat."""
    context.chat_data["janitorEnabled"] = False
    
    await update.message.reply_text("Janitor has been disabled for this chat!")
    logger.info(f"Janitor disabled in chat {update.effective_chat.id}")


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the current settings."""
    janitor_status = context.chat_data.get("janitorEnabled", False)
    channel_filter_status = context.chat_data.get("channelFilterEnabled", False)
    fsp_status = context.chat_data.get("forwardSpamProtectionEnabled", False)
    
    # Count filter patterns
    filter_count = 0
    if "filter_patterns" in context.chat_data and context.chat_data["filter_patterns"]:
        filter_count = len(context.chat_data["filter_patterns"])
    
    janitor_text = "enabled" if janitor_status else "disabled"
    channel_filter_text = "enabled" if channel_filter_status else "disabled"
    fsp_text = "enabled" if fsp_status else "disabled"
    
    status_text = f"""
*Current settings for this chat:*

🧹 *Janitor:* {janitor_text}
📺 *Channel Filter:* {channel_filter_text}
🔁 *Forward Spam Protection:* {fsp_text}
🔍 *Active Filters:* {filter_count} pattern(s)

*Available Commands:*
• `/enable_janitor` / `/disable_janitor` - Toggle message filtering
• `/toggle_channel_filter` - Toggle external channel message filtering
• `/toggle_forward_spam` - Toggle forward spam protection (delete repeated forwards within 24h)
• `/add_filter <pattern>` - Add regex filter
• `/remove_filter <number>` - Remove filter
• `/list_filters` - Show all filters
    """
    
    await update.message.reply_text(status_text, parse_mode="Markdown")
    logger.info(f"Settings displayed for chat {update.effective_chat.id}")


@admin_only
async def toggle_forward_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle forward spam protection for the chat."""
    current_state = context.chat_data.get("forwardSpamProtectionEnabled", False)
    new_state = not current_state
    context.chat_data["forwardSpamProtectionEnabled"] = new_state

    # Ensure data is marked for persistence
    await context.application.update_persistence()

    status = "enabled" if new_state else "disabled"
    emoji = "✅" if new_state else "❌"

    await update.message.reply_text(
        f"{emoji} Forward spam protection has been {status}.\n\n"
        f"When enabled, any specific forwarded message repeated within 24 hours will be deleted."
    )

    logger.info(
        f"Forward spam protection {status} in chat {update.effective_chat.id} by user {update.effective_user.id}"
    )


def _cleanup_fsp_cache(cache: dict) -> None:
    """Remove cache entries older than 24 hours."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    stale_keys = [key for key, first_seen in cache.items() if first_seen < cutoff]
    for key in stale_keys:
        del cache[key]


def _make_forward_key(message) -> str | None:
    """Create a stable key representing the original forwarded message.

    Combines multiple signals for robust identification.
    Returns None if a safe key cannot be determined.
    """
    # Channel post forwards: best signal - has actual message ID
    # Support both old API (forward_from_chat) and new API (forward_origin)
    if getattr(message, "forward_from_chat", None) and getattr(message, "forward_from_message_id", None):
        origin_chat_id = message.forward_from_chat.id
        origin_msg_id = message.forward_from_message_id
        return f"chat:{origin_chat_id}:msg:{origin_msg_id}"
    
    # New API: Check forward_origin for channel
    if getattr(message, "forward_origin", None):
        origin = message.forward_origin
        # MessageOriginChannel
        if hasattr(origin, "chat") and hasattr(origin, "message_id"):
            return f"chat:{origin.chat.id}:msg:{origin.message_id}"
        # MessageOriginUser
        elif hasattr(origin, "sender_user"):
            origin_user_id = origin.sender_user.id
            key_parts = [f"user:{origin_user_id}"]
            
            # Add forward date as additional discriminator
            if hasattr(origin, "date"):
                key_parts.append(f"date:{int(origin.date.timestamp())}")
            
            # Add text/caption content if available
            content = (message.text or message.caption or "").strip()
            if content:
                key_parts.append(f"text:{hash(content)}")
            
            # Add media file_unique_id for different media types
            media_id = None
            if getattr(message, "photo", None) and message.photo:
                media_id = f"photo:{message.photo[-1].file_unique_id}"
            elif getattr(message, "document", None):
                media_id = f"doc:{message.document.file_unique_id}"
            elif getattr(message, "video", None):
                media_id = f"video:{message.video.file_unique_id}"
            elif getattr(message, "audio", None):
                media_id = f"audio:{message.audio.file_unique_id}"
            elif getattr(message, "voice", None):
                media_id = f"voice:{message.voice.file_unique_id}"
            elif getattr(message, "sticker", None):
                media_id = f"sticker:{message.sticker.file_unique_id}"
            elif getattr(message, "animation", None):
                media_id = f"animation:{message.animation.file_unique_id}"
            elif getattr(message, "video_note", None):
                media_id = f"videonote:{message.video_note.file_unique_id}"
            
            if media_id:
                key_parts.append(media_id)
            
            # Only create key if we have date and (content or media)
            if len(key_parts) >= 2:
                return ":".join(key_parts)

    # Old API: User forwards
    if getattr(message, "forward_from", None):
        origin_user_id = message.forward_from.id
        key_parts = [f"user:{origin_user_id}"]
        
        # Add text/caption content if available
        content = (message.text or message.caption or "").strip()
        if content:
            key_parts.append(f"text:{hash(content)}")
        
        # Add media file_unique_id for different media types
        media_id = None
        if getattr(message, "photo", None) and message.photo:
            media_id = f"photo:{message.photo[-1].file_unique_id}"
        elif getattr(message, "document", None):
            media_id = f"doc:{message.document.file_unique_id}"
        elif getattr(message, "video", None):
            media_id = f"video:{message.video.file_unique_id}"
        elif getattr(message, "audio", None):
            media_id = f"audio:{message.audio.file_unique_id}"
        elif getattr(message, "voice", None):
            media_id = f"voice:{message.voice.file_unique_id}"
        elif getattr(message, "sticker", None):
            media_id = f"sticker:{message.sticker.file_unique_id}"
        elif getattr(message, "animation", None):
            media_id = f"animation:{message.animation.file_unique_id}"
        elif getattr(message, "video_note", None):
            media_id = f"videonote:{message.video_note.file_unique_id}"
        
        if media_id:
            key_parts.append(media_id)
        
        # Only create key if we have content or media
        if len(key_parts) > 1:
            return ":".join(key_parts)

    # Anonymous/hidden sender name forwards or cases with no reliable key
    return None


async def handle_forward_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete forwarded messages repeated within 24 hours when protection is enabled."""
    try:
        if not context.chat_data.get("forwardSpamProtectionEnabled", False):
            return

        message = update.effective_message
        if not message:
            return

        # Skip automatic forwards from linked channels
        if getattr(message, "is_automatic_forward", False) is True:
            logger.info(f"FSP: Skipping automatic forward in chat {update.effective_chat.id}")
            return

        # Skip forwards from Telegram service (777000) - linked channel posts
        if getattr(message, "forward_from", None) and message.forward_from.id == 777000:
            logger.info(f"FSP: Skipping linked channel post (777000) in chat {update.effective_chat.id}")
            return

        # Prepare cache in chat_data
        cache: dict = context.chat_data.setdefault("fsp_cache", {})
        _cleanup_fsp_cache(cache)

        key = _make_forward_key(message)
        if key is None:
            return  # Cannot safely identify origin; skip

        now = datetime.now(timezone.utc)
        first_seen: datetime | None = cache.get(key)

        if first_seen is None:
            cache[key] = now
            # Optionally persist
            await context.application.update_persistence()
            logger.info(f"FSP: Tracking new forward key={key} in chat {update.effective_chat.id} from user {update.effective_user.id}")
            return

        # If seen before within 24 hours, delete this message
        if now - first_seen <= timedelta(hours=24):
            try:
                delta = now - first_seen
                logger.info(
                    f"FSP trigger: user={update.effective_user.id} chat={update.effective_chat.id} "
                    f"key={key} first_seen={first_seen.isoformat()} now={now.isoformat()} "
                    f"delta_seconds={int(delta.total_seconds())}"
                )
                await message.delete()
                logger.info(
                    f"FSP: Deleted repeated forward key {key} in chat {update.effective_chat.id}"
                )

                # Notify and auto-delete the notice after 6 seconds
                user = update.effective_user
                who = (
                    f"@{user.username}" if getattr(user, "username", None) else str(user.id)
                )
                # Compute remaining time until 24h window expires
                remaining = timedelta(hours=24) - delta
                if remaining.total_seconds() < 0:
                    remaining = timedelta(seconds=0)
                total_secs = int(remaining.total_seconds())
                hours, rem = divmod(total_secs, 3600)
                minutes, seconds = divmod(rem, 60)
                parts = []
                if hours > 0:
                    parts.append(f"{hours}h")
                if minutes > 0 or hours > 0:
                    parts.append(f"{minutes}m")
                parts.append(f"{seconds}s")
                remaining_str = " ".join(parts)
                notice = await update.effective_chat.send_message(
                    f"🧹 Removed repeated forwarded message from {who} (within 24h). "
                    f"Try again in {remaining_str}."
                )

                if context.job_queue:
                    context.job_queue.run_once(
                        _delete_message_job,
                        when=6,
                        data={"chat_id": notice.chat_id, "message_id": notice.message_id},
                    )
            except Exception as del_err:
                logger.error(f"FSP: Failed to delete message: {del_err}")
        else:
            # Older than 24h: reset the window to now
            cache[key] = now
            await context.application.update_persistence()
            logger.info(f"FSP: Reset tracking for forward key={key} in chat {update.effective_chat.id} from user {update.effective_user.id} (previous: {first_seen.isoformat()})")
    except Exception as e:
        logger.error(f"Error in handle_forward_spam: {e}")


async def _delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue task to delete a specific message (bot's notice)."""
    try:
        job = context.job  # type: ignore[attr-defined]
        data = getattr(job, "data", {}) or {}
        chat_id = data.get("chat_id")
        message_id = data.get("message_id")
        if chat_id and message_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"FSP: Failed to auto-delete notice message: {e}")

async def check_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug command to check if a user is an admin, using the best available display name."""
    try:
        user = update.effective_user
        
        who = (
            f"@{user.username}"
            if user.username
            else (str(user.id))
        )

        is_admin = await is_user_admin(update)

        if is_admin:
            await update.message.reply_text(f"✅ {who} is an admin in this chat.")
        else:
            await update.message.reply_text(f"❌ {who} is NOT an admin in this chat.")

        logger.info(f"Admin status check: {who} ({user.id}) in chat {update.effective_chat.id} is admin: {is_admin}")
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await update.message.reply_text("Error checking admin status.")



async def check_all_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug command to check all permissions for the bot in the current chat."""
    try:
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        bot_id = context.bot.id
        
        # For private chats, bot has all permissions
        if chat_type == "private":
            await update.message.reply_text(
                "✅ *Private Chat - Bot has all permissions*\n\n"
                "In private chats, the bot can perform all actions.",
                parse_mode="Markdown"
            )
            logger.info(f"Bot permission check: Bot {bot_id} in private chat - all permissions granted")
            return
        
        # Get bot's member info in the chat
        try:
            bot_member = await update.effective_chat.get_member(bot_id)
            status = bot_member.status
            
            # Build permission report for the bot
            permission_text = f"*Bot Permission Report*\n\n"
            permission_text += f"**Chat:** {update.effective_chat.title or 'Unknown'}\n"
            permission_text += f"**Chat Type:** {chat_type}\n"
            permission_text += f"**Bot Status:** {status}\n"
            permission_text += f"**Bot ID:** {bot_id}\n\n"
            
            if status == "administrator":
                # Check specific admin permissions for the bot
                bot_perms = []
                
                # Critical permissions for bot functionality
                if hasattr(bot_member, 'can_delete_messages') and bot_member.can_delete_messages:
                    bot_perms.append("✅ Can delete messages")
                else:
                    bot_perms.append("❌ **Cannot delete messages** (CRITICAL)")
                
                if hasattr(bot_member, 'can_restrict_members') and bot_member.can_restrict_members:
                    bot_perms.append("✅ Can restrict members")
                else:
                    bot_perms.append("❌ Cannot restrict members")
                
                if hasattr(bot_member, 'can_change_info') and bot_member.can_change_info:
                    bot_perms.append("✅ Can change chat info")
                else:
                    bot_perms.append("❌ Cannot change chat info")
                
                if hasattr(bot_member, 'can_invite_users') and bot_member.can_invite_users:
                    bot_perms.append("✅ Can invite users")
                else:
                    bot_perms.append("❌ Cannot invite users")
                
                if hasattr(bot_member, 'can_pin_messages') and bot_member.can_pin_messages:
                    bot_perms.append("✅ Can pin messages")
                else:
                    bot_perms.append("❌ Cannot pin messages")
                
                if hasattr(bot_member, 'can_manage_chat') and bot_member.can_manage_chat:
                    bot_perms.append("✅ Can manage chat")
                else:
                    bot_perms.append("❌ Cannot manage chat")
                
                if hasattr(bot_member, 'can_manage_video_chats') and bot_member.can_manage_video_chats:
                    bot_perms.append("✅ Can manage video chats")
                else:
                    bot_perms.append("❌ Cannot manage video chats")
                
                permission_text += "🤖 **BOT IS ADMINISTRATOR**\n\n"
                permission_text += "**Bot Permissions:**\n"
                permission_text += "\n".join(bot_perms)
                
                # Check if bot can perform its core functions
                can_delete = hasattr(bot_member, 'can_delete_messages') and bot_member.can_delete_messages
                
                permission_text += "\n\n**Bot Functionality Status:**\n"
                if can_delete:
                    permission_text += "✅ Message filtering will work\n"
                    permission_text += "✅ Channel filtering will work\n"
                    permission_text += "✅ Janitor mode will work"
                else:
                    permission_text += "❌ **Message filtering will NOT work**\n"
                    permission_text += "❌ **Channel filtering will NOT work**\n"
                    permission_text += "❌ **Janitor mode will NOT work**\n\n"
                    permission_text += "⚠️ **Bot needs 'Delete Messages' permission to function properly!**"
                
            elif status == "member":
                permission_text += "👤 **BOT IS REGULAR MEMBER**\n\n"
                permission_text += "❌ **Bot has NO admin permissions**\n"
                permission_text += "❌ **Cannot delete messages**\n"
                permission_text += "❌ **Message filtering will NOT work**\n"
                permission_text += "❌ **Channel filtering will NOT work**\n"
                permission_text += "❌ **Janitor mode will NOT work**\n\n"
                permission_text += "⚠️ **Bot needs to be promoted to administrator with 'Delete Messages' permission!**"
                
            elif status == "restricted":
                permission_text += "🚫 **BOT IS RESTRICTED**\n\n"
                permission_text += "❌ **Bot has restricted permissions**\n"
                permission_text += "❌ **Most bot functions will NOT work**"
                
            elif status == "left":
                permission_text += "👻 **BOT HAS LEFT THE CHAT**\n\n"
                permission_text += "❌ **Bot is not in this chat**"
                
            elif status == "kicked":
                permission_text += "🚫 **BOT IS BANNED**\n\n"
                permission_text += "❌ **Bot has been kicked from this chat**"
            
            await update.message.reply_text(permission_text, parse_mode="Markdown")
            logger.info(f"Bot permission check completed for chat {chat_id}: status={status}")
            
        except Exception as member_error:
            logger.error(f"Error getting bot member info: {member_error}")
            await update.message.reply_text(
                f"❌ **Error checking bot permissions**\n\n"
                f"Could not retrieve bot member information.\n"
                f"Error: {str(member_error)}",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error in check_all_permissions: {str(e)}")
        await update.message.reply_text("❌ Error checking bot permissions.")


def register_conversation_handlers(application):
    """Register command handlers with the application."""
    # Add command handlers
    application.add_handler(CommandHandler("enable_janitor", enable_janitor))
    application.add_handler(CommandHandler("disable_janitor", disable_janitor))
    application.add_handler(CommandHandler("status", show_settings))
    application.add_handler(CommandHandler("amiadmin", check_admin_status))
    application.add_handler(CommandHandler("botperms", check_all_permissions))
    application.add_handler(CommandHandler("toggle_forward_spam", toggle_forward_spam))
    # Message handler to enforce forward spam protection
    application.add_handler(MessageHandler(filters.FORWARDED & (~filters.StatusUpdate.ALL), handle_forward_spam))
    
    logger.info("Settings handlers registered") 
