# 🔐 USDT BEP-20 Telegram Escrow Bot

A production-ready Telegram escrow bot that safely holds **USDT (BEP-20)** between a
buyer and a seller. Payments are verified on-chain via the **BscScan API**. Runs
completely free on **Render.com** using polling — no VPS, no custom domain, no webhook.

---

## 📁 Project Structure

```
escrow-bot/
├── app.py           ← Entry point, polling setup, error handler
├── config.py        ← All environment variables in one place
├── database.py      ← Thread-safe SQLite helpers
├── escrow.py        ← All command handlers (user + admin)
├── utils.py         ← BscScan verification, amounts, formatting
├── requirements.txt ← Pinned Python dependencies
├── render.yaml      ← Render.com deployment config
├── .env.example     ← Template — copy to .env and fill in values
├── .gitignore       ← Prevents secrets from being committed
└── README.md        ← This file
```

---

## ⚙️ Environment Variables

Set these in your Render dashboard (never commit real values to GitHub).

| Variable             | Required | Description                                                  |
|----------------------|----------|--------------------------------------------------------------|
| `BOT_TOKEN`          | ✅ Yes   | Telegram bot token — get from @BotFather                     |
| `BSC_ADDRESS`        | ✅ Yes   | Your BSC escrow wallet address where buyers send USDT        |
| `BSC_API_KEY`        | ✅ Yes   | BscScan API key — free at bscscan.com/apis                   |
| `ADMIN_ID`           | ✅ Yes   | Your Telegram numeric user ID (NOT username)                 |
| `COMMISSION_PERCENT` | ⚙️ Optional | Commission % added to buyer's total. Default: `5`         |
| `DATABASE_PATH`      | ⚙️ Optional | Path for SQLite file. Default: `escrow.db` (use `/data/escrow.db` on Render) |

### How to get each value

**BOT_TOKEN**
1. Open Telegram → search `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you (looks like `123456:ABC-DEF...`)

**BSC_ADDRESS**
- Open MetaMask or Trust Wallet → copy your BEP-20 wallet address
- This is the wallet buyers will send USDT to
- ⚠️ Back up the private key — you will manually release funds from here

**BSC_API_KEY**
1. Go to [bscscan.com](https://bscscan.com) → Register a free account
2. My Account → API Keys → Add
3. Copy the generated key

**ADMIN_ID**
1. Open Telegram → search `@userinfobot`
2. Send `/start` — it replies with your numeric ID (e.g. `123456789`)
3. Copy that number — **not** your @username

---

## 🤖 User Commands

| Command | Description |
|---|---|
| `/start` | Show welcome message and full command list |
| `/create <amount> <seller_username>` | Open a new escrow trade as the buyer |
| `/paid <trade_id> <tx_hash>` | Submit payment proof — triggers live BscScan verification |
| `/status <trade_id>` | Check the current state of any trade |
| `/confirm <trade_id>` | Seller confirms delivery — marks trade as complete |
| `/dispute <trade_id> <reason>` | Raise a dispute — immediately alerts the admin |
| `/cancel <trade_id>` | Cancel a trade (only allowed before payment is made) |

### Usage Examples

```
/create 100 john_doe
/paid ESC-A3F9B2 0xabc123def456...
/status ESC-A3F9B2
/confirm ESC-A3F9B2
/dispute ESC-A3F9B2 Seller did not deliver the item
/cancel ESC-A3F9B2
```

---

## 🔑 Admin Commands

Only works for the Telegram account whose ID matches `ADMIN_ID`.

| Command | Description |
|---|---|
| `/admin_trades` | List the last 30 trades with status icons |
| `/admin_trade <trade_id>` | View full details of one specific trade |
| `/admin_resolve <trade_id> <buyer\|seller>` | Resolve a disputed trade in favour of buyer or seller |

### Usage Examples

```
/admin_trades
/admin_trade ESC-A3F9B2
/admin_resolve ESC-A3F9B2 seller
/admin_resolve ESC-A3F9B2 buyer
```

---

## 📊 Trade Statuses

```
AWAITING_PAYMENT  → Trade created. Waiting for buyer to send USDT.
PAYMENT_VERIFIED  → Payment confirmed on BscScan. Waiting for seller to confirm delivery.
COMPLETED         → Seller confirmed delivery. Trade closed successfully.
DISPUTED          → A party raised a dispute. Admin intervention required.
CANCELLED         → Trade was cancelled before payment was made.
```

### Status Flow

```
AWAITING_PAYMENT
      │
      ├─ /paid + BscScan OK ──→  PAYMENT_VERIFIED
      │                                │
      ├─ /cancel ──→ CANCELLED         ├─ /confirm ──→ COMPLETED
      │                                │
      └─ /dispute ──→ DISPUTED         └─ /dispute ──→ DISPUTED
                           │
                    /admin_resolve ──→ COMPLETED or CANCELLED
```

---

## 🔍 Payment Verification Logic

When a buyer calls `/paid <trade_id> <tx_hash>`, the bot performs these checks in order:

### 1. Duplicate Transaction Check
The TX hash is looked up in the `used_transactions` table. If it has been used in
any previous trade, the payment is rejected immediately — preventing reuse attacks.

### 2. BscScan API Query
The bot calls the BscScan `tokentx` endpoint, fetching the last 100 USDT BEP-20
transfers **to** the escrow wallet address. This scopes the search to relevant
transactions only.

### 3. TX Hash Match
The specific transaction hash submitted by the buyer must be found in those results.
If not found, the trade remains `AWAITING_PAYMENT` and the user is told to wait for
confirmation (typically 15–30 seconds on BSC).

### 4. Contract Address Verification
```
Expected: 0x55d398326f99059ff775485246999027b3197955
```
The `contractAddress` field of the matched transaction must equal the official USDT
BEP-20 contract on BSC mainnet. Any other token (BUSD, fake USDT, etc.) is rejected.

### 5. To-Address Verification
The `to` field of the transaction must exactly match `BSC_ADDRESS` (your escrow wallet).
Prevents attackers from submitting a valid USDT TX that went to a different address.

### 6. Amount Verification
The transaction `value` is decoded from raw 18-decimal integer to USDT float and
compared to `total_required` (amount + commission). A **0.5% dust tolerance** is
applied to handle minor rounding differences in wallets.

```
raw_value / 10^18  ≥  total_required × 0.995
```

All 6 checks must pass for the status to advance to `PAYMENT_VERIFIED`.

---

## 💸 Commission Flow

The buyer pays the trade amount **plus** the commission percentage on top.
The seller receives the agreed amount. You keep the commission.

| Scenario | USDT |
|---|---|
| Agreed trade amount | 100.00 |
| Commission (5%) | 5.00 |
| **Buyer must send** | **105.00** |
| Seller receives | 100.00 |
| Admin commission | 5.00 |

> Commission is configurable via `COMMISSION_PERCENT` env var. Default is `5`.

---

## 🚀 Render Deployment Instructions

### Step 1 — Create a Render Account
1. Go to [render.com](https://render.com)
2. Click **Get Started for Free**
3. Sign up using your **GitHub account** (easiest option)
4. Authorize Render when prompted

### Step 2 — Connect Your Repository
1. In the Render dashboard click **New +** (top right)
2. Select **Background Worker**
3. Click **Connect a repository**
4. Find and select your `escrow-bot` repository
5. Click **Connect**

### Step 3 — Configure the Service
Render will auto-detect `render.yaml`. Confirm these settings:

- **Environment:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`
- **Plan:** Free

### Step 4 — Add Environment Variables
1. Scroll to the **Environment** section
2. Click **Add Environment Variable** for each:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your bot token from @BotFather |
| `BSC_ADDRESS` | Your BSC wallet address |
| `BSC_API_KEY` | Your BscScan API key |
| `ADMIN_ID` | Your numeric Telegram user ID |
| `COMMISSION_PERCENT` | `5` |
| `DATABASE_PATH` | `/data/escrow.db` |

### Step 5 — Add a Persistent Disk
1. Scroll to the **Disks** section
2. Click **Add Disk**
3. Set Name: `escrow-data`
4. Mount Path: `/data`
5. Size: `1 GB` (free tier allows 1 GB)

### Step 6 — Deploy
1. Click **Create Background Worker**
2. Render will clone your repo, install packages, and start the bot
3. Click the **Logs** tab and wait for:
   ```
   Database ready.
   Bot starting — polling…
   ```

### Step 7 — Test
Open Telegram, find your bot, and send `/start`. You should get the welcome message.

---

## 💻 Local Testing

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/escrow-bot.git
cd escrow-bot

# 2. Create a virtual environment
python3.11 -m venv venv

# 3. Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create your .env file
cp .env.example .env
# Now open .env in any text editor and fill in your values

# 6. Run the bot
python app.py
```

---

## 🛡️ Security Notes

- **Never commit `.env`** — it is listed in `.gitignore` and will be blocked
- Keep your GitHub repository set to **Private**
- The bot verifies and tracks payments — actual fund release must be done **manually** from your escrow wallet
- Each transaction hash can only be used **once** across all trades (stored in `used_transactions` table)
- Only the buyer (by Telegram user ID) can submit payment for their own trade
- Only the seller (by @username match) can confirm delivery for their own trade
- Only the admin (by numeric `ADMIN_ID`) can access admin commands
- Disputes immediately lock the trade and alert the admin — neither party can act until resolved

---

## 🧯 Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Bot doesn't respond | Wrong `BOT_TOKEN` or bot not running | Check Render logs for startup errors |
| `KeyError: BOT_TOKEN` at startup | Env var not set in Render | Add variable in Render → Environment tab |
| BscScan returns "no transactions" | TX not confirmed yet | Wait 15–30 seconds, then retry `/paid` |
| "Wrong token contract" error | Sent wrong token (not USDT BEP-20) | Must send USDT on BSC network only |
| "Duplicate transaction" error | TX hash already used in another trade | Each payment needs a unique TX |
| `/confirm` says "not the seller" | Username mismatch | Seller's @username must match exactly what buyer typed in `/create` |
| Bot offline after free tier sleep | Render free workers sleep after inactivity | Upgrade to paid plan or use a cron job to ping the service |
| Database resets on redeploy | `DATABASE_PATH` not on persistent disk | Set `DATABASE_PATH=/data/escrow.db` and add the `/data` disk in Render |
| `ADMIN_ID` commands not working | Using username instead of numeric ID | Get your numeric ID from @userinfobot |
