"""
app.py — Telegram Escrow Bot entry point.
Uses polling (no webhook needed), compatible with Render free tier.
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
    ContextTypes,
)

import database as db
from config import BOT_TOKEN
from escrow import (
    cmd_start,
    cmd_create,
    cmd_paid,
    cmd_status,
    cmd_confirm,
    cmd_dispute,
    cmd_cancel,
    cmd_admin_trades,
    cmd_admin_trade,
    cmd_admin_resolve,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Dummy Web Server for Render ───────────────────────────────────────────────
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running successfully!")

def run_dummy_server():
    # Render tana bayar da PORT a matsayin environment variable
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()


# ── Error handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An internal error occurred. Please try again or contact support."
            )
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    # Initialise DB
    db.init_db()
    logger.info("Database ready.")

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()

    # ── User commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("create",  cmd_create))
    app.add_handler(CommandHandler("paid",    cmd_paid))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("confirm", cmd_confirm))
    app.add_handler(CommandHandler("dispute", cmd_dispute))
    app.add_handler(CommandHandler("cancel",  cmd_cancel))

    # ── Admin commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin_trades",  cmd_admin_trades))
    app.add_handler(CommandHandler("admin_trade",   cmd_admin_trade))
    app.add_handler(CommandHandler("admin_resolve", cmd_admin_resolve))

    # ── Error handler ──────────────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    # ── Start the dummy server in a background thread ──────────────────────────
    logger.info("Starting dummy web server for Render...")
    threading.Thread(target=run_dummy_server, daemon=True).start()

    logger.info("Bot starting — polling…")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,       # ignore updates that arrived while offline
    )


if __name__ == "__main__":
    main()
        
