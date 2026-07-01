"""
Capitol Trades scraper — fetches recent US congressional stock disclosures.
Free public data: https://www.capitoltrades.com/trades
Politicians must disclose trades within 45 days of execution.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import CAPITOL_TRADES_MIN_AMOUNT

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# The most consistently profitable politicians to copy (from backtests: 34.8% vs 15% S&P)
TRACKED_POLITICIANS = [
    "Michael McCaul",
    "Nancy Pelosi",
    "Dan Crenshaw",
    "Tommy Tuberville",
    "Marjorie Taylor Greene",
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_recent_trades(days_back: int = 7) -> list[dict]:
    """
    Scrape Capitol Trades for recent congressional stock disclosures.
    Returns list of trades from the past `days_back` days.
    """
    url = "https://www.capitoltrades.com/trades?period=7d&orderBy=-txDate&pageSize=96"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    trades = []

    # Parse the trades table
    rows = soup.select("table tbody tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) < 7:
            continue
        try:
            politician = cells[0].get_text(strip=True)
            ticker     = cells[2].get_text(strip=True)
            tx_type    = cells[4].get_text(strip=True)   # "Purchase" or "Sale"
            tx_date    = cells[5].get_text(strip=True)
            amount_str = cells[6].get_text(strip=True)

            # Parse amount range (e.g. "$15,001 - $50,000" → use midpoint)
            amount = _parse_amount(amount_str)

            # Only track buys from our watched politicians
            if tx_type.lower() not in ("purchase", "buy"):
                continue

            if any(name.lower() in politician.lower() for name in TRACKED_POLITICIANS):
                trades.append({
                    "politician": politician,
                    "ticker": ticker,
                    "action": "BUY",
                    "date": tx_date,
                    "amount": amount,
                    "source": "capitol_trades",
                })
        except Exception:
            continue

    return trades


def get_buy_candidates() -> list[str]:
    """
    Returns a deduplicated list of ticker symbols recently purchased
    by tracked politicians. These are candidate stocks for the bot.
    """
    try:
        trades = fetch_recent_trades(days_back=7)
        seen = set()
        candidates = []
        for t in trades:
            if t["ticker"] and t["ticker"] not in seen:
                seen.add(t["ticker"])
                candidates.append(t["ticker"])
        return candidates
    except Exception as e:
        print(f"[Capitol Trades] Error: {e}")
        return []


def _parse_amount(amount_str: str) -> float:
    """Convert '$15,001 - $50,000' style strings to a midpoint float."""
    import re
    nums = re.findall(r"[\d,]+", amount_str)
    if not nums:
        return 0
    values = [float(n.replace(",", "")) for n in nums]
    return sum(values) / len(values)
