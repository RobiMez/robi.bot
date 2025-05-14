import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logger = logging.getLogger("telegram_bot")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    await update.message.reply_text(f'Hello {user.first_name}! I am your telegram bot.')

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a hello message."""
    user = update.effective_user
    logger.info(f"User {user.id} used hello command")
    await update.message.reply_text(f'Hello {user.first_name}!')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/start - Start the bot
/hello - Get a hello message
/help - Show this help message
/joke - Get a random joke

/poll - Create a poll (usage: /poll "Question" "Option1" "Option2")
/enable_janitor - Enable message filtering
/disable_janitor - Disable message filtering
/status - Display current chat settings

Filter management (requires janitor to be enabled):
/add_filter [pattern] - Add a regex pattern to filter messages
/remove_filter [pattern] - Remove a regex pattern
/list_filters - List all configured filter patterns
/regex_help - Show examples of useful regex patterns
    """
    await update.message.reply_text(help_text)

def register_basic_handlers(application):
    """Register basic command handlers to the application."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("hello", hello))
    application.add_handler(CommandHandler("help", help_command))
    
    logger.info("Basic handlers registered") 