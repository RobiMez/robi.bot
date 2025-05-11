# Telegram Bot

A scalable and extensible Telegram bot built with Python.

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your Telegram bot token:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   ```
4. Run the bot:
   ```
   python main.py
   ```

## Available Commands

- `/start` - Start the bot
- `/hello` - Get a hello message
- `/help` - Show help information
- `/stats` - Show bot statistics (admin only)
- `/enable_janitor` - Enable message filtering
- `/disable_janitor` - Disable message filtering
- `/status` - Display current chat settings

### Message Filtering Commands

- `/add_filter [pattern]` - Add a regex pattern to filter messages
- `/remove_filter [pattern]` - Remove a regex pattern
- `/list_filters` - List all configured filter patterns
- `/regex_help` - Show examples of useful regex patterns

## Features

- **Automatic Message Filtering**: Delete messages matching configured regex patterns
- **Self-Destructing Notifications**: When a message is deleted, a notification appears and disappears after 1 minute
- **Persistence**: All settings are stored and survive bot restarts
- **Role-Based Access**: Admin commands are restricted

## Project Structure

- `main.py`: Bot entry point
- `handlers/`: Command handlers
  - `basic.py`: Basic user commands
  - `admin.py`: Admin-only commands
  - `conversation.py`: Chat settings management
  - `filters.py`: Message filtering system
- `utils/`: Utility functions
  - `logger.py`: Logging setup 