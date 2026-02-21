import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from config import ADMIN_ID, ESCROW_WALLET, FEE_PERCENTAGE, SUPPORT_CONTACT

logger = logging.getLogger(__name__)

# State for ConversationHandler
WAITING_FOR_TX = 1

# ─── MIDDLEWARE (Anti-ban check) ──────────────────────────────────────────────
async def check_ban(update: Update) -> bool:
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.effective_message.reply_text("⛔ You are banned from using this service.")
        return True
    return False

# ─── USER COMMANDS ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): return
    
    # Kwalliyar Trust & Branding kamar yadda ka bukata
    text = (
        "🔐 *Gross Escrow — Secure Trade Protection*\n\n"
        "We safely hold funds between buyer and seller to prevent scams.\n\n"
        "✅ *Funds locked* before delivery\n"
        "✅ *Seller paid* only after confirmation\n"
        "✅ *Admin dispute* protection\n\n"
        "⚙️ *How to start:*\n"
        "Send: `/create <amount> <@seller_username>`\n"
        "Example: `/create 100 @johndoe`\n\n"
        f"🎧 Support: {SUPPORT_CONTACT}\n\n"
        "⚠️ _Notice: Admin will NEVER DM you first. Never pay outside this bot._"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 View Statistics", callback_data="view_stats")],
        [InlineKeyboardButton("🎧 Contact Support", url=f"https://t.me/{SUPPORT_CONTACT.replace('@', '')}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def cmd_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): return
    
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ *Format error*\nUse: `/create <amount> <@seller_username>`", parse_mode="Markdown")
        return
        
    try:
        amount = float(args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return
        
    seller_username = args[1].replace("@", "")
    buyer = update.effective_user
    buyer_username = buyer.username or str(buyer.id)
    
    if seller_username.lower() == buyer_username.lower():
        await update.message.reply_text("❌ You cannot trade with yourself.")
        return

    fee = amount * FEE_PERCENTAGE
    total_to_pay = amount + fee
    
    trade_id = db.create_trade(buyer.id, buyer_username, seller_username, amount, fee)
    
    # Professional Trade Formatting & Wallet reveal
    text = (
        f"🔒 *TRADE OPENED: #{trade_id}*\n\n"
        f"👤 *Buyer:* @{buyer_username}\n"
        f"🏪 *Seller:* @{seller_username}\n"
        f"💰 *Amount:* {amount} USDT\n"
        f"💸 *Fee ({int(FEE_PERCENTAGE*100)}%):* {fee} USDT\n"
        f"💳 *Total to Send:* {total_to_pay} USDT\n\n"
        f"📊 *Status:* 🟡 Waiting for payment\n\n"
        f"💳 *Payment Address (USDT BEP-20):*\n`{ESCROW_WALLET}`\n\n"
        "⚠️ _ONLY send USDT BEP-20 to this exact address. Once sent, click the button below._"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ I Sent Payment", callback_data=f"pay_{trade_id}")],
        [InlineKeyboardButton("❌ Cancel Trade", callback_data=f"cancel_{trade_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# ─── INTERACTIVE BUTTON CALLBACKS ─────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "view_stats":
        comp, vol, act = db.get_stats()
        text = (
            "📊 *Gross Escrow Statistics*\n\n"
            f"✅ *Completed Trades:* {comp}\n"
            f"💰 *Volume Secured:* {vol:,.2f} USDT\n"
            f"🔄 *Active Trades:* {act}\n\n"
            "🛡️ _100% Safe & Secure_"
        )
        await query.message.reply_text(text, parse_mode="Markdown")
        return ConversationHandler.END

    if data.startswith("cancel_"):
        trade_id = int(data.split("_")[1])
        trade = db.get_trade(trade_id)
        if not trade or trade['buyer_id'] != update.effective_user.id:
            await query.message.reply_text("❌ Not your trade.")
            return ConversationHandler.END
            
        if trade['status'] != 'Waiting for payment':
            await query.message.reply_text("❌ Cannot cancel this trade anymore.")
            return ConversationHandler.END
            
        db.update_trade_status(trade_id, "Cancelled")
        await query.edit_message_text(f"🚫 *Trade #{trade_id} Cancelled by Buyer.*", parse_mode="Markdown")
        return ConversationHandler.END

    if data.startswith("pay_"):
        trade_id = int(data.split("_")[1])
        trade = db.get_trade(trade_id)
        if not trade or trade['buyer_id'] != update.effective_user.id:
            await query.message.reply_text("❌ Not your trade.")
            return ConversationHandler.END
            
        context.user_data['paying_trade_id'] = trade_id
        await query.message.reply_text(
            f"📥 *Please reply to this message with your Transaction Hash (TX Hash) for Trade #{trade_id}.*\n\n"
            "Type /cancel_pay to abort.", 
            parse_mode="Markdown"
        )
        return WAITING_FOR_TX
        
    if data.startswith("confirm_"):
        trade_id = int(data.split("_")[1])
        trade = db.get_trade(trade_id)
        # Only buyer can confirm delivery
        if trade['buyer_id'] != update.effective_user.id:
            await query.message.reply_text("❌ Only the buyer can confirm delivery.")
            return ConversationHandler.END
            
        db.update_trade_status(trade_id, "Completed")
        await query.edit_message_text(f"✅ *Trade #{trade_id} Completed.*\nFunds will be released to @{trade['seller_username']} shortly.", parse_mode="Markdown")
        return ConversationHandler.END
        
    if data.startswith("dispute_"):
        trade_id = int(data.split("_")[1])
        db.update_trade_status(trade_id, "Disputed")
        await query.edit_message_text(f"⚖️ *Dispute Opened for Trade #{trade_id}.*\nAdmin has been notified and will resolve this.", parse_mode="Markdown")
        return ConversationHandler.END

# ─── PAYMENT FLOW (Conversation) ─────────────────────────────────────────────

async def receive_tx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_hash = update.message.text
    trade_id = context.user_data.get('paying_trade_id')
    
    if len(tx_hash) < 10:  # Basic validation
        await update.message.reply_text("❌ Invalid TX Hash format. Please try again or /cancel_pay.")
        return WAITING_FOR_TX
        
    db.update_trade_status(trade_id, "Payment Under Review", tx_hash)
    
    keyboard = [
        [InlineKeyboardButton("📦 Confirm Delivery", callback_data=f"confirm_{trade_id}")],
        [InlineKeyboardButton("⚖️ Open Dispute", callback_data=f"dispute_{trade_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⏳ *Payment Under Review for Trade #{trade_id}*\n\n"
        f"TX Hash: `{tx_hash}`\n\n"
        "Seller should now deliver the product. Once received, click *Confirm Delivery*.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    context.user_data.pop('paying_trade_id', None)
    return ConversationHandler.END

async def cancel_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('paying_trade_id', None)
    await update.message.reply_text("Payment submission cancelled.")
    return ConversationHandler.END

# ─── ADMIN COMMANDS ───────────────────────────────────────────────────────────

async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        trade_id = int(context.args[0])
        db.update_trade_status(trade_id, "Completed")
        await update.message.reply_text(f"✅ Trade #{trade_id} manually marked as Completed (Released).")
    except:
        await update.message.reply_text("Format: `/release <trade_id>`")

async def cmd_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        trade_id = int(context.args[0])
        db.update_trade_status(trade_id, "Refunded")
        await update.message.reply_text(f"🔙 Trade #{trade_id} marked as Refunded.")
    except:
        await update.message.reply_text("Format: `/refund <trade_id>`")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        user_id = int(context.args[0])
        db.ban_user(user_id)
        await update.message.reply_text(f"🔨 User {user_id} has been banned globally.")
    except:
        await update.message.reply_text("Format: `/ban <user_id>`")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comp, vol, act = db.get_stats()
    text = (
        "👑 *Admin Dashboard*\n\n"
        f"✅ Completed Trades: {comp}\n"
        f"💰 Total Volume: {vol:,.2f} USDT\n"
        f"🔄 Active Trades: {act}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    
