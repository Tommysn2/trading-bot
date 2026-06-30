"""
Connection tester — run this before deploying to confirm every API key works.
Usage: python test_connections.py

All tests must pass before you deploy to the VPS.
"""

import sys
import os

# Load .env first
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("❌ python-dotenv not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

PASS = "✅"
FAIL = "❌"
results = []


def test(name, fn):
    try:
        msg = fn()
        print(f"{PASS} {name}: {msg}")
        results.append((name, True))
    except Exception as e:
        print(f"{FAIL} {name}: {e}")
        results.append((name, False))


# ── 1. Trading 212 ───────────────────────────────────────────
def check_trading212():
    from data.trading212_client import Trading212Client
    client = Trading212Client()
    acc = client.get_account()
    mode = os.getenv("T212_MODE", "demo").upper()
    return f"{mode} account | Equity: £{acc['equity']:,.2f} | Cash: £{acc['cash']:,.2f}"

test("Trading 212", check_trading212)


# ── 2. Anthropic (Haiku) ─────────────────────────────────────
def check_anthropic_haiku():
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with: OK"}]
    )
    return f"Haiku responded: {resp.content[0].text.strip()}"

test("Anthropic Haiku", check_anthropic_haiku)


# ── 3. Anthropic (Sonnet) ────────────────────────────────────
def check_anthropic_sonnet():
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with: OK"}]
    )
    return f"Sonnet responded: {resp.content[0].text.strip()}"

test("Anthropic Sonnet", check_anthropic_sonnet)


# ── 4. Supabase ──────────────────────────────────────────────
def check_supabase():
    from supabase import create_client
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    # Check the trades table exists
    result = client.table("trades").select("id").limit(1).execute()
    return f"Connected | trades table exists ({len(result.data)} rows returned)"

test("Supabase", check_supabase)


# ── 5. Telegram ──────────────────────────────────────────────
def check_telegram():
    import requests
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": "🤖 Bot connection test passed. Ready to deploy!"
    }, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text}")
    return "Message sent — check your Telegram"

test("Telegram", check_telegram)


# ── 6. Market data (yfinance) ────────────────────────────────
def check_yfinance():
    import yfinance as yf
    spy = yf.download("SPY", period="5d", interval="1d", progress=False, auto_adjust=True)
    if spy.empty:
        raise Exception("No data returned")
    latest = float(spy["Close"].iloc[-1])
    return f"SPY last close: ${latest:.2f}"

test("Market data (yfinance)", check_yfinance)


# ── 7. Markov regime ─────────────────────────────────────────
def check_markov():
    from brain.markov_regime import get_regime_signal
    signal = get_regime_signal(force_refresh=True)
    return signal["summary"]

test("Markov regime detection", check_markov)


# ── 8. News feed ─────────────────────────────────────────────
def check_news():
    from data.news_checker import _fetch_google_news
    headlines = _fetch_google_news("S&P 500", hours_back=24)
    return f"{len(headlines)} headlines fetched from Google News RSS"

test("News feed", check_news)


# ── Summary ──────────────────────────────────────────────────
print("\n" + "="*50)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"Results: {passed}/{total} passed")

if passed == total:
    print("\n🚀 All systems go. Safe to deploy to Railway.")
else:
    failed = [name for name, ok in results if not ok]
    print(f"\n⚠️  Fix these before deploying: {', '.join(failed)}")
    print("Check your .env file and make sure all API keys are correct.")
    sys.exit(1)
