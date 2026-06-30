"""
Earnings calendar — avoids opening new positions on earnings day for held stocks.
Uses yfinance earnings data — free.
Rule: Never open a new position in a stock that reports earnings today or tomorrow.
"""

import yfinance as yf
from datetime import date, timedelta


def get_earnings_dates(tickers: list[str]) -> dict:
    """
    Returns a dict of {ticker: next_earnings_date} for the given tickers.
    Returns None for a ticker if earnings date is unknown.
    """
    result = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).calendar
            if info is not None and not info.empty:
                # Calendar returns a DataFrame; earnings date is in the index
                earnings_date = info.columns[0].date() if hasattr(info.columns[0], 'date') else None
                result[ticker] = earnings_date
            else:
                result[ticker] = None
        except Exception:
            result[ticker] = None
    return result


def is_earnings_risk(ticker: str, days_ahead: int = 1) -> tuple[bool, date | None]:
    """
    Returns (True, earnings_date) if the ticker has earnings today or within `days_ahead` days.
    Returns (False, None) if safe.
    """
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        if cal is None or cal.empty:
            return False, None

        # Try to get the earnings date
        earnings_col = cal.columns[0]
        if hasattr(earnings_col, 'date'):
            earnings_date = earnings_col.date()
        else:
            return False, None

        today = date.today()
        days_until = (earnings_date - today).days

        if 0 <= days_until <= days_ahead:
            return True, earnings_date
        return False, None

    except Exception:
        return False, None


def filter_earnings_safe(candidates: list[str]) -> tuple[list[str], list[str]]:
    """
    Splits candidates into safe (no upcoming earnings) and risky (earnings soon).
    Returns (safe_tickers, risky_tickers).
    """
    safe = []
    risky = []
    for ticker in candidates:
        at_risk, earnings_date = is_earnings_risk(ticker, days_ahead=1)
        if at_risk:
            risky.append(ticker)
            print(f"[Earnings] Skipping {ticker} — earnings on {earnings_date}")
        else:
            safe.append(ticker)
    return safe, risky
