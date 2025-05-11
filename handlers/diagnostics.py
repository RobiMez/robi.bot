import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
import os

logger = logging.getLogger("telegram_bot")


ADMIN_USER_IDS = [352475318]

def is_admin(user_id):
    """Check if a user is authorized to use admin commands."""
    return user_id in ADMIN_USER_IDS

async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track chats the bot is added to."""
    chat = update.effective_chat
    
    # Initialize bot_data structure if not exists
    if "tracked_chats" not in context.bot_data:
        context.bot_data["tracked_chats"] = {}
    
    # Get member count safely
    member_count = "Unknown"
    try:
        # Only get member count for groups and supergroups
        if chat.type in ["group", "supergroup"]:
            # get_member_count() is a method that returns a coroutine
            # We need to await it to get the actual count
            member_count = await context.bot.get_chat_member_count(chat.id)
    except Exception as e:
        logger.error(f"Error getting member count for chat {chat.id}: {e}")
    
    # Store or update chat info with only serializable data
    context.bot_data["tracked_chats"][chat.id] = {
        "chat_id": chat.id,
        "title": chat.title or (f"Private chat with {update.effective_user.first_name}" if chat.type == "private" else "Unknown"),
        "type": chat.type,
        "members": member_count,
        "username": chat.username,
        "last_activity": datetime.now().isoformat(),
    }
    
    # Don't force persistence update on every message
    # Let the application handle persistence based on its schedule
    # await context.application.update_persistence()  # Removed this line

async def admin_list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all groups the bot is in (admin only)."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt to admin command by user {user_id}")
        return
    
    if "tracked_chats" not in context.bot_data or not context.bot_data["tracked_chats"]:
        await update.message.reply_text("No tracked chats available.")
        return
    
    groups = [
        chat for chat_id, chat in context.bot_data["tracked_chats"].items() 
        if chat.get("type") in ["group", "supergroup"]
    ]
    
    if not groups:
        await update.message.reply_text("Bot is not in any groups.")
        return
    
    # Prepare a formatted list of groups
    groups_text = "\n\n".join([
        f"*{i+1}. {g['title']}*\n"
        f"ID: `{g['chat_id']}`\n"
        f"Type: {g['type']}\n"
        f"Username: {g.get('username', 'None')}\n"
        f"Last activity: {g.get('last_activity', 'Unknown')}"
        for i, g in enumerate(groups)
    ])
    
    await update.message.reply_text(
        f"🤖 *Bot is in {len(groups)} groups:*\n\n{groups_text}",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"Admin {user_id} requested group list")

async def admin_group_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show filters configured for a specific group (admin only)."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt to admin command by user {user_id}")
        return
    
    # Get group ID from command arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a group ID or use /admin_list_groups to see available groups."
        )
        return
    
    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid group ID. Use /admin_list_groups to see available groups.")
        return
    
    # Get the group data from persistent storage
    chat_data = context.application.chat_data.get(group_id)
    
    if not chat_data:
        await update.message.reply_text(f"No data found for group ID {group_id}")
        return
    
    # Get filter patterns for this group
    filter_patterns = chat_data.get("filter_patterns", [])
    
    if not filter_patterns:
        await update.message.reply_text(f"No filter patterns configured for group ID {group_id}")
        return
    
    # Convert to list if it's a set
    if isinstance(filter_patterns, set):
        filter_patterns = list(filter_patterns)
    
    # Format the filter patterns
    patterns_text = "\n".join([f"{i+1}. `{pattern}`" for i, pattern in enumerate(filter_patterns)])
    
    # Get group name from tracked chats if available
    group_name = "Unknown Group"
    if "tracked_chats" in context.bot_data and group_id in context.bot_data["tracked_chats"]:
        group_name = context.bot_data["tracked_chats"][group_id].get("title", "Unknown Group")
    
    await update.message.reply_text(
        f"*Filters for {group_name} (ID: {group_id}):*\n\n{patterns_text}",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"Admin {user_id} requested filters for group {group_id}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics and diagnostics (admin only)."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt to admin command by user {user_id}")
        return
    
    # Gather statistics
    total_chats = 0
    private_chats = 0
    groups = 0
    supergroups = 0
    channels = 0
    total_filters = 0
    
    if "tracked_chats" in context.bot_data:
        for chat_id, chat in context.bot_data["tracked_chats"].items():
            total_chats += 1
            chat_type = chat.get("type", "unknown")
            if chat_type == "private":
                private_chats += 1
            elif chat_type == "group":
                groups += 1
            elif chat_type == "supergroup":
                supergroups += 1
            elif chat_type == "channel":
                channels += 1
            
            # Count filters
            chat_data = context.application.chat_data.get(chat_id, {})
            filters_count = len(chat_data.get("filter_patterns", []))
            total_filters += filters_count
    
    # Bot uptime
    bot_start_time = context.bot_data.get("start_time", "Unknown")
    uptime_str = "Unknown"
    if bot_start_time != "Unknown":
        try:
            start_time = datetime.fromisoformat(bot_start_time)
            uptime = datetime.now() - start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        except Exception as e:
            logger.error(f"Error calculating uptime: {e}")
            uptime_str = "Error calculating"
    
    # Format statistics
    stats_text = (
        f"*🤖 Bot Statistics*\n\n"
        f"*Chats:*\n"
        f"• Total chats: {total_chats}\n"
        f"• Private chats: {private_chats}\n"
        f"• Groups: {groups}\n"
        f"• Supergroups: {supergroups}\n"
        f"• Channels: {channels}\n\n"
        f"*Filters:*\n"
        f"• Total filter patterns: {total_filters}\n\n"
        f"*Performance:*\n"
        f"• Bot uptime: {uptime_str}\n"
    )
    
    await update.message.reply_text(
        stats_text,
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"Admin {user_id} requested bot statistics")

def register_diagnostic_handlers(application):
    """Register diagnostic handlers with the application."""
    # Admin commands
    application.add_handler(CommandHandler("admin_list_groups", admin_list_groups))
    application.add_handler(CommandHandler("admin_group_filters", admin_group_filters))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    
    logger.info("Diagnostic handlers registered")

    # Note: track_chat is not a command, it should be called from other handlers
    # like message handlers or chat_member handlers 