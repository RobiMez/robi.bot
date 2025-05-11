import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logger = logging.getLogger("telegram_bot")

# List of admin user IDs - move to config in production
ADMIN_USERS = [352475318]  # Replace with actual admin user IDs

def admin_required(func):
    """Decorator to restrict commands to admin users only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USERS:
            await update.message.reply_text("Sorry, this command is restricted to admins.")
            logger.warning(f"Non-admin user {user_id} attempted to use admin command")
            return
        return await func(update, context)
    return wrapper

@admin_required
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send usage statistics (admin only)."""
    await update.message.reply_text("Bot statistics: (placeholder)")
    logger.info(f"Admin {update.effective_user.id} requested stats")

def register_admin_handlers(application):
    """Register admin command handlers to the application."""
    application.add_handler(CommandHandler("stats", stats))
    
    logger.info("Admin handlers registered") 