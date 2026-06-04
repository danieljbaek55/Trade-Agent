# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
ACCOUNT_SIZE = 3000.0   # pretend $3k even though Alpaca paper gives $100k

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
TICKERS = ["QQQ", "IWM"]    # Nasdaq + Russell 2000.  Cheap enough for a $3k acct.

# ---------------------------------------------------------------------------
# Time horizon (long options, 1–3 months)
# ---------------------------------------------------------------------------
MIN_DTE = 30
MAX_DTE = 90

# ---------------------------------------------------------------------------
# Per-contract limits
# ---------------------------------------------------------------------------
MAX_CONTRACT_COST = 200.0           # max premium per contract ($)
MAX_PREMIUM_PER_SHARE = MAX_CONTRACT_COST / 100  # $2.00/share

# ---------------------------------------------------------------------------
# Conviction tiers — "perfect setup → go big"
#
# Signal strength is computed from RSI + MACD + EMA trend + regime alignment.
#   < 3   = hold (skip)
#   = 3   = STANDARD tier
#   >= 4  = HIGH CONVICTION tier ("perfect setup")
# ---------------------------------------------------------------------------
MIN_SIGNAL_STRENGTH = 3
HIGH_CONVICTION_THRESHOLD = 4

# Target deployment per tier as fraction of account
STANDARD_DEPLOY_PCT = 0.10          # $300 at $3k
HIGH_CONVICTION_DEPLOY_PCT = 0.25   # $750 at $3k

# ---------------------------------------------------------------------------
# Portfolio limits
# ---------------------------------------------------------------------------
MAX_POSITIONS = 3                   # tighter — each position is bigger now
STOP_LOSS_PCT = 0.50                # close at 50% loss
TAKE_PROFIT_PCT = 1.00              # close at 100% gain

# ---------------------------------------------------------------------------
# Liquidity filter
# ---------------------------------------------------------------------------
MIN_VOLUME = 25
MIN_OPEN_INTEREST = 50

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
RSI_EXTREME_LOW = 25      # bonus strength when extreme
RSI_EXTREME_HIGH = 75

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

EMA_SHORT = 20
EMA_LONG = 50

# ---------------------------------------------------------------------------
# Market regime filter
# ---------------------------------------------------------------------------
USE_REGIME_FILTER = True

# ---------------------------------------------------------------------------
# Data + persistence
# ---------------------------------------------------------------------------
DATA_PERIOD = "1y"
DATA_INTERVAL = "1d"
PORTFOLIO_FILE = "portfolio.json"

# Reference risk-per-trade (1% rule); surfaced for awareness, not enforced
RISK_REFERENCE_PCT = 0.01
