import logging
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
)
from functools import wraps

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
    
    # Count filter patterns
    filter_count = 0
    if "filter_patterns" in context.chat_data and context.chat_data["filter_patterns"]:
        filter_count = len(context.chat_data["filter_patterns"])
    
    janitor_text = "enabled" if janitor_status else "disabled"
    channel_filter_text = "enabled" if channel_filter_status else "disabled"
    
    status_text = f"""
*Current settings for this chat:*

🧹 *Janitor:* {janitor_text}
📺 *Channel Filter:* {channel_filter_text}
🔍 *Active Filters:* {filter_count} pattern(s)

*Available Commands:*
• `/enable_janitor` / `/disable_janitor` - Toggle message filtering
• `/toggle_channel_filter` - Toggle external channel message filtering
• `/add_filter <pattern>` - Add regex filter
• `/remove_filter <number>` - Remove filter
• `/list_filters` - Show all filters
    """
    
    await update.message.reply_text(status_text, parse_mode="Markdown")
    logger.info(f"Settings displayed for chat {update.effective_chat.id}")


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
    
    logger.info("Settings handlers registered") 
