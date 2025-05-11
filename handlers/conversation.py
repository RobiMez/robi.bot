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
    status_text = "enabled" if janitor_status else "disabled"
    
    await update.message.reply_text(
        f"Current settings for this chat:\n\nJanitor: {status_text}"
    )
    logger.info(f"Settings displayed for chat {update.effective_chat.id}")


async def check_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug command to check if a user is an admin."""
    try:
        is_admin = await is_user_admin(update)
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if is_admin:
            await update.message.reply_text(f"✅ User {user_id} is an admin in this chat.")
        else:
            await update.message.reply_text(f"❌ User {user_id} is NOT an admin in this chat.")
        
        logger.info(f"Admin status check: User {user_id} in chat {chat_id} is admin: {is_admin}")
    except Exception as e:
        logger.error(f"Error checking admin status: {str(e)}")
        await update.message.reply_text("Error checking admin status.")


def register_conversation_handlers(application):
    """Register command handlers with the application."""
    # Add command handlers
    application.add_handler(CommandHandler("enable_janitor", enable_janitor))
    application.add_handler(CommandHandler("disable_janitor", disable_janitor))
    application.add_handler(CommandHandler("status", show_settings))
    application.add_handler(CommandHandler("amiadmin", check_admin_status))
    
    logger.info("Settings handlers registered") 