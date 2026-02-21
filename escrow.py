"""
Core escrow command handlers.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from config import BSC_ADDRESS, ADMIN_ID, COMMISSION_PERCENT
from utils import (
    generate_trade_id,
    calculate_amounts,
    verify_transaction,
    trade_summary,
    fmt_usdt,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"👋 Welcome, {user.first_name}!\n\n"
        "🔐 <b>USDT BEP-20 Escrow Bot</b>\n\n"
        "I hold funds safely between buyer and seller.\n\n"
        "<b>Commands:</b>\n"
        "  /create &lt;amount&gt; &lt;seller_username&gt;\n"
        "    — Open a new escrow trade\n\n"
        "  /paid &lt;trade_id&gt; &lt;tx_hash&gt;\n"
        "    — Submit payment proof\n\n"
        "  /status &lt;trade_id&gt;\n"
        "    — Check trade status\n\n"
        "  /confirm &lt;trade_id&gt;\n"
        "    — Seller confirms delivery\n\n"
        "  /dispute &lt;trade_id&gt; &lt;reason&gt;\n"
        "    — Raise a dispute\n\n"
        "  /cancel &lt;trade_id&gt;\n"
        "    — Cancel an awaiting trade\n\n"
        f"💸 Commission: <b>{COMMISSION_PERCENT}%</b> added to buyer's payment\n"
        f"🏦 Escrow wallet: <code>{BSC_ADDRESS}</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────────
# /create <amount> <seller_username>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: /create <amount> <seller_username>\n"
            "Example: /create 100 john_doe"
        )
        return

    # Validate amount
    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Amount must be a positive number.")
        return

    seller_username = args[1].lstrip("@").strip()
    if not seller_username:
        await update.message.reply_text("❌ Please provide a valid seller username.")
        return

    if seller_username.lower() == (user.username or "").lower():
        await update.message.reply_text("❌ You cannot be both buyer and seller.")
        return

    amount_usdt, commission, total_required = calculate_amounts(amount)
    trade_id = generate_trade_id()

    db.create_trade(
        trade_id=trade_id,
        buyer_id=user.id,
        buyer_username=user.username,
        seller_username=seller_username,
        amount_usdt=amount_usdt,
        commission=commission,
        total_required=total_required,
    )

    text = (
        f"✅ <b>Escrow Trade Created!</b>\n\n"
        f"🆔 Trade ID   : <code>{trade_id}</code>\n"
        f"📦 Amount     : {fmt_usdt(amount_usdt)}\n"
        f"💸 Commission : {fmt_usdt(commission)} ({COMMISSION_PERCENT}%)\n"
        f"💰 <b>You must send: {fmt_usdt(total_required)}</b>\n\n"
        f"👤 Seller     : @{seller_username}\n\n"
        f"<b>Step 1:</b> Send exactly <b>{fmt_usdt(total_required)}</b> USDT (BEP-20) to:\n"
        f"<code>{BSC_ADDRESS}</code>\n\n"
        f"<b>Step 2:</b> After sending, run:\n"
        f"<code>/paid {trade_id} YOUR_TX_HASH</code>\n\n"
        "⚠️ Send only USDT BEP-20 (BSC network). Other tokens will be lost."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────────
# /paid <trade_id> <tx_hash>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: /paid <trade_id> <tx_hash>\n"
            "Example: /paid ESC-A3F9B2 0xabc123..."
        )
        return

    trade_id = args[0].upper().strip()
    tx_hash = args[1].strip()

    if not tx_hash.startswith("0x") or len(tx_hash) < 60:
        await update.message.reply_text("❌ Invalid TX hash format. It should start with 0x and be 66 chars.")
        return

    # Load trade
    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade <code>{trade_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    # Ownership check
    if trade["buyer_id"] != user.id:
        await update.message.reply_text("❌ Only the buyer of this trade can submit payment.")
        return

    # Status check
    if trade["status"] != "AWAITING_PAYMENT":
        await update.message.reply_text(
            f"❌ This trade is already in status <b>{trade['status']}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Duplicate TX check
    if db.is_tx_used(tx_hash):
        await update.message.reply_text(
            "❌ This transaction hash has already been used in another trade."
        )
        return

    await update.message.reply_text("⏳ Verifying your transaction on BscScan… please wait.")

    result = await verify_transaction(tx_hash, trade["total_required"])

    if not result["valid"]:
        await update.message.reply_text(
            f"❌ <b>Verification Failed</b>\n\n{result['reason']}",
            parse_mode=ParseMode.HTML,
        )
        return

    # Mark TX as used and update trade
    db.mark_tx_used(tx_hash, trade_id)
    db.update_trade_status(trade_id, "PAYMENT_VERIFIED", tx_hash=tx_hash)

    text = (
        f"✅ <b>Payment Verified!</b>\n\n"
        f"🆔 Trade ID : <code>{trade_id}</code>\n"
        f"💰 Amount   : {fmt_usdt(result['amount'])}\n"
        f"🔗 TX Hash  : <code>{tx_hash}</code>\n\n"
        f"The seller <b>@{trade['seller_username']}</b> must now confirm delivery.\n"
        f"Seller runs: <code>/confirm {trade_id}</code>\n\n"
        "If there's a problem, either party can run:\n"
        f"<code>/dispute {trade_id} your reason here</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Notify admin
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Payment Verified</b>\n\n"
            f"Trade: <code>{trade_id}</code>\n"
            f"Buyer: @{user.username or user.id}\n"
            f"Seller: @{trade['seller_username']}\n"
            f"Amount: {fmt_usdt(result['amount'])}\n"
            f"TX: <code>{tx_hash}</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass  # Admin notification is non-critical


# ──────────────────────────────────────────────────────────────────────────────
# /status <trade_id>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /status <trade_id>")
        return

    trade_id = args[0].upper().strip()
    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade <code>{trade_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text(trade_summary(trade), parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────────
# /confirm <trade_id>   (seller confirms delivery)
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /confirm <trade_id>")
        return

    trade_id = args[0].upper().strip()
    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade <code>{trade_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    # Only the seller (matched by username) can confirm
    seller_uname = (user.username or "").lower()
    if seller_uname != trade["seller_username"].lower():
        await update.message.reply_text("❌ Only the seller of this trade can confirm delivery.")
        return

    if trade["status"] != "PAYMENT_VERIFIED":
        await update.message.reply_text(
            f"❌ Cannot confirm — trade status is <b>{trade['status']}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    db.update_trade_status(trade_id, "COMPLETED", seller_id=user.id)

    text = (
        f"🎉 <b>Trade Completed!</b>\n\n"
        f"🆔 Trade ID : <code>{trade_id}</code>\n"
        f"✅ Seller @{trade['seller_username']} has confirmed delivery.\n"
        f"💰 {fmt_usdt(trade['amount_usdt'])} released to seller.\n\n"
        "Thank you for using our escrow service!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Notify admin
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"✅ <b>Trade Completed</b>\n\nTrade: <code>{trade_id}</code>\nSeller: @{user.username}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# /dispute <trade_id> <reason…>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_dispute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: /dispute <trade_id> <reason>\n"
            "Example: /dispute ESC-A3F9B2 Seller did not deliver the item"
        )
        return

    trade_id = args[0].upper().strip()
    reason = " ".join(args[1:]).strip()

    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade <code>{trade_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    # Must be buyer or seller
    buyer_match = trade["buyer_id"] == user.id
    seller_match = (user.username or "").lower() == trade["seller_username"].lower()
    if not buyer_match and not seller_match:
        await update.message.reply_text("❌ You are not a party to this trade.")
        return

    if trade["status"] in ("COMPLETED", "CANCELLED"):
        await update.message.reply_text(
            f"❌ Cannot dispute a trade with status <b>{trade['status']}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    db.update_trade_status(trade_id, "DISPUTED", dispute_reason=reason)

    await update.message.reply_text(
        f"⚠️ <b>Dispute Raised</b>\n\n"
        f"🆔 Trade ID : <code>{trade_id}</code>\n"
        f"📝 Reason   : {reason}\n\n"
        "An admin will review and contact both parties.",
        parse_mode=ParseMode.HTML,
    )

    # Notify admin
    try:
        role = "Buyer" if buyer_match else "Seller"
        await context.bot.send_message(
            ADMIN_ID,
            f"🚨 <b>DISPUTE RAISED</b>\n\n"
            f"Trade: <code>{trade_id}</code>\n"
            f"{role}: @{user.username or user.id}\n"
            f"Reason: {reason}\n\n"
            f"Review with /admin_trade {trade_id}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# /cancel <trade_id>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /cancel <trade_id>")
        return

    trade_id = args[0].upper().strip()
    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade <code>{trade_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    if trade["buyer_id"] != user.id:
        await update.message.reply_text("❌ Only the buyer can cancel this trade.")
        return

    if trade["status"] != "AWAITING_PAYMENT":
        await update.message.reply_text(
            f"❌ Cannot cancel a trade with status <b>{trade['status']}</b>. "
            "Raise a /dispute instead.",
            parse_mode=ParseMode.HTML,
        )
        return

    db.update_trade_status(trade_id, "CANCELLED")
    await update.message.reply_text(
        f"🚫 Trade <code>{trade_id}</code> has been <b>cancelled</b>.",
        parse_mode=ParseMode.HTML,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Admin: /admin_trades   — list recent trades
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_admin_trades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    trades = db.get_all_trades(limit=30)
    if not trades:
        await update.message.reply_text("No trades yet.")
        return

    lines = ["<b>📋 Last 30 Trades</b>\n"]
    for t in trades:
        status_icon = {
            "AWAITING_PAYMENT": "⏳",
            "PAYMENT_VERIFIED": "💳",
            "COMPLETED": "✅",
            "DISPUTED": "🚨",
            "CANCELLED": "🚫",
        }.get(t["status"], "❓")

        lines.append(
            f"{status_icon} <code>{t['trade_id']}</code> | "
            f"{fmt_usdt(t['total_required'])} | "
            f"@{t['seller_username']} | "
            f"{t['status']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────────
# Admin: /admin_trade <trade_id>   — full detail
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_admin_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /admin_trade <trade_id>")
        return

    trade_id = args[0].upper().strip()
    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade {trade_id} not found.")
        return

    await update.message.reply_text(trade_summary(trade), parse_mode=ParseMode.HTML)


# ──────────────────────────────────────────────────────────────────────────────
# Admin: /admin_resolve <trade_id> <buyer|seller>
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_admin_resolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /admin_resolve <trade_id> <buyer|seller>")
        return

    trade_id = args[0].upper().strip()
    resolution = args[1].lower().strip()

    if resolution not in ("buyer", "seller"):
        await update.message.reply_text("❌ Resolution must be 'buyer' or 'seller'.")
        return

    trade = db.get_trade(trade_id)
    if not trade:
        await update.message.reply_text(f"❌ Trade {trade_id} not found.")
        return

    if trade["status"] != "DISPUTED":
        await update.message.reply_text("❌ Trade is not in DISPUTED status.")
        return

    new_status = "COMPLETED" if resolution == "seller" else "CANCELLED"
    db.update_trade_status(trade_id, new_status)

    await update.message.reply_text(
        f"✅ Trade <code>{trade_id}</code> resolved in favour of <b>{resolution}</b>. "
        f"New status: <b>{new_status}</b>",
        parse_mode=ParseMode.HTML,
    )
