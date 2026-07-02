"""
Central configuration — all constants and settings live here.
Change behaviour by editing this file or overriding via .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Trading 212 (UK broker, commission-free) ─────────────────
T212_API_KEY    = os.environ["T212_API_KEY"]
T212_SECRET_KEY = os.environ["T212_SECRET_KEY"]
T212_MODE       = os.getenv("T212_MODE", "demo")   # "demo" or "live"

# ── Claude ───────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL_FAST    = "claude-haiku-4-5-20251001"  # Real-time decisions — ~£1/month
CLAUDE_MODEL_ANALYST = "claude-sonnet-4-6"           # Weekly self-learning review — ~£1-2/month
CLAUDE_MODEL         = CLAUDE_MODEL_FAST             # Default (backwards compat)

# ── Supabase ─────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# ── Risk rules ───────────────────────────────────────────────
MAX_POSITION_PCT    = float(os.getenv("MAX_POSITION_PCT", "0.10"))   # 10% per position
MAX_POSITIONS       = int(os.getenv("MAX_POSITIONS", "5"))
MIN_CASH_PCT        = float(os.getenv("MIN_CASH_PCT", "0.10"))       # Always 10%+ cash
TRAILING_STOP_PCT   = float(os.getenv("TRAILING_STOP_PCT", "0.10"))  # 10% trailing stop
CIRCUIT_BREAKER_DEFENSIVE_PCT = float(os.getenv("CIRCUIT_BREAKER_DEFENSIVE_PCT", "0.03"))  # At -3%: tighten stops, no new trades
CIRCUIT_BREAKER_HALT_PCT      = float(os.getenv("CIRCUIT_BREAKER_HALT_PCT", "0.05"))       # At -5%: halt ALL new trades for day

# ── Scheduler ────────────────────────────────────────────────
POSITION_CHECK_MINS = int(os.getenv("POSITION_CHECK_MINS", "5"))     # Monitor stops every 5 min
TRADE_DECISION_MINS = int(os.getenv("TRADE_DECISION_MINS", "30"))    # Look for new trades every 30 min

# ── Market session windows (ET) ───────────────────────────────
MARKET_OPEN_ET         = "09:30"
MARKET_CLOSE_ET        = "16:00"
NY_KILL_ZONE_START_ET  = "07:00"   # ICT: best entries 7–10 AM
NY_KILL_ZONE_END_ET    = "10:00"
LUNCH_AVOID_START_ET   = "12:00"   # ICT: no new entries 12–1:30 PM
LUNCH_AVOID_END_ET     = "13:30"
LUNCH_SWEEP_WINDOW_ET  = "13:15"   # ICT: watch for liquidity sweep before 1:30 close
PM_SESSION_START_ET    = "13:30"   # ICT PM session range start (1:30 PM ET)
PM_SESSION_END_ET      = "16:00"   # ICT PM session range end (4:00 PM ET)
PM_SWEEP_WINDOW_MINS   = 30        # How long after open to watch for PM level sweep
FRIDAY_REVIEW_ET       = "15:30"   # Weekend hold/cash decision

# ── Markov regime ────────────────────────────────────────────
MARKOV_LOOKBACK_DAYS   = 20        # 20-day rolling return window
MARKOV_BULL_THRESHOLD  = 0.05      # +5% = bull state
MARKOV_BEAR_THRESHOLD  = -0.05     # -5% = bear state
MARKOV_MARKET_TICKER   = "SPY"     # Reference market for regime detection

# ── Capitol Trades ───────────────────────────────────────────
CAPITOL_TRADES_URL        = "https://www.capitoltrades.com/trades"
CAPITOL_TRADES_MIN_AMOUNT = 0      # Track ALL politician trades (no minimum)

# ── Permanent Watchlist ───────────────────────────────────────
# Evaluated every 30 minutes via TradingView signals.
# Bot always has stocks to consider — never idles waiting for signals.
WATCHLIST = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META",
    # Financials (NYSE)
    "JPM", "BAC", "GS",
    # Consumer & Retail
    "COST", "WMT", "HD",
    # Healthcare
    "UNH", "JNJ",
    # Energy
    "XOM", "CVX",
    # Broad market ETFs
    "QQQ", "SPY", "IWM",
    # High-momentum favourites
    "TSLA", "AMD",
]

# ── News sources ─────────────────────────────────────────────
NEWS_TWITTER_HANDLES   = ["DeItaone", "FinancialJuice"]
BRIEFING_COM_URL       = "https://www.briefing.com/investor/calendars/economic/"

# ── Macroeconomic no-trade events ────────────────────────────
HIGH_IMPACT_EVENTS     = ["CPI", "FOMC", "NFP", "Non-Farm", "Federal Funds"]

# ── Self-learning ─────────────────────────────────────────────
DAILY_REVIEW_TIME_ET   = "16:30"   # Nightly 5-min summary after market close
LEARNING_REVIEW_DAY    = "sunday"  # Day of full weekly self-review
LEARNING_REVIEW_TIME   = "08:00"   # Time of Sunday deep review (ET)
MIN_TRADES_FOR_REVIEW  = 5         # Don't deep-review with fewer trades than this
HYPOTHESIS_TEST_WEEKS  = 2         # Test each proposed change for 2 weeks
