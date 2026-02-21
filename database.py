"""
SQLite database layer — thread-safe via check_same_thread=False + manual
connection-per-call pattern using a module-level lock.
"""

import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional

from config import DATABASE_PATH

logger = logging.getLogger(__name__)
_lock = threading.Lock()


# ── Schema ────────────────────────────────────────────────────────────────────

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    UNIQUE NOT NULL,
    buyer_id        INTEGER NOT NULL,
    buyer_username  TEXT,
    seller_id       INTEGER,
    seller_username TEXT    NOT NULL,
    amount_usdt     REAL    NOT NULL,
    commission      REAL    NOT NULL,
    total_required  REAL    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'AWAITING_PAYMENT',
    tx_hash         TEXT,
    dispute_reason  TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""

CREATE_TX_TABLE = """
CREATE TABLE IF NOT EXISTS used_transactions (
    tx_hash TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
"""

# Trade statuses:
#   AWAITING_PAYMENT  – created, waiting for buyer to pay
#   PAYMENT_VERIFIED  – BscScan confirmed, waiting for seller to confirm delivery
#   COMPLETED         – seller confirmed, funds (conceptually) released
#   DISPUTED          – either party raised a dispute
#   CANCELLED         – cancelled before payment


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(CREATE_TRADES_TABLE)
            conn.execute(CREATE_TX_TABLE)
            conn.commit()
            logger.info("Database initialised at %s", DATABASE_PATH)
        finally:
            conn.close()


# ── Trade helpers ─────────────────────────────────────────────────────────────

def create_trade(
    trade_id: str,
    buyer_id: int,
    buyer_username: Optional[str],
    seller_username: str,
    amount_usdt: float,
    commission: float,
    total_required: float,
) -> None:
    now = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO trades
                    (trade_id, buyer_id, buyer_username, seller_username,
                     amount_usdt, commission, total_required,
                     status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trade_id, buyer_id, buyer_username, seller_username,
                    amount_usdt, commission, total_required,
                    "AWAITING_PAYMENT", now, now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_trade(trade_id: str) -> Optional[sqlite3.Row]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            return row
        finally:
            conn.close()


def get_trade_by_tx(tx_hash: str) -> Optional[sqlite3.Row]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM trades WHERE tx_hash = ?", (tx_hash.lower(),)
            ).fetchone()
            return row
        finally:
            conn.close()


def get_trades_by_buyer(buyer_id: int) -> list:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM trades WHERE buyer_id = ? ORDER BY created_at DESC",
                (buyer_id,),
            ).fetchall()
            return rows
        finally:
            conn.close()


def get_all_trades(limit: int = 50) -> list:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return rows
        finally:
            conn.close()


def update_trade_status(
    trade_id: str,
    status: str,
    tx_hash: Optional[str] = None,
    seller_id: Optional[int] = None,
    dispute_reason: Optional[str] = None,
) -> None:
    now = _now()
    with _lock:
        conn = _connect()
        try:
            if tx_hash:
                conn.execute(
                    "UPDATE trades SET status=?, tx_hash=?, updated_at=? WHERE trade_id=?",
                    (status, tx_hash.lower(), now, trade_id),
                )
            elif seller_id:
                conn.execute(
                    "UPDATE trades SET status=?, seller_id=?, updated_at=? WHERE trade_id=?",
                    (status, seller_id, now, trade_id),
                )
            elif dispute_reason:
                conn.execute(
                    "UPDATE trades SET status=?, dispute_reason=?, updated_at=? WHERE trade_id=?",
                    (status, dispute_reason, now, trade_id),
                )
            else:
                conn.execute(
                    "UPDATE trades SET status=?, updated_at=? WHERE trade_id=?",
                    (status, now, trade_id),
                )
            conn.commit()
        finally:
            conn.close()


# ── Duplicate-TX helpers ──────────────────────────────────────────────────────

def is_tx_used(tx_hash: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM used_transactions WHERE tx_hash = ?",
                (tx_hash.lower(),),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def mark_tx_used(tx_hash: str, trade_id: str) -> None:
    now = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO used_transactions (tx_hash, trade_id, recorded_at) VALUES (?,?,?)",
                (tx_hash.lower(), trade_id, now),
            )
            conn.commit()
        finally:
            conn.close()


# ── Utility ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
