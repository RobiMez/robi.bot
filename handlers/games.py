import logging
import json
import random
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

logger = logging.getLogger("telegram_bot")

# Load Never Have I Ever questions
questions_path = os.path.join(os.path.dirname(__file__), 'data', 'never_have_i_ever_questions.json')
with open(questions_path, 'r', encoding='utf-8') as f:
    NEVER_QUESTIONS = json.load(f)

logger.info(f"Loaded {len(NEVER_QUESTIONS)} Never Have I Ever questions")

# Load Truth or Dare questions
tod_questions_path = os.path.join(os.path.dirname(__file__), 'data', 'questions.json')
with open(tod_questions_path, 'r', encoding='utf-8') as f:
    ALL_TOD_QUESTIONS = json.load(f)

# Categorize questions by type
TRUTH_QUESTIONS = [q for q in ALL_TOD_QUESTIONS if q.get('type') == 'truth']
STARTER_QUESTIONS = [q for q in ALL_TOD_QUESTIONS if q.get('type') == 'starter']

logger.info(f"Loaded {len(ALL_TOD_QUESTIONS)} Truth or Dare questions")
logger.info(f"  - Truth: {len(TRUTH_QUESTIONS)}, Starter: {len(STARTER_QUESTIONS)}")


async def neverhaveiever(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a random 'Never have I ever' question with interactive buttons."""
    try:
        # Get a random question
        question = random.choice(NEVER_QUESTIONS)
        
        # Create the message text
        message_text = f"Never have I ever {question}"
        
        # Send the message and get the message object
        sent_message = await update.message.reply_text(
            message_text,
            reply_markup=create_never_keyboard()
        )
        
        # Initialize message tracking in bot_data
        if 'never_messages' not in context.bot_data:
            context.bot_data['never_messages'] = {}
        
        # Store the original message text for this message
        message_key = f"{sent_message.chat_id}:{sent_message.message_id}"
        context.bot_data['never_messages'][message_key] = {
            'text': message_text,
            'users': []
        }
        
        logger.info(f"User {update.effective_user.id} requested Never Have I Ever question")
        
    except Exception as e:
        logger.error(f"Error in neverhaveiever command: {e}")
        await update.message.reply_text("Sorry, couldn't fetch a question right now. Try again!")


def create_never_keyboard() -> InlineKeyboardMarkup:
    """Create the inline keyboard for Never Have I Ever responses."""
    keyboard = [
        [
            InlineKeyboardButton("I have", callback_data="never:yes"),
            InlineKeyboardButton("I have never", callback_data="never:no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_never_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks for Never Have I Ever game."""
    query = update.callback_query
    
    try:
        # Parse callback data
        _, response = query.data.split(':')
        
        # Get message info
        message = query.message
        message_key = f"{message.chat_id}:{message.message_id}"
        
        # Initialize never_messages if it doesn't exist
        if 'never_messages' not in context.bot_data:
            context.bot_data['never_messages'] = {}
        
        # Get or create message data
        if message_key not in context.bot_data['never_messages']:
            # If message data doesn't exist, initialize it with current message text
            context.bot_data['never_messages'][message_key] = {
                'text': message.text,
                'users': []
            }
        
        message_data = context.bot_data['never_messages'][message_key]
        
        # Get user info
        user = query.from_user
        user_id = user.id
        
        # Create user mention link
        user_link = f"[{user.first_name}](tg://user?id={user_id})"
        
        # Check if user already responded
        existing_user = None
        for user_response in message_data['users']:
            if user_response['user_id'] == user_id:
                existing_user = user_response
                break
        
        # Update or add user response
        if existing_user:
            existing_user['response'] = response
            existing_user['username'] = user.first_name
        else:
            message_data['users'].append({
                'user_id': user_id,
                'username': user.first_name,
                'response': response
            })
        
        # Build the updated message text
        new_text = message_data['text']
        
        if message_data['users']:
            new_text += "\n"
            for user_response in message_data['users']:
                user_mention = f"[{user_response['username']}](tg://user?id={user_response['user_id']})"
                if user_response['response'] == 'yes':
                    new_text += f"\n{user_mention} has done it"
                else:
                    new_text += f"\n{user_mention} has never done it"
        
        # Edit the message with updated text
        await query.edit_message_text(
            text=new_text,
            reply_markup=create_never_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Answer the callback query to remove loading state
        await query.answer()
        
        logger.info(f"User {user_id} responded '{response}' to Never Have I Ever question")
        
    except Exception as e:
        logger.error(f"Error handling Never Have I Ever callback: {e}")
        try:
            await query.answer("An error occurred. Please try again.")
        except:
            pass


async def truth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a random truth question."""
    try:
        if not TRUTH_QUESTIONS:
            await update.message.reply_text("Sorry, no truth questions available right now.")
            return
        
        question = random.choice(TRUTH_QUESTIONS)
        await update.message.reply_text(question['summary'])
        
        logger.info(f"User {update.effective_user.id} requested a truth question")
        
    except Exception as e:
        logger.error(f"Error in truth command: {e}")
        await update.message.reply_text("Sorry, couldn't fetch a question right now. Try again!")


async def starter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a random starter question."""
    try:
        if not STARTER_QUESTIONS:
            await update.message.reply_text("Sorry, no starter questions available right now.")
            return
        
        question = random.choice(STARTER_QUESTIONS)
        await update.message.reply_text(question['summary'])
        
        logger.info(f"User {update.effective_user.id} requested a starter question")
        
    except Exception as e:
        logger.error(f"Error in starter command: {e}")
        await update.message.reply_text("Sorry, couldn't fetch a question right now. Try again!")


async def question_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a random question (any type)."""
    try:
        if not ALL_TOD_QUESTIONS:
            await update.message.reply_text("Sorry, no questions available right now.")
            return
        
        question = random.choice(ALL_TOD_QUESTIONS)
        await update.message.reply_text(question['summary'])
        
        logger.info(f"User {update.effective_user.id} requested a random question")
        
    except Exception as e:
        logger.error(f"Error in question command: {e}")
        await update.message.reply_text("Sorry, couldn't fetch a question right now. Try again!")


def register_games_handlers(application):
    """Register game command handlers."""
    # Never Have I Ever
    application.add_handler(CommandHandler("nhie", neverhaveiever))
    application.add_handler(CallbackQueryHandler(handle_never_callback, pattern="^never:"))
    
    # Truth or Dare commands
    application.add_handler(CommandHandler("truth", truth_command))
    application.add_handler(CommandHandler("starter", starter_command))
    application.add_handler(CommandHandler("question", question_command))
    
    logger.info("Games handlers registered")


