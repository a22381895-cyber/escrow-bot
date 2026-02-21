import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_FILE = "escrow.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Teburin ciniki
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER,
                    buyer_username TEXT,
                    seller_username TEXT,
                    amount REAL,
                    fee REAL,
                    status TEXT,
                    tx_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    # Teburin masu laifi (Bans)
    c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                    user_id INTEGER PRIMARY KEY
                )''')
    conn.commit()
    conn.close()

def create_trade(buyer_id, buyer_username, seller_username, amount, fee):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO trades (buyer_id, buyer_username, seller_username, amount, fee, status) VALUES (?, ?, ?, ?, ?, 'Waiting for payment')",
              (buyer_id, buyer_username, seller_username, amount, fee))
    trade_id = c.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def get_trade(trade_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE id=?", (trade_id,))
    trade = c.fetchone()
    conn.close()
    return trade

def update_trade_status(trade_id, status, tx_hash=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if tx_hash:
        c.execute("UPDATE trades SET status=?, tx_hash=? WHERE id=?", (status, tx_hash, trade_id))
    else:
        c.execute("UPDATE trades SET status=? WHERE id=?", (status, trade_id))
    conn.commit()
    conn.close()

def ban_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM banned_users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return bool(result)

def get_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(amount) FROM trades WHERE status='Completed'")
    completed_data = c.fetchone()
    c.execute("SELECT COUNT(*) FROM trades WHERE status!='Completed' AND status!='Cancelled'")
    active_trades = c.fetchone()[0]
    conn.close()
    
    completed_trades = completed_data[0] if completed_data[0] else 0
    total_volume = completed_data[1] if completed_data[1] else 0.0
    
    return completed_trades, total_volume, active_trades
    
