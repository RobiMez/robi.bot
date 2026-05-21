import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from handlers.conversation import admin_only

logger = logging.getLogger("telegram_bot")

@admin_only
async def toggle_channel_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle channel filter mode for the chat."""
    current_state = context.chat_data.get("channelFilterEnabled", False)
    new_state = not current_state
    context.chat_data["channelFilterEnabled"] = new_state
    
    # Ensure data is marked for persistence
    await context.application.update_persistence()
    
    status = "enabled" if new_state else "disabled"
    emoji = "✅" if new_state else "❌"
    
    await update.message.reply_text(
        f"{emoji} Channel filter has been {status}.\n\n"
        f"When enabled, messages sent from external channels will be automatically deleted."
    )
    
    logger.info(f"Channel filter {status} in chat {update.effective_chat.id} by user {update.effective_user.id}")

def register_admin_handlers(application):
    """Register admin handlers with the application."""
    application.add_handler(CommandHandler("toggle_channel_filter", toggle_channel_filter))

    logger.info("Admin handlers registered")
