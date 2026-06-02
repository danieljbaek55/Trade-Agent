ACCOUNT_SIZE = 800.0
MAX_CONTRACT_COST = 100.0       # max premium per contract ($1/share * 100 shares)
MAX_PREMIUM_PER_SHARE = MAX_CONTRACT_COST / 100  # $1.00

TICKERS = ["SPY", "QQQ"]

MIN_DTE = 30    # minimum days to expiration
MAX_DTE = 180   # maximum days to expiration (multi-month)

MAX_POSITIONS = 4
STOP_LOSS_PCT = 0.50    # exit if position down 50%
TAKE_PROFIT_PCT = 1.00  # exit if position up 100%

MIN_VOLUME = 25
MIN_OPEN_INTEREST = 50

RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

EMA_SHORT = 20
EMA_LONG = 50

DATA_PERIOD = "6mo"
DATA_INTERVAL = "1d"

PORTFOLIO_FILE = "portfolio.json"
