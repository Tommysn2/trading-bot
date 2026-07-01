"""
ICT PM Session Range — previous day's high/low between 1:30–4:00 PM ET (RTH only).

How it works:
  1. Each day at close, record the PM session high/low for SPY (market proxy)
  2. At the next day's open, watch if price SWEEPS below PM low (bullish) or
     above PM high (bearish) within the first 30 minutes
  3. A sweep = stop-hunt by the algorithm before reversal — high-probability setup

Rules:
  - PM sweep BELOW the low in a BULL regime -> strong buy signal (sell-side liquidity taken)
  - PM sweep ABOVE the high in a BEAR regime -> strong sell signal (buy-side liquidity taken)
  - No sweep in first 30 min -> PM range not the active driver today

Uses Stooq 5-minute bars (no rate limits, no API key needed).
"""

import requests
import pandas as pd
from io import StringIO
import pytz
from datetime import datetime, date, timedelta, time
from config.settings import (
    PM_SESSION_START_ET, PM_SESSION_END_ET,
    PM_SWEEP_WINDOW_MINS, MARKOV_MARKET_TICKER
)

ET = pytz.timezone("America/New_York")

_STOOQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _fetch_stooq_5min(ticker: str) -> pd.DataFrame:
    """Fetch 5-minute bars from Stooq. Returns DataFrame with DatetimeIndex in ET."""
    stooq_symbol = ticker.lower() + ".us"
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=5"
    resp = requests.get(url, timeout=12, headers=_STOOQ_HEADERS)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text), parse_dates=["Date"])
    if df.empty:
        raise ValueError("Empty response from Stooq")

    if "Time" in df.columns:
        df["datetime"] = pd.to_datetime(
            df["Date"].astype(str) + " " + df["Time"].astype(str)
        )
    else:
        df["datetime"] = pd.to_datetime(df["Date"])

    df = df.set_index("datetime").sort_index()

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert(ET)

    return df


def get_pm_session_range(ticker: str = None, for_date: date = None) -> dict:
    """
    Returns the PM session high and low for a given date (default: yesterday).
    Uses 5-minute bars filtered to 1:30-4:00 PM ET.
    """
    ticker = ticker or MARKOV_MARKET_TICKER
    if for_date is None:
        for_date = _last_trading_day()

    try:
        df = _fetch_stooq_5min(ticker)

        # Filter to target date only
        day_data = df[df.index.date == for_date]
        if day_data.empty:
            return _unavailable(f"No data for {for_date}")

        # Filter to PM session window (1:30 PM - 4:00 PM ET)
        pm_start = _t(PM_SESSION_START_ET)
        pm_end   = _t(PM_SESSION_END_ET)
        pm_data = day_data[
            (day_data.index.time >= pm_start) &
            (day_data.index.time <= pm_end)
        ]

        if pm_data.empty:
            return _unavailable(f"No PM session data for {for_date}")

        pm_high = float(pm_data["High"].max())
        pm_low  = float(pm_data["Low"].min())

        return {
            "available": True,
            "date": for_date.isoformat(),
            "ticker": ticker,
            "pm_high": round(pm_high, 4),
            "pm_low":  round(pm_low, 4),
            "pm_range": round(pm_high - pm_low, 4),
            "source": "stooq 5m",
        }

    except Exception as e:
        return _unavailable(str(e))


def check_pm_sweep(regime_signal: str = "sideways") -> dict:
    """
    Called shortly after the 9:30 AM open (within the first 30 minutes).
    Checks whether the current price has swept the previous day's PM high or low.
    """
    now_et = datetime.now(ET)

    # Only valid in the first PM_SWEEP_WINDOW_MINS after open
    market_open_today = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    window_end = market_open_today + timedelta(minutes=PM_SWEEP_WINDOW_MINS)
    if now_et < market_open_today or now_et > window_end:
        return {
            "signal": "outside_window",
            "bias": "neutral",
            "note": (
                f"PM sweep check only valid 9:30-{window_end.strftime('%H:%M')} ET. "
                f"Current: {now_et.strftime('%H:%M')}"
            ),
        }

    # Get yesterday's PM range
    pm = get_pm_session_range()
    if not pm["available"]:
        return {"signal": "unavailable", "bias": "neutral", "note": pm.get("reason", "PM range unavailable")}

    # Get current price (last bar from Stooq)
    try:
        df = _fetch_stooq_5min(MARKOV_MARKET_TICKER)
        if df.empty:
            return {"signal": "unavailable", "bias": "neutral", "note": "Cannot fetch current price"}
        current_low   = float(df["Low"].iloc[-1])
        current_high  = float(df["High"].iloc[-1])
        current_price = float(df["Close"].iloc[-1])
    except Exception as e:
        return {"signal": "unavailable", "bias": "neutral", "note": str(e)}

    pm_high = pm["pm_high"]
    pm_low  = pm["pm_low"]

    swept_low  = current_low < pm_low
    swept_high = current_high > pm_high

    if swept_low and regime_signal in ("bull", "sideways"):
        signal = "bullish_sweep"
        bias   = "bullish"
        note   = (
            f"Price swept BELOW PM low ({pm_low:.2f}) -> sell-side liquidity taken. "
            f"Bull regime -> ICT buy signal. Watch for reversal back above PM low."
        )
    elif swept_high and regime_signal in ("bear", "sideways"):
        signal = "bearish_sweep"
        bias   = "bearish"
        note   = (
            f"Price swept ABOVE PM high ({pm_high:.2f}) -> buy-side liquidity taken. "
            f"Bear regime -> ICT sell signal. Watch for reversal back below PM high."
        )
    elif swept_low or swept_high:
        signal = "sweep_against_regime"
        bias   = "neutral"
        note   = (
            f"PM level swept but against current regime ({regime_signal}). "
            f"Lower probability - skip or wait for clearer setup."
        )
    else:
        signal = "no_sweep"
        bias   = "neutral"
        note   = (
            f"No PM sweep yet. PM range: {pm_low:.2f}-{pm_high:.2f}. "
            f"Current price: {current_price:.2f}. Watching..."
        )

    return {
        "signal": signal,
        "bias": bias,
        "pm_high": pm_high,
        "pm_low": pm_low,
        "current_price": current_price,
        "swept_low": swept_low,
        "swept_high": swept_high,
        "note": note,
    }


def get_pm_range_for_context() -> dict:
    """
    Returns a combined dict for the decision engine context.
    Called once per trade decision cycle.
    """
    pm_range = get_pm_session_range()
    if not pm_range["available"]:
        return {"available": False, "note": "PM session range unavailable."}

    return {
        "available": True,
        "pm_high": pm_range["pm_high"],
        "pm_low": pm_range["pm_low"],
        "pm_range": pm_range["pm_range"],
        "date": pm_range["date"],
        "note": (
            f"Previous PM range ({pm_range['date']}): "
            f"High {pm_range['pm_high']:.2f} / Low {pm_range['pm_low']:.2f} "
            f"(range: {pm_range['pm_range']:.2f} pts)"
        ),
    }


# -- Helpers ------------------------------------------------------------------

def _t(time_str: str) -> time:
    h, m = map(int, time_str.split(":"))
    return time(h, m)


def _last_trading_day() -> date:
    """Returns the most recent weekday (skips weekends)."""
    today = date.today()
    offset = 1
    candidate = today - timedelta(days=offset)
    while candidate.weekday() >= 5:
        offset += 1
        candidate = today - timedelta(days=offset)
    return candidate


def _unavailable(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "pm_high": None,
        "pm_low": None,
    }
