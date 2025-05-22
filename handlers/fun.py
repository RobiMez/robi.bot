import logging
import requests
import shlex
from telegram import Update, Poll
from telegram.ext import ContextTypes, CommandHandler

logger = logging.getLogger("telegram_bot")

JOKE_APIS = [
    "https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist,explicit",
    "https://official-joke-api.appspot.com/random_joke",
    "https://api.chucknorris.io/jokes/random"
]

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and send a random joke from multiple sources."""
    for api_url in JOKE_APIS:
        try:
            response = requests.get(api_url, timeout=3)
            if response.status_code == 200:
                joke_data = response.json()
                
                if "chucknorris.io" in api_url:
                    joke_text = joke_data['value']
                elif "jokeapi.dev" in api_url:
                    if joke_data['type'] == 'single':
                        joke_text = joke_data['joke']
                    else:
                        joke_text = f"{joke_data['setup']}\n\n{joke_data['delivery']}"
                elif "appspot.com" in api_url:
                    joke_text = f"{joke_data['setup']}\n\n{joke_data['punchline']}"
                
                await update.message.reply_text(joke_text)
                return
                
        except Exception as e:
            logger.warning(f"Failed to fetch from {api_url}: {e}")
            continue
    
    await update.message.reply_text("Couldn't fetch a joke right now. Try again later!")


async def create_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a poll from command arguments with proper quoted string handling."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /poll \"Question\" \"Option1\" \"Option2\" ...\n"
            "Example: /poll \"Favorite Person?\" \"Me\" \"Myself\" \"I\""
        )
        return
    
    try:
       
        parsed_args = shlex.split(' '.join(context.args))
        
        if len(parsed_args) < 3:
            await update.message.reply_text(
                "You need at least 1 question and 2 options.\n"
                "Example: /poll \"Favorite Person?\" \"Me\" \"Myself\" \"I\""
            )
            return
            
        question = parsed_args[0]
        options = parsed_args[1:]
        
      
        if len(options) < 2:
            await update.message.reply_text("You need at least 2 options for a poll.")
            return
        if len(options) > 10:
            await update.message.reply_text("You can have maximum 10 options in a poll.")
            options = options[:10]  
            
        await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False
        )
        
    except ValueError as e:
        await update.message.reply_text(
            "Invalid format. Make sure to use quotes correctly.\n"
            "Example: /poll \"Favorite Person?\" \"Me\" \"Myself\" \"I\""
        )
        logger.error(f"Poll command error: {e}")
    except Exception as e:
        await update.message.reply_text("Couldn't create the poll. Please try again.")
        logger.error(f"Poll creation error: {e}")

def register_fun_handlers(application):
    """Register fun command handlers."""
    application.add_handler(CommandHandler("joke", joke))
  
    application.add_handler(CommandHandler("poll", create_poll))
    
    logger.info("Fun handlers registered")