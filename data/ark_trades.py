"""
ARK Invest daily trades tracker.
ARK publishes their daily buy/sell activity as a CSV every evening.
Cathie Wood's flagship ETFs: ARKK, ARKQ, ARKG, ARKW, ARKX.

Logic: if ARK buys a stock across MULTIPLE funds on the same day,
it's a high-conviction signal. Single-fund buys with large share counts
also qualify.

Source: ark-funds.com — public, no API key needed.
"""

import requests
import csv
from io import StringIO
from datetime import datetime, timedelta
from collections import defaultdict
import logging

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ARK ETF daily holdings CSV URLs
ARK_FUND_URLS = {
    "ARKK": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKQ": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_AUTONOMOUS_TECHNOLOGY_&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKG": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKW": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKX": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_SPACE_EXPLORATION_&_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}

# Fallback: ARK also publishes trade activity directly
ARK_TRADES_URL = "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_TRADES.csv"

# Minimum share count for a buy to be meaningful (avoids noise from tiny rebalances)
MIN_ARK_SHARES = 10_000


def fetch_ark_daily_trades() -> list[dict]:
    """
    Fetch ARK's most recent published trades.
    Returns list of buys from today or yesterday.
    """
    trades = []
    cutoff = datetime.now() - timedelta(days=3)   # trades file updated nightly

    try:
        resp = requests.get(ARK_TRADES_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        reader = csv.DictReader(StringIO(resp.text))
        for row in reader:
            try:
                direction = row.get("direction", row.get("Direction", "")).strip()
                if direction.lower() not in ("buy", "bought"):
                    continue

                ticker = row.get("ticker", row.get("Ticker", "")).strip().upper()
                fund   = row.get("fund", row.get("Fund", "")).strip().upper()
                shares_str = row.get("shares", row.get("Shares", "0")).replace(",", "")
                date_str   = row.get("date", row.get("Date", "")).strip()

                shares = float(shares_str) if shares_str else 0
                if shares < MIN_ARK_SHARES:
                    continue

                try:
                    trade_date = datetime.strptime(date_str[:10], "%m/%d/%Y")
                except ValueError:
                    try:
                        trade_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    except Exception:
                        trade_date = datetime.now()

                if trade_date < cutoff:
                    continue

                trades.append({
                    "ticker": ticker,
                    "fund": fund,
                    "shares": shares,
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "source": "ark_trades_csv",
                })
            except Exception as e:
                log.debug(f"[ARK] Row parse error: {e}")
                continue

        log.info(f"[ARK] Fetched {len(trades)} ARK buys from trades CSV")

    except Exception as e:
        log.warning(f"[ARK] Primary trades CSV failed: {e} — trying holdings diff")
        # Holdings diff approach (less reliable, skipping for now)

    return trades


def get_multi_fund_buys(min_funds: int = 2) -> list[dict]:
    """
    Returns tickers ARK bought across 2+ different funds today.
    Multi-fund buys = highest conviction ARK signal.
    """
    trades = fetch_ark_daily_trades()
    if not trades:
        return []

    # Group by (ticker, date)
    by_ticker: dict = defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append(t)

    results = []
    for ticker, fund_trades in by_ticker.items():
        funds = list({t["fund"] for t in fund_trades})
        total_shares = sum(t["shares"] for t in fund_trades)

        if len(funds) >= min_funds:
            results.append({
                "ticker": ticker,
                "funds": funds,
                "total_shares": total_shares,
                "date": fund_trades[0]["date"],
                "signal": "ARK_MULTI_FUND_BUY",
                "source": "ark_invest",
                "reason": f"ARK bought {total_shares:,.0f} shares across {funds}",
            })

    results.sort(key=lambda x: x["total_shares"], reverse=True)
    return results


def get_buy_candidates() -> list[str]:
    """
    Returns tickers ARK is buying today (multi-fund preferred, large single buys included).
    Drop-in for use in portfolio_manager.
    """
    try:
        trades = fetch_ark_daily_trades()
        if not trades:
            return []

        multi_fund = {r["ticker"] for r in get_multi_fund_buys(min_funds=2)}

        # Also include any very large single-fund buy (500k+ shares)
        big_singles = {t["ticker"] for t in trades if t["shares"] >= 500_000}

        candidates = list(multi_fund | big_singles)
        log.info(f"[ARK] {len(candidates)} buy candidates: {candidates}")
        return candidates
    except Exception as e:
        log.error(f"[ARK] get_buy_candidates failed: {e}")
        return []
