"""
app.py — Professional Telegram Escrow Bot.
Compatible with Render free tier.
"""

import logging
import sys
import threading
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

import database as db
from config import BOT_TOKEN
from escrow import (
    cmd_start, cmd_create, button_handler, receive_tx, cancel_pay, WAITING_FOR_TX,
    cmd_release, cmd_refund, cmd_ban, cmd_stats
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Dummy Web Server for Render ───────────────────────────────────────────────
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Escrow Bot is Secure and Running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    db.init_db()
    logger.info("Database initialized.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for Payment TX Hash
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAITING_FOR_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tx)]
        },
        fallbacks=[CommandHandler('cancel_pay', cancel_pay)],
        allow_reentry=True
    )

    # Basic Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("create", cmd_create))
    
    # Admin Commands
    app.add_handler(CommandHandler("release", cmd_release))
    app.add_handler(CommandHandler("refund", cmd_refund))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Add Conversation/Button Handler
    app.add_handler(conv_handler)

    logger.info("Starting dummy web server for Render...")
    threading.Thread(target=run_dummy_server, daemon=True).start()

    logger.info("Bot starting — polling…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
