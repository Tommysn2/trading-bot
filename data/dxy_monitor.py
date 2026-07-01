"""
DXY (US Dollar Index) monitor.
Key inverse relationship: DXY up = stocks/crypto down. DXY down = stocks up.
Uses Stooq.com for DXY data — free, no rate limits, no API key needed.
Falls back to neutral signal on any failure so the bot is never blocked.
"""

import requests
import pandas as pd
from io import StringIO


_NEUTRAL = {"available": False, "bias": "neutral", "reason": "DXY data unavailable"}


def _fetch_dxy_stooq(rows: int = 10) -> pd.Series:
    """
    Fetch DXY closing prices from Stooq.com.
    DXY ticker on Stooq: dxy
    Returns a sorted pd.Series of close prices (index=Date).
    """
    url = "https://stooq.com/q/d/l/?s=dxy&i=d"
    resp = requests.get(url, timeout=10, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), index_col="Date", parse_dates=True)
    df = df.sort_index()
    return df["Close"].tail(rows)


def get_dxy_bias() -> dict:
    """
    Returns current DXY direction and what it means for stock trading.
    Never raises — returns neutral signal on any failure.
    """
    try:
        closes = _fetch_dxy_stooq(rows=5)
        if len(closes) < 2:
            return _NEUTRAL

        latest = float(closes.iloc[-1])
        prev   = float(closes.iloc[-2])
        change_pct = (latest - prev) / prev * 100

        if change_pct > 0.3:
            direction = "rising"
            stock_bias = "bearish"
            note = f"DXY rising +{change_pct:.2f}% — headwind for stocks. Reduce long exposure."
        elif change_pct < -0.3:
            direction = "falling"
            stock_bias = "bullish"
            note = f"DXY falling {change_pct:.2f}% — tailwind for stocks. Favour longs."
        else:
            direction = "flat"
            stock_bias = "neutral"
            note = f"DXY flat ({change_pct:+.2f}%) — no meaningful macro signal from dollar today."

        return {
            "available": True,
            "dxy_level": round(latest, 2),
            "dxy_change_pct": round(change_pct, 3),
            "direction": direction,
            "stock_bias": stock_bias,
            "note": note,
        }
    except Exception as e:
        print(f"[DXY] Error: {e}")
        return {**_NEUTRAL, "reason": str(e)}


def get_dxy_weekly_trend() -> str:
    """Returns a 5-day DXY trend summary for the Sunday prep report."""
    try:
        closes = _fetch_dxy_stooq(rows=10)
        if len(closes) < 5:
            return "DXY data insufficient."

        week = closes.tail(5)
        start = float(week.iloc[0])
        end   = float(week.iloc[-1])
        week_change = (end - start) / start * 100

        if week_change > 0.5:
            return f"DXY gained {week_change:.1f}% this week — dollar strengthening. Stocks face macro headwind."
        elif week_change < -0.5:
            return f"DXY fell {abs(week_change):.1f}% this week — dollar weakening. Tailwind for stocks."
        else:
            return f"DXY flat ({week_change:+.1f}%) this week — no dominant macro signal from dollar."
    except Exception as e:
        return f"DXY weekly trend unavailable: {e}"
