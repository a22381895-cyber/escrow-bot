import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from config import ADMIN_ID, ESCROW_WALLET, FEE_PERCENTAGE, SUPPORT_CONTACT

logger = logging.getLogger(__name__)

WAITING_FOR_TX = 1

async def check_ban(update: Update) -> bool:
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.effective_message.reply_text("⛔ You are banned from using this service.")
        return True
    return False

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): return
    
    text = (
        "🔐 <b>Gross Escrow — Secure Trade Protection</b>\n\n"
        "We safely hold funds between buyer and seller to prevent scams.\n\n"
        "✅ <b>Funds locked</b> before delivery\n"
        "✅ <b>Seller paid</b> only after confirmation\n"
        "✅ <b>Admin dispute</b> protection\n\n"
        "⚙️ <b>How to start:</b>\n"
        "Send: <code>/create &lt;amount&gt; &lt;@seller_username&gt;</code>\n"
        "Example: <code>/create 100 @johndoe</code>\n\n"
        f"🎧 Support: {SUPPORT_CONTACT}\n\n"
        "⚠️ <i>Notice: Admin will NEVER DM you first. Never pay outside this bot.</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 View Statistics", callback_data="view_stats")],
        [InlineKeyboardButton("🎧 Contact Support", url=f"https://t.me/{SUPPORT_CONTACT.replace('@', '')}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def cmd_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): return
    
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ <b>Format error</b>\nUse: <code>/create &lt;amount&gt; &lt;@seller_username&gt;</code>", parse_mode="HTML")
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
    
    text = (
        f"🔒 <b>TRADE OPENED: #{trade_id}</b>\n\n"
        f"👤 <b>Buyer:</b> @{buyer_username}\n"
        f"🏪 <b>Seller:</b> @{seller_username}\n"
        f"💰 <b>Amount:</b> {amount} USDT\n"
        f"💸 <b>Fee ({int(FEE_PERCENTAGE*100)}%):</b> {fee} USDT\n"
        f"💳 <b>Total to Send:</b> {total_to_pay} USDT\n\n"
        f"📊 <b>Status:</b> 🟡 Waiting for payment\n\n"
        f"💳 <b>Payment Address (USDT BEP-20):</b>\n<code>{ESCROW_WALLET}</code>\n\n"
        "⚠️ <i>ONLY send USDT BEP-20 to this exact address. Once sent, click the button below.</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ I Sent Payment", callback_data=f"pay_{trade_id}")],
        [InlineKeyboardButton("❌ Cancel Trade", callback_data=f"cancel_{trade_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "view_stats":
        comp, vol, act = db.get_stats()
        text = (
            "📊 <b>Gross Escrow Statistics</b>\n\n"
            f"✅ <b>Completed Trades:</b> {comp}\n"
            f"💰 <b>Volume Secured:</b> {vol:,.2f} USDT\n"
            f"🔄 <b>Active Trades:</b> {act}\n\n"
            "🛡️ <i>100% Safe & Secure</i>"
        )
        await query.message.reply_text(text, parse_mode="HTML")
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
        await query.edit_message_text(f"🚫 <b>Trade #{trade_id} Cancelled by Buyer.</b>", parse_mode="HTML")
        return ConversationHandler.END

    if data.startswith("pay_"):
        trade_id = int(data.split("_")[1])
        trade = db.get_trade(trade_id)
        if not trade or trade['buyer_id'] != update.effective_user.id:
            await query.message.reply_text("❌ Not your trade.")
            return ConversationHandler.END
            
        context.user_data['paying_trade_id'] = trade_id
        await query.message.reply_text(
            f"📥 <b>Please reply to this message with your Transaction Hash (TX Hash) for Trade #{trade_id}.</b>\n\n"
            "Type /cancel_pay to abort.", 
            parse_mode="HTML"
        )
        return WAITING_FOR_TX
        
    if data.startswith("confirm_"):
        trade_id = int(data.split("_")[1])
        trade = db.get_trade(trade_id)
        if trade['buyer_id'] != update.effective_user.id:
            await query.message.reply_text("❌ Only the buyer can confirm delivery.")
            return ConversationHandler.END
            
        db.update_trade_status(trade_id, "Completed")
        await query.edit_message_text(f"✅ <b>Trade #{trade_id} Completed.</b>\nFunds will be released to @{trade['seller_username']} shortly.", parse_mode="HTML")
        return ConversationHandler.END
        
    if data.startswith("dispute_"):
        trade_id = int(data.split("_")[1])
        db.update_trade_status(trade_id, "Disputed")
        await query.edit_message_text(f"⚖️ <b>Dispute Opened for Trade #{trade_id}.</b>\nAdmin has been notified and will resolve this.", parse_mode="HTML")
        return ConversationHandler.END

async def receive_tx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_hash = update.message.text
    trade_id = context.user_data.get('paying_trade_id')
    
    if len(tx_hash) < 10:
        await update.message.reply_text("❌ Invalid TX Hash format. Please try again or /cancel_pay.")
        return WAITING_FOR_TX
        
    db.update_trade_status(trade_id, "Payment Under Review", tx_hash)
    
    keyboard = [
        [InlineKeyboardButton("📦 Confirm Delivery", callback_data=f"confirm_{trade_id}")],
        [InlineKeyboardButton("⚖️ Open Dispute", callback_data=f"dispute_{trade_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⏳ <b>Payment Under Review for Trade #{trade_id}</b>\n\n"
        f"TX Hash: <code>{tx_hash}</code>\n\n"
        "Seller should now deliver the product. Once received, click <b>Confirm Delivery</b>.",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    context.user_data.pop('paying_trade_id', None)
    return ConversationHandler.END

async def cancel_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('paying_trade_id', None)
    await update.message.reply_text("Payment submission cancelled.")
    return ConversationHandler.END

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
        "👑 <b>Admin Dashboard</b>\n\n"
        f"✅ Completed Trades: {comp}\n"
        f"💰 Total Volume: {vol:,.2f} USDT\n"
        f"🔄 Active Trades: {act}\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")
