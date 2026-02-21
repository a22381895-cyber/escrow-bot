"""
Utility helpers: BscScan API calls, amount formatting, trade-ID generation.
"""

import logging
import uuid
import aiohttp

from config import (
    BSC_API_KEY,
    BSC_ADDRESS,
    BSCSCAN_API_URL,
    USDT_CONTRACT,
    USDT_DECIMALS,
    COMMISSION_PERCENT,
)

logger = logging.getLogger(__name__)


# ── Trade ID ──────────────────────────────────────────────────────────────────

def generate_trade_id() -> str:
    """Return a short uppercase trade ID like  ESC-A3F9B2."""
    return "ESC-" + uuid.uuid4().hex[:6].upper()


# ── Commission calc ───────────────────────────────────────────────────────────

def calculate_amounts(amount_usdt: float) -> tuple[float, float, float]:
    """
    Returns (amount, commission, total_required).
    Buyer must send  total_required  so that after commission is deducted
    the seller receives  amount.
    """
    commission = round(amount_usdt * COMMISSION_PERCENT / 100, 6)
    total_required = round(amount_usdt + commission, 6)
    return amount_usdt, commission, total_required


# ── BscScan verification ──────────────────────────────────────────────────────

async def verify_transaction(tx_hash: str, expected_amount_usdt: float) -> dict:
    """
    Verify a USDT BEP-20 transfer on BSC via BscScan API.

    Returns a dict:
        {
            "valid": bool,
            "reason": str,          # only set when valid=False
            "from_address": str,
            "to_address": str,
            "amount": float,
            "contract": str,
        }
    """
    result = {
        "valid": False,
        "reason": "",
        "from_address": "",
        "to_address": "",
        "amount": 0.0,
        "contract": "",
    }

    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": USDT_CONTRACT,
        "address": BSC_ADDRESS,
        "apikey": BSC_API_KEY,
        "page": 1,
        "offset": 100,  # look at the last 100 USDT txns to the escrow wallet
        "sort": "desc",
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(BSCSCAN_API_URL, params=params) as resp:
                data = await resp.json(content_type=None)
    except aiohttp.ClientError as exc:
        logger.error("BscScan request failed: %s", exc)
        result["reason"] = "Network error contacting BscScan. Please retry."
        return result

    if data.get("status") != "1" or not data.get("result"):
        logger.warning("BscScan returned non-1 status: %s", data)
        result["reason"] = "BscScan returned no transactions. TX may not be confirmed yet."
        return result

    # Find our specific TX hash in the results
    target_hash = tx_hash.lower().strip()
    matched = None
    for tx in data["result"]:
        if tx.get("hash", "").lower() == target_hash:
            matched = tx
            break

    if matched is None:
        result["reason"] = (
            "Transaction not found among recent USDT transfers to the escrow wallet. "
            "Ensure it is confirmed on BSC and is a USDT BEP-20 transfer."
        )
        return result

    # ── Validate contract address ──────────────────────────────────────────────
    contract = matched.get("contractAddress", "").lower()
    if contract != USDT_CONTRACT.lower():
        result["reason"] = f"Wrong token contract: {contract}. Only USDT BEP-20 accepted."
        return result

    # ── Validate to-address ────────────────────────────────────────────────────
    to_addr = matched.get("to", "").lower()
    if to_addr != BSC_ADDRESS.lower():
        result["reason"] = (
            f"Payment sent to wrong address: {to_addr}. "
            f"Expected: {BSC_ADDRESS}"
        )
        return result

    # ── Validate amount ────────────────────────────────────────────────────────
    raw_value = int(matched.get("value", "0"))
    actual_amount = raw_value / (10 ** USDT_DECIMALS)

    # Allow a 0.5% tolerance for rounding / dust
    tolerance = expected_amount_usdt * 0.005
    if actual_amount < (expected_amount_usdt - tolerance):
        result["reason"] = (
            f"Insufficient amount. Expected ≥ {expected_amount_usdt:.2f} USDT, "
            f"received {actual_amount:.6f} USDT."
        )
        return result

    result["valid"] = True
    result["from_address"] = matched.get("from", "")
    result["to_address"] = to_addr
    result["amount"] = actual_amount
    result["contract"] = contract
    return result


# ── Formatting ─────────────────────────────────────────────────────────────────

def fmt_usdt(amount: float) -> str:
    return f"{amount:.2f} USDT"


def trade_summary(trade) -> str:
    """Return a human-readable summary of a trade row."""
    lines = [
        f"🆔 Trade ID : <code>{trade['trade_id']}</code>",
        f"📦 Amount   : {fmt_usdt(trade['amount_usdt'])}",
        f"💸 Commission: {fmt_usdt(trade['commission'])} ({COMMISSION_PERCENT}%)",
        f"💰 Total Due : <b>{fmt_usdt(trade['total_required'])}</b>",
        f"👤 Seller   : @{trade['seller_username']}",
        f"📊 Status   : <b>{trade['status']}</b>",
    ]
    if trade["tx_hash"]:
        lines.append(f"🔗 TX Hash  : <code>{trade['tx_hash']}</code>")
    if trade["dispute_reason"]:
        lines.append(f"⚠️ Dispute  : {trade['dispute_reason']}")
    lines.append(f"🕐 Created  : {trade['created_at']} UTC")
    return "\n".join(lines)
