import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# Import handlers
from handlers.basic import register_basic_handlers
from handlers.admin import register_admin_handlers
from handlers.conversation import register_conversation_handlers
from handlers.filters import register_filter_handlers
from handlers.diagnostics import register_diagnostic_handlers, track_chat
from utils.logger import setup_logger

from telegram import Update
from telegram.ext import ApplicationBuilder, PicklePersistence, ChatMemberHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Set up logging
logger = setup_logger()

def main() -> None:
    """Start the bot."""
    # Get token from environment
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No token provided. Set TELEGRAM_BOT_TOKEN environment variable.")
        return

    # Setup persistence with a reasonable update interval
    persistence_path = os.getenv("PERSISTENCE_PATH", "bot_data")
    persistence = PicklePersistence(
        filepath=persistence_path,
        update_interval=60  # Save every 60 seconds instead of every message
    )
    
    # Create application with persistence
    application = ApplicationBuilder().token(token).persistence(persistence).build()
    
    # Record bot start time
    application.bot_data["start_time"] = datetime.now().isoformat()
    
    # Register handlers
    register_basic_handlers(application)
    register_admin_handlers(application)
    register_conversation_handlers(application)
    register_filter_handlers(application)
    register_diagnostic_handlers(application)
    
    # Add a chat update handler to track groups
    application.add_handler(
        MessageHandler(filters.ALL, track_chat_activity),
        group=999  # High group number to run after other handlers
    )
    
    # Start the Bot
    logger.info("Starting bot")
    application.run_polling()

async def track_chat_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track chat activity for monitoring."""
    if update.effective_chat:
        await track_chat(update, context)

if __name__ == '__main__':
    main()
