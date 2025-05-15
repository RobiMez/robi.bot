import logging
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest
from handlers.conversation import admin_only

logger = logging.getLogger("telegram_bot")

@admin_only
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a regex pattern to the filter list."""
    # Check if user is admin or has permission
    # This is just a basic implementation - you may want to enhance permission checks
    
    # Get the pattern from command arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide a regex pattern to filter.\n"
            "Example: /add_filter \\bspam\\b"
        )
        return
    
    pattern = ' '.join(context.args)
    
    # Validate regex pattern
    try:
        re.compile(pattern)
    except re.error:
        await update.message.reply_text(f"'{pattern}' is not a valid regex pattern.")
        return
    
    # Initialize filter_patterns if it doesn't exist - use a list instead of a set
    if "filter_patterns" not in context.chat_data:
        context.chat_data["filter_patterns"] = []
    
    # Add the pattern to the list if not already present
    if pattern not in context.chat_data["filter_patterns"]:
        context.chat_data["filter_patterns"].append(pattern)
        # Ensure data is marked for persistence
        await context.application.update_persistence()
        await update.message.reply_text(f"Added filter pattern: '{pattern}'")
        logger.info(f"Added filter pattern '{pattern}' in chat {update.effective_chat.id}")
    else:
        await update.message.reply_text(f"Filter pattern '{pattern}' already exists.")


@admin_only
async def remove_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a regex pattern from the filter list."""
    # Check if user is admin or has permission
    
    # Get the pattern from command arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Please provide the filter number or regex pattern to remove.\n"
            "Use /list_filters to see all patterns."
        )
        return
    
    arg = ' '.join(context.args)
    
    # Check if filter_patterns exists
    if "filter_patterns" not in context.chat_data or not context.chat_data["filter_patterns"]:
        await update.message.reply_text("No filter patterns are configured for this chat.")
        return
    
    # Convert to list if it's a set
    if isinstance(context.chat_data["filter_patterns"], set):
        context.chat_data["filter_patterns"] = list(context.chat_data["filter_patterns"])
    
    patterns_list = context.chat_data["filter_patterns"]
    
    # Try to interpret the argument as a filter number
    try:
        # Check if this is a number
        index = int(arg) - 1  # Convert to 0-based index
        if 0 <= index < len(patterns_list):
            pattern = patterns_list[index]
            patterns_list.remove(pattern)
            # Ensure data is marked for persistence
            await context.application.update_persistence()
            await update.message.reply_text(f"Removed filter #{index+1}: '{pattern}'")
            logger.info(f"Removed filter pattern '{pattern}' in chat {update.effective_chat.id}")
            return
        else:
            await update.message.reply_text(f"Invalid filter number. Please use a number between 1 and {len(patterns_list)}")
            return
    except ValueError:
        # Not a number, treat as a pattern (existing behavior)
        pattern = arg
        if pattern in patterns_list:
            patterns_list.remove(pattern)
            # Ensure data is marked for persistence
            await context.application.update_persistence()
            await update.message.reply_text(f"Removed filter pattern: '{pattern}'")
            logger.info(f"Removed filter pattern '{pattern}' in chat {update.effective_chat.id}")
            return
    
    # If we get here, neither a valid number nor a valid pattern was provided
    patterns_text = "\n".join([f"{i+1}. `{p}`" for i, p in enumerate(patterns_list)])
    await update.message.reply_text(
        f"Filter pattern '{arg}' not found.\n\n"
        f"Available patterns:\n{patterns_text}",
        parse_mode=ParseMode.MARKDOWN
    )


async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all regex patterns in the filter list."""
    if "filter_patterns" not in context.chat_data or not context.chat_data["filter_patterns"]:
        await update.message.reply_text("No filter patterns are configured for this chat.")
        return
    
    patterns = context.chat_data["filter_patterns"]
    if not patterns:
        await update.message.reply_text("No filter patterns are configured for this chat.")
        return
    
    # Convert to list if it's a set    
    if isinstance(patterns, set):
        patterns = list(patterns)
        context.chat_data["filter_patterns"] = patterns
        context.application.update_persistence()
        
    patterns_text = "\n".join([f"{i+1}. `{pattern}`" for i, pattern in enumerate(patterns)])
    
    await update.message.reply_text(
        f"Filter patterns for this chat:\n{patterns_text}\n\n"
        f"You can remove filters by number: `/remove_filter 2`",
        parse_mode=ParseMode.MARKDOWN
    )


async def filter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if a message matches any filter patterns and delete if it does."""
    # Skip if janitor is not enabled
    if not context.chat_data.get("janitorEnabled", False):
        return
    
    # Skip if there are no filter patterns
    if "filter_patterns" not in context.chat_data or not context.chat_data["filter_patterns"]:
        return

    # Get the message content - could be either text or caption
    message_content = update.message.text or update.message.caption
    
    # Skip if no text or caption
    if not message_content:
        return

    # Skip commands, only filter regular messages
    if message_content.startswith('/'):
        return
    
    # Check message against each pattern
    for pattern in context.chat_data["filter_patterns"]:
        try:
            if re.search(pattern, message_content, re.IGNORECASE):
                # Try to delete the message
                try:
                    user = update.effective_user
                    username = user.username or user.first_name or f"User {user.id}"
                    
                    # Delete the original message
                    await update.message.delete()
                    
                    # Send notification that will self-destruct
                    notification = await update.effective_chat.send_message(
                        f"Deleted a message from {username} \nMatched filter pattern: `{pattern}`",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Schedule deletion of our notification after 60 seconds
                    context.job_queue.run_once(
                        delete_message_job,
                        30,  # 60 seconds = 1 minute
                        data={
                            'chat_id': update.effective_chat.id,
                            'message_id': notification.message_id
                        }
                    )
                    
                    logger.info(
                        f"Deleted message from user {update.effective_user.id} in chat "
                        f"{update.effective_chat.id} matching pattern '{pattern}'"
                    )
                    return  # Stop after first match and deletion
                except BadRequest as e:
                    logger.error(
                        f"Failed to delete message: {e} - User: {update.effective_user.id}, "
                        f"Chat: {update.effective_chat.id}"
                    )
                except Exception as e:
                    logger.error(f"Error in filter_message: {e}")
        except Exception as e:
            logger.error(f"Error matching pattern '{pattern}': {e}")


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a message - used for self-destructing notifications."""
    job_data = context.job.data
    chat_id = job_data.get('chat_id')
    message_id = job_data.get('message_id')
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Deleted notification message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error deleting notification message: {e}")



async def regex_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show helpful regex patterns that can be used with filters."""
    help_text = """
*Regex Pattern Examples*

Here are some common regex patterns you can use:

*Basic Patterns:*
• `word` - Matches if "word" appears anywhere in the message
• `\\bword\\b` - Matches the exact word "word" (not inside other words)
• `hello|hi` - Matches "hello" or "hi"

*Special Characters:*
• `\\d+` - Matches one or more digits
• `\\w+` - Matches one or more word characters (letters, numbers, underscore)
• `\\s+` - Matches one or more whitespace characters

*URL and Contact Patterns:*
• `https?://\\S+` - Matches URLs beginning with http:// or https://
• `t\\.me/\\S+` - Matches Telegram links (t.me/...)
• `\\+?\\d{10,}` - Matches phone numbers (at least 10 digits)

*Examples of Use:*
• `/add_filter \\bspam\\b` - Filter messages containing exactly "spam"
• `/add_filter https?://\\S+` - Filter all URLs
• `/add_filter badword1|badword2` - Filter messages containing either word

*Note:* Some special characters need to be escaped with `\\` in regex.
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")
    logger.info(f"Regex help requested by user {update.effective_user.id} in chat {update.effective_chat.id}")


def register_filter_handlers(application):
    """Register filter handlers with the application."""
    # Command handlers
    application.add_handler(CommandHandler("add_filter", add_filter))
    application.add_handler(CommandHandler("remove_filter", remove_filter))
    application.add_handler(CommandHandler("list_filters", list_filters))
    application.add_handler(CommandHandler("regex_help", regex_help))
    
    # Global message filter handler - should be added last to process after other handlers
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
        filter_message
    ), group=1)
    
    logger.info("Filter handlers registered") 