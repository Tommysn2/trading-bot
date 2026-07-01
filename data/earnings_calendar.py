"""
Earnings calendar — avoids opening new positions on earnings day for held stocks.
Rule: Never open a new position in a stock that reports earnings today or tomorrow.

Uses yfinance with a hard 5-second timeout per ticker.
If yfinance hangs or fails, the ticker is assumed SAFE (we don't block trades
on missing data — better to trade and be wrong on earnings than freeze the bot).
"""

import yfinance as yf
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FT
import logging

log = logging.getLogger(__name__)

_TIMEOUT = 5   # seconds per ticker — hard wall-clock limit


def _fetch_earnings_date(ticker: str) -> date | None:
    """Fetch next earnings date with a hard timeout. Returns None on any failure."""
    def _get():
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                return None
            earnings_col = cal.columns[0]
            if hasattr(earnings_col, "date"):
                return earnings_col.date()
            return None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_get).result(timeout=_TIMEOUT)
        except FT:
            log.debug(f"[Earnings] {ticker} calendar timed out after {_TIMEOUT}s — assuming safe")
            return None
        except Exception:
            return None


def is_earnings_risk(ticker: str, days_ahead: int = 1) -> tuple[bool, date | None]:
    """
    Returns (True, earnings_date) if the ticker has earnings today or within days_ahead days.
    Returns (False, None) if safe or if data is unavailable.
    """
    earnings_date = _fetch_earnings_date(ticker)
    if earnings_date is None:
        return False, None

    today = date.today()
    days_until = (earnings_date - today).days
    if 0 <= days_until <= days_ahead:
        return True, earnings_date
    return False, None


def filter_earnings_safe(candidates: list[str]) -> tuple[list[str], list[str]]:
    """
    Splits candidates into safe (no upcoming earnings) and risky (earnings soon).
    Tickers that time out are assumed safe so the bot is never blocked by hanging data.
    """
    safe = []
    risky = []
    for ticker in candidates:
        at_risk, earnings_date = is_earnings_risk(ticker, days_ahead=1)
        if at_risk:
            risky.append(ticker)
            log.info(f"[Earnings] Skipping {ticker} — earnings on {earnings_date}")
        else:
            safe.append(ticker)
    return safe, risky
