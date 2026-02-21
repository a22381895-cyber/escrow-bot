import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_ID: int = int(os.environ["ADMIN_ID"])

# ── BSC / BscScan ─────────────────────────────────────────────────────────────
BSC_ADDRESS: str = os.environ["BSC_ADDRESS"].lower()          # escrow wallet (lowercase)
BSC_API_KEY: str = os.environ["BSC_API_KEY"]

# USDT BEP-20 contract on BSC mainnet (official, checksummed)
USDT_CONTRACT: str = "0x55d398326f99059ff775485246999027b3197955"

BSCSCAN_API_URL: str = "https://api.bscscan.com/api"

# ── Commission ────────────────────────────────────────────────────────────────
COMMISSION_PERCENT: float = float(os.getenv("COMMISSION_PERCENT", "5"))

# ── Misc ──────────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "escrow.db")

# BEP-20 USDT has 18 decimals
USDT_DECIMALS: int = 18
