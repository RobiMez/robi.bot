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


async def filter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if a message matches any filter patterns and delete if it does."""
    # Log all message details for debugging
    if update.message:
        logger.info(f"Message update details:")
        logger.info(f"  Chat ID: {update.effective_chat.id}")
        logger.info(f"  Chat type: {update.effective_chat.type}")
        logger.info(f"  From user: {update.message.from_user}")
        logger.info(f"  Sender chat: {update.message.sender_chat}")
        if update.message.sender_chat:
            logger.info(f"    Sender chat ID: {update.message.sender_chat.id}")
            logger.info(f"    Sender chat type: {update.message.sender_chat.type}")
            logger.info(f"    Sender chat title: {update.message.sender_chat.title}")
        logger.info(f"  Message text: {update.message.text[:50] if update.message.text else 'No text'}")
        logger.info(f"  Is automatic forward: {update.message.is_automatic_forward}")
        
        # Check for forward origin safely
        if hasattr(update.message, 'forward_origin') and update.message.forward_origin:
            logger.info(f"  Forward origin: {update.message.forward_origin}")
        else:
            logger.info(f"  Forward origin: None")
            
        logger.info("---")

    # Check channel filter first - delete messages from external channels if enabled
    # BUT skip automatic forwards and whitelisted channels
    if (context.chat_data.get("channelFilterEnabled", False) and
        update.message.sender_chat and 
        update.message.sender_chat.id != update.effective_chat.id and
        update.message.sender_chat.type == "channel" and
        not update.message.is_automatic_forward):  # Skip automatic forwards
        
        # Check if this channel is whitelisted
        channel_whitelist = context.chat_data.get("channelWhitelist", [])
        channel_username = update.message.sender_chat.username
        channel_id = update.message.sender_chat.id
        
        # Skip deletion if channel is whitelisted (by username or ID)
        if (channel_username and channel_username in channel_whitelist) or (str(channel_id) in channel_whitelist):
            logger.info(f"Channel {channel_username or channel_id} is whitelisted, skipping deletion")
            return
        
        try:
            channel_name = update.message.sender_chat.title or f"Channel {update.message.sender_chat.id}"
            await update.message.delete()
            
            # Send notification that will self-destruct
            notification = await update.effective_chat.send_message(
                f"🚫 Deleted a message from channel: {channel_name}",
                parse_mode=ParseMode.HTML
            )
            
            # Schedule deletion of our notification after 30 seconds
            context.job_queue.run_once(
                delete_message_job,
                30,
                data={
                    'chat_id': update.effective_chat.id,
                    'message_id': notification.message_id
                }
            )
            
            logger.info(f"Deleted channel message from {channel_name} in chat {update.effective_chat.id}")
            return  # Exit early, don't process regex filters
            
        except BadRequest as e:
            logger.error(f"Failed to delete channel message: {e} - Chat: {update.effective_chat.id}")
        except Exception as e:
            logger.error(f"Error deleting channel message: {e}")

    # Skip regex filtering if janitor is not enabled
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
                    
                    # Schedule deletion of our notification after 30 seconds
                    context.job_queue.run_once(
                        delete_message_job,
                        30,
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



def register_filter_handlers(application):
    """Register filter handlers with the application."""
 
    # Single message filter handler that handles both channel filtering and regex filtering
    #application.add_handler(MessageHandler(
    #    (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, 
    #    filter_message
    #), group=1)
    
    logger.info("Filter handlers registered") 
