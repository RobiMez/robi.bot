"""
Coupon system handlers for Telegram bot.
Implements /initcoupons, /balance, /give, /ask, /history, and /gam commands.
"""

import logging
import re
import random
from typing import Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes
)

from handlers import coupons_db

logger = logging.getLogger("telegram_bot")

# Constants
INITIAL_COUPON_BALANCE = 50
DEFAULT_HISTORY_LIMIT = 10
MAX_HISTORY_LIMIT = 25


# ============================================================================
# Helper Functions
# ============================================================================

def is_registered(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if a user is registered in the coupon system."""
    return "coupon_balance" in context.application.user_data.get(user_id, {})


def get_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Get user's coupon balance."""
    return context.application.user_data.get(user_id, {}).get("coupon_balance", 0)


async def set_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int):
    """Set user's coupon balance."""
    if user_id not in context.application.user_data:
        context.application.user_data[user_id] = {}
    context.application.user_data[user_id]["coupon_balance"] = amount
    await context.application.update_persistence()


async def adjust_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int, delta: int) -> int:
    """Adjust user's balance by delta and return new balance."""
    current = get_balance(context, user_id)
    new_balance = current + delta
    await set_balance(context, user_id, new_balance)
    return new_balance


def parse_username(text: str) -> Optional[str]:
    """Parse and clean username from text."""
    if not text:
        return None
    # Remove @ prefix if present
    username = text.strip().lstrip('@')
    return username if username else None


def parse_amount(text: str) -> Optional[int]:
    """Parse amount from text. Returns None if invalid."""
    try:
        amount = int(text)
        return amount if amount > 0 else None
    except (ValueError, TypeError):
        return None


async def find_user_by_username(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[int]:
    """Find user_id by username. Returns None if not found."""
    username_lower = username.lower()
    
    # Search through all registered users in user_data
    for user_id, user_data in context.application.user_data.items():
        stored_username = user_data.get("username", "").lower()
        if stored_username == username_lower:
            return user_id
    
    # Fallback: check database
    user = coupons_db.get_user_by_username(username)
    if user:
        return user["telegram_user_id"]
    
    return None


async def update_user_info(context: ContextTypes.DEFAULT_TYPE, user_id: int, 
                          username: Optional[str], display_name: Optional[str]):
    """Update user info in both persistence and database."""
    if user_id not in context.application.user_data:
        context.application.user_data[user_id] = {}
    
    if username:
        context.application.user_data[user_id]["username"] = username
    if display_name:
        context.application.user_data[user_id]["display_name"] = display_name
    
    await context.application.update_persistence()
    
    # Also update in database
    coupons_db.update_user_info(user_id, username, display_name)


# ============================================================================
# Command Handlers
# ============================================================================

async def initcoupons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register user with initial coupon balance."""
    user = update.effective_user
    user_id = user.id
    
    # Update user info
    await update_user_info(context, user_id, user.username, user.first_name)
    
    if is_registered(context, user_id):
        # User already registered
        balance = get_balance(context, user_id)
        await update.message.reply_text(f"🎟️ You're already registered. Balance: {balance}")
        logger.info(f"User {user_id} attempted re-registration (balance: {balance})")
    else:
        # New user - register with initial balance
        await set_balance(context, user_id, INITIAL_COUPON_BALANCE)
        
        # Create user in database
        coupons_db.create_user(user_id, user.username, user.first_name)
        
        # Log init transaction
        coupons_db.log_transaction(
            trans_type="init",
            amount=INITIAL_COUPON_BALANCE,
            to_user_id=user_id,
            reason="Initial registration"
        )
        
        await update.message.reply_text(f"🎟️ Registered. Starting balance: {INITIAL_COUPON_BALANCE}")
        logger.info(f"User {user_id} registered with {INITIAL_COUPON_BALANCE} coupons")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current coupon balance."""
    user_id = update.effective_user.id
    
    if not is_registered(context, user_id):
        await update.message.reply_text(
            "❌ You're not registered yet. Use /initcoupons to get started."
        )
        return
    
    balance_amount = get_balance(context, user_id)
    await update.message.reply_text(f"🎟️ Balance: {balance_amount} coupons")
    logger.info(f"User {user_id} checked balance: {balance_amount}")


async def give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transfer coupons to another user."""
    user = update.effective_user
    sender_id = user.id
    
    # Check if sender is registered
    if not is_registered(context, sender_id):
        await update.message.reply_text(
            "❌ You're not registered yet. Use /initcoupons to get started."
        )
        return
    
    # Parse command arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage: /give @username <amount> [reason]\n"
            "Example: /give @alice 5 for being awesome"
        )
        return
    
    target_username = parse_username(context.args[0])
    amount = parse_amount(context.args[1])
    reason = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    if not target_username:
        await update.message.reply_text("❌ Invalid username format.")
        return
    
    if not amount:
        await update.message.reply_text("❌ Invalid amount. Must be a positive number.")
        return
    
    # Find target user
    target_id = await find_user_by_username(context, target_username)
    if not target_id:
        await update.message.reply_text(
            f"❌ User @{target_username} not found or not registered. "
            "They need to use /initcoupons first."
        )
        return
    
    if target_id == sender_id:
        await update.message.reply_text("❌ You can't give coupons to yourself.")
        return
    
    # Check if target is registered
    if not is_registered(context, target_id):
        await update.message.reply_text(
            f"❌ User @{target_username} is not registered. "
            "They need to use /initcoupons first."
        )
        return
    
    # Check sender has enough balance
    sender_balance = get_balance(context, sender_id)
    if sender_balance < amount:
        await update.message.reply_text(
            f"❌ Not enough coupons. Your balance: {sender_balance}"
        )
        return
    
    # Perform atomic transfer
    try:
        await adjust_balance(context, sender_id, -amount)
        await adjust_balance(context, target_id, amount)
        
        # Log transaction
        coupons_db.log_transaction(
            trans_type="give",
            from_user_id=sender_id,
            to_user_id=target_id,
            amount=amount,
            reason=reason
        )
        
        new_balance = get_balance(context, sender_id)
        reason_text = f" — {reason}" if reason else ""
        await update.message.reply_text(
            f"✅ Gave {amount} coupons to @{target_username}{reason_text}. "
            f"Your balance: {new_balance}"
        )
        logger.info(f"Transfer: {sender_id} -> {target_id}, amount: {amount}")
        
    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        await update.message.reply_text("❌ Transfer failed. Please try again.")


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Request coupons from another user with inline approval button."""
    user = update.effective_user
    requester_id = user.id
    
    # Check if requester is registered
    if not is_registered(context, requester_id):
        await update.message.reply_text(
            "❌ You're not registered yet. Use /initcoupons to get started."
        )
        return
    
    # Parse command arguments
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Usage: /ask @username <amount> <reason>\n"
            "Example: /ask @alice 5 for cuddles"
        )
        return
    
    target_username = parse_username(context.args[0])
    amount = parse_amount(context.args[1])
    reason = " ".join(context.args[2:])
    
    if not target_username:
        await update.message.reply_text("❌ Invalid username format.")
        return
    
    if not amount:
        await update.message.reply_text("❌ Invalid amount. Must be a positive number.")
        return
    
    if not reason:
        await update.message.reply_text("❌ Please provide a reason for the request.")
        return
    
    # Find target user
    target_id = await find_user_by_username(context, target_username)
    if not target_id:
        await update.message.reply_text(
            f"❌ User @{target_username} not found or not registered. "
            "They need to use /initcoupons first."
        )
        return
    
    if target_id == requester_id:
        await update.message.reply_text("❌ You can't request coupons from yourself.")
        return
    
    # Check if target is registered
    if not is_registered(context, target_id):
        await update.message.reply_text(
            f"❌ User @{target_username} is not registered. "
            "They need to use /initcoupons first."
        )
        return
    
    # Create request in database
    request_id = coupons_db.create_request(
        requester_user_id=requester_id,
        target_user_id=target_id,
        amount=amount,
        reason=reason
    )
    
    # Create inline keyboard with approval button
    keyboard = [[
        InlineKeyboardButton(
            f"Give {amount} coupons",
            callback_data=f"req_approve:{request_id}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send request message in the same chat as a reply
    requester_username = user.username or user.first_name or "Someone"
    try:
        await update.message.reply_text(
            text=(
                f"🎟️ Coupon request\n"
                f"@{requester_username} requests {amount} coupons from @{target_username}\n"
                f"Reason: {reason}"
            ),
            reply_markup=reply_markup
        )
        
        logger.info(f"Request created: {request_id} ({requester_id} -> {target_id})")
        
    except Exception as e:
        logger.error(f"Failed to send request message: {e}")
        await update.message.reply_text("❌ Failed to send request. Please try again.")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent transaction history."""
    user_id = update.effective_user.id
    
    # Check if user is registered
    if not is_registered(context, user_id):
        await update.message.reply_text(
            "❌ You're not registered yet. Use /initcoupons to get started."
        )
        return
    
    # Parse limit argument
    limit = DEFAULT_HISTORY_LIMIT
    if context.args:
        parsed_limit = parse_amount(context.args[0])
        if parsed_limit:
            limit = min(parsed_limit, MAX_HISTORY_LIMIT)
    
    # Fetch transactions
    transactions = coupons_db.get_user_transactions(user_id, limit)
    
    if not transactions:
        await update.message.reply_text("🧾 No transaction history yet.")
        return
    
    # Format transactions
    lines = [f"🧾 Last {len(transactions)} transactions\n"]
    
    for trans in transactions:
        trans_type = trans["type"]
        amount = trans["amount"]
        reason = trans["reason"]
        
        if trans_type == "init":
            lines.append(f"⬆️ +{amount} init")
        elif trans["to_user_id"] == user_id:
            # Received coupons
            from_username = trans["from_username"] or "unknown"
            reason_text = f" — {reason}" if reason else ""
            lines.append(f"⬆️ +{amount} from @{from_username}{reason_text}")
        elif trans["from_user_id"] == user_id:
            # Sent coupons
            to_username = trans["to_username"] or "unknown"
            reason_text = f" — {reason}" if reason else ""
            lines.append(f"⬇️ -{amount} to @{to_username}{reason_text}")
    
    await update.message.reply_text("\n".join(lines))
    logger.info(f"User {user_id} viewed history ({len(transactions)} transactions)")


async def gamble(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a gambling challenge - winner takes double the bet."""
    user = update.effective_user
    gambler_id = user.id
    
    # Check if gambler is registered
    if not is_registered(context, gambler_id):
        await update.message.reply_text(
            "❌ You're not registered yet. Use /initcoupons to get started."
        )
        return
    
    # Parse command arguments
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ Usage: /gam <amount>\n"
            "Example: /gam 5\n"
            "Winner takes double (10 coupons)!"
        )
        return
    
    amount = parse_amount(context.args[0])
    
    if not amount:
        await update.message.reply_text("❌ Invalid amount. Must be a positive number.")
        return
    
    # Check gambler has enough balance
    gambler_balance = get_balance(context, gambler_id)
    if gambler_balance < amount:
        await update.message.reply_text(
            f"❌ Not enough coupons. Your balance: {gambler_balance}"
        )
        return
    
    # Create gamble request in database (reuse requests table with special type)
    request_id = coupons_db.create_request(
        requester_user_id=gambler_id,
        target_user_id=0,  # 0 means "anyone can accept"
        amount=amount,
        reason="gamble"
    )
    
    # Create inline keyboard with accept button
    keyboard = [[
        InlineKeyboardButton(
            f"🎲 Accept gamble ({amount} coupons)",
            callback_data=f"gamble_accept:{request_id}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send gamble challenge in the chat
    gambler_username = user.username or user.first_name or "Someone"
    try:
        await update.message.reply_text(
            text=(
                f"🎲 Gambling Challenge!\n"
                f"@{gambler_username} bets {amount} coupons\n"
                f"Winner takes {amount * 2} coupons!\n"
                f"50/50 chance - accept to play!"
            ),
            reply_markup=reply_markup
        )
        
        logger.info(f"Gamble created: {request_id} by {gambler_id} for {amount}")
        
    except Exception as e:
        logger.error(f"Failed to send gamble message: {e}")
        await update.message.reply_text("❌ Failed to create gamble. Please try again.")


# ============================================================================
# Callback Handler
# ============================================================================

async def handle_request_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approval button press for coupon requests."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    
    user_id = update.effective_user.id
    
    # Parse callback data
    if not query.data.startswith("req_approve:"):
        await query.edit_message_text("❌ Invalid request.")
        return
    
    request_id = query.data.split(":", 1)[1]
    
    # Fetch request from database
    request = coupons_db.get_request(request_id)
    if not request:
        await query.edit_message_text("❌ Request not found.")
        return
    
    # Check if already approved (idempotency)
    if request["status"] == "approved":
        await query.answer("Already approved ✅", show_alert=True)
        return
    
    # Verify the button presser is the target user
    if user_id != request["target_user_id"]:
        await query.answer("❌ This request is not for you.", show_alert=True)
        return
    
    # Check if request is still pending
    if request["status"] != "pending":
        await query.edit_message_text(f"❌ Request is {request['status']}.")
        return
    
    requester_id = request["requester_user_id"]
    amount = request["amount"]
    reason = request["reason"]
    
    # Check if target has enough balance
    target_balance = get_balance(context, user_id)
    if target_balance < amount:
        await query.edit_message_text(
            f"❌ Not enough coupons to approve.\n"
            f"Your balance: {target_balance}\n"
            f"Required: {amount}"
        )
        return
    
    # Perform atomic transfer
    try:
        # Update request status first (for idempotency)
        success = coupons_db.update_request_status(request_id, "approved")
        if not success:
            # Race condition - request was already processed
            await query.answer("Already approved ✅", show_alert=True)
            return
        
        # Transfer coupons
        giver_new_balance = await adjust_balance(context, user_id, -amount)
        receiver_new_balance = await adjust_balance(context, requester_id, amount)
        
        # Log transaction
        coupons_db.log_transaction(
            trans_type="ask_approved",
            from_user_id=user_id,
            to_user_id=requester_id,
            amount=amount,
            reason=reason,
            request_id=request_id
        )
        
        # Get usernames for display
        giver_username = request["target_username"] or "You"
        receiver_username = request["requester_username"] or "Requester"
        
        await query.edit_message_text(
            f"✅ Approved: gave {amount} coupons\n"
            f"@{giver_username}: {giver_new_balance}\n"
            f"@{receiver_username}: {receiver_new_balance}"
        )
        logger.info(f"Request approved: {request_id} ({user_id} -> {requester_id})")
        
    except Exception as e:
        logger.error(f"Approval failed: {e}")
        await query.edit_message_text("❌ Approval failed. Please try again.")


async def handle_gamble_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle acceptance of a gambling challenge."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    
    acceptor_id = update.effective_user.id
    
    # Parse callback data
    if not query.data.startswith("gamble_accept:"):
        await query.edit_message_text("❌ Invalid gamble.")
        return
    
    request_id = query.data.split(":", 1)[1]
    
    # Fetch request from database
    request = coupons_db.get_request(request_id)
    if not request:
        await query.edit_message_text("❌ Gamble not found.")
        return
    
    # Check if already completed
    if request["status"] != "pending":
        await query.answer("Gamble already completed!", show_alert=True)
        return
    
    gambler_id = request["requester_user_id"]
    amount = request["amount"]
    
    # Can't gamble with yourself
    if acceptor_id == gambler_id:
        await query.answer("❌ You can't accept your own gamble!", show_alert=True)
        return
    
    # Check if acceptor is registered
    if not is_registered(context, acceptor_id):
        await query.answer("❌ You need to /initcoupons first!", show_alert=True)
        return
    
    # Check both players have enough balance
    gambler_balance = get_balance(context, gambler_id)
    acceptor_balance = get_balance(context, acceptor_id)
    
    if gambler_balance < amount:
        await query.edit_message_text(
            f"❌ Gambler doesn't have enough coupons anymore.\n"
            f"Required: {amount}"
        )
        return
    
    if acceptor_balance < amount:
        await query.answer(
            f"❌ You need {amount} coupons to accept! Your balance: {acceptor_balance}",
            show_alert=True
        )
        return
    
    # Perform the gamble!
    try:
        # Update request status first (for idempotency)
        success = coupons_db.update_request_status(request_id, "approved")
        if not success:
            await query.answer("Gamble already completed!", show_alert=True)
            return
        
        # 50/50 chance
        gambler_wins = random.random() < 0.5
        
        if gambler_wins:
            # Gambler wins - takes amount from acceptor
            winner_id = gambler_id
            loser_id = acceptor_id
            winner_username = request["requester_username"]
            loser_username = context.application.user_data.get(acceptor_id, {}).get("username", "Acceptor")
        else:
            # Acceptor wins - takes amount from gambler
            winner_id = acceptor_id
            loser_id = gambler_id
            winner_username = context.application.user_data.get(acceptor_id, {}).get("username", "Acceptor")
            loser_username = request["requester_username"]
        
        # Transfer coupons
        winner_new_balance = await adjust_balance(context, winner_id, amount)
        loser_new_balance = await adjust_balance(context, loser_id, -amount)
        
        # Log transaction
        coupons_db.log_transaction(
            trans_type="give",
            from_user_id=loser_id,
            to_user_id=winner_id,
            amount=amount,
            reason=f"gamble (won)",
            request_id=request_id
        )
        
        # Show results
        await query.edit_message_text(
            f"🎲 Gamble Complete!\n"
            f"{'🎉' if gambler_wins else '💔'} @{winner_username} WINS!\n"
            f"{'💔' if gambler_wins else '🎉'} @{loser_username} loses\n\n"
            f"@{winner_username}: {winner_new_balance} (+{amount})\n"
            f"@{loser_username}: {loser_new_balance} (-{amount})"
        )
        
        logger.info(f"Gamble completed: {request_id}, winner: {winner_id}")
        
    except Exception as e:
        logger.error(f"Gamble failed: {e}")
        await query.edit_message_text("❌ Gamble failed. Please try again.")


# ============================================================================
# Registration
# ============================================================================

def register_coupon_handlers(application):
    """Register all coupon-related handlers with the application."""
    application.add_handler(CommandHandler("initcoupons", initcoupons))
    application.add_handler(CommandHandler("bal", balance))
    application.add_handler(CommandHandler("give", give))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("gam", gamble))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(
        handle_request_approval, 
        pattern=r"^req_approve:"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_gamble_accept,
        pattern=r"^gamble_accept:"
    ))
    
    logger.info("Coupon handlers registered")

