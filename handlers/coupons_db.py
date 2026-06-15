"""
Database operations for the coupon system.
Uses SQLite for transaction history and request tracking.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from contextlib import contextmanager

logger = logging.getLogger("telegram_bot")

DB_PATH = "coupons.db"


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_database():
    """Initialize the database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL CHECK(type IN ('init', 'give', 'ask_approved')),
                from_user_id INTEGER,
                to_user_id INTEGER,
                amount INTEGER NOT NULL CHECK(amount > 0),
                reason TEXT,
                request_id TEXT,
                FOREIGN KEY (from_user_id) REFERENCES users(telegram_user_id),
                FOREIGN KEY (to_user_id) REFERENCES users(telegram_user_id)
            )
        """)
        
        # Requests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'expired')),
                requester_user_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL CHECK(amount > 0),
                reason TEXT,
                FOREIGN KEY (requester_user_id) REFERENCES users(telegram_user_id),
                FOREIGN KEY (target_user_id) REFERENCES users(telegram_user_id)
            )
        """)
        
        # Create indices for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_from_user 
            ON transactions(from_user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_to_user 
            ON transactions(to_user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_status 
            ON requests(status)
        """)
        
        logger.info("Database schema initialized")


# User operations
def create_user(telegram_user_id: int, username: Optional[str] = None, 
                display_name: Optional[str] = None) -> bool:
    """Create a new user record."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_user_id, username, display_name)
                VALUES (?, ?, ?)
            """, (telegram_user_id, username, display_name))
            logger.info(f"Created user record for {telegram_user_id}")
            return True
    except sqlite3.IntegrityError:
        # User already exists
        return False


def update_user_info(telegram_user_id: int, username: Optional[str] = None,
                     display_name: Optional[str] = None):
    """Update user information."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET username = ?, display_name = ?
            WHERE telegram_user_id = ?
        """, (username, display_name, telegram_user_id))


def get_user(telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by telegram ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users WHERE telegram_user_id = ?
        """, (telegram_user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username (case-insensitive)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users WHERE LOWER(username) = LOWER(?)
        """, (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


# Transaction operations
def log_transaction(trans_type: str, amount: int, from_user_id: Optional[int] = None,
                   to_user_id: Optional[int] = None, reason: Optional[str] = None,
                   request_id: Optional[str] = None) -> int:
    """Log a transaction and return the transaction ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (type, from_user_id, to_user_id, amount, reason, request_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (trans_type, from_user_id, to_user_id, amount, reason, request_id))
        transaction_id = cursor.lastrowid
        logger.info(f"Logged {trans_type} transaction: {amount} coupons (ID: {transaction_id})")
        return transaction_id


def get_user_transactions(telegram_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent transactions for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.*, 
                   u_from.username as from_username,
                   u_to.username as to_username
            FROM transactions t
            LEFT JOIN users u_from ON t.from_user_id = u_from.telegram_user_id
            LEFT JOIN users u_to ON t.to_user_id = u_to.telegram_user_id
            WHERE t.from_user_id = ? OR t.to_user_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
        """, (telegram_user_id, telegram_user_id, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# Request operations
def create_request(requester_user_id: int, target_user_id: int, 
                  amount: int, reason: Optional[str] = None) -> str:
    """Create a new coupon request and return the request_id."""
    request_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (request_id, status, requester_user_id, target_user_id, amount, reason)
            VALUES (?, 'pending', ?, ?, ?, ?)
        """, (request_id, requester_user_id, target_user_id, amount, reason))
        logger.info(f"Created request {request_id}: {requester_user_id} -> {target_user_id} for {amount}")
        return request_id


def get_request(request_id: str) -> Optional[Dict[str, Any]]:
    """Get a request by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*,
                   u_req.username as requester_username,
                   u_target.username as target_username
            FROM requests r
            LEFT JOIN users u_req ON r.requester_user_id = u_req.telegram_user_id
            LEFT JOIN users u_target ON r.target_user_id = u_target.telegram_user_id
            WHERE r.request_id = ?
        """, (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_request_status(request_id: str, status: str) -> bool:
    """Update request status. Returns True if update was successful."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE requests 
            SET status = ?
            WHERE request_id = ? AND status = 'pending'
        """, (status, request_id))
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Updated request {request_id} status to {status}")
        return updated


def is_request_approved(request_id: str) -> bool:
    """Check if a request has already been approved (for idempotency)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status FROM requests WHERE request_id = ?
        """, (request_id,))
        row = cursor.fetchone()
        return row and row['status'] == 'approved'


# Initialize database on module import
init_database()

