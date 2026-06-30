"""
DXY (US Dollar Index) monitor.
Key inverse relationship: DXY up = stocks/crypto down. DXY down = stocks up.
Uses yfinance to fetch DXY data — completely free.
"""

import yfinance as yf
from datetime import datetime, timedelta


def get_dxy_bias() -> dict:
    """
    Returns current DXY direction and what it means for stock trading.
    """
    try:
        dxy = yf.download("DX-Y.NYB", period="5d", interval="1d", progress=False, auto_adjust=True)
        if dxy.empty or len(dxy) < 2:
            return {"available": False, "bias": "neutral", "reason": "DXY data unavailable"}

        latest = float(dxy["Close"].iloc[-1])
        prev   = float(dxy["Close"].iloc[-2])
        change_pct = (latest - prev) / prev * 100

        if change_pct > 0.3:
            direction = "rising"
            stock_bias = "bearish"
            note = f"DXY rising +{change_pct:.2f}% → headwind for stocks. Reduce long exposure."
        elif change_pct < -0.3:
            direction = "falling"
            stock_bias = "bullish"
            note = f"DXY falling {change_pct:.2f}% → tailwind for stocks. Favour longs."
        else:
            direction = "flat"
            stock_bias = "neutral"
            note = f"DXY flat ({change_pct:+.2f}%) → no meaningful macro signal from dollar today."

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
        return {"available": False, "bias": "neutral", "reason": str(e)}


def get_dxy_weekly_trend() -> str:
    """Returns a 5-day DXY trend summary for the Sunday prep report."""
    try:
        dxy = yf.download("DX-Y.NYB", period="10d", interval="1d", progress=False, auto_adjust=True)
        if len(dxy) < 5:
            return "DXY data insufficient."

        week = dxy.tail(5)
        start = float(week["Close"].iloc[0])
        end   = float(week["Close"].iloc[-1])
        week_change = (end - start) / start * 100

        if week_change > 0.5:
            return f"DXY gained {week_change:.1f}% this week — dollar strengthening. Stocks face macro headwind."
        elif week_change < -0.5:
            return f"DXY fell {abs(week_change):.1f}% this week — dollar weakening. Tailwind for stocks."
        else:
            return f"DXY flat ({week_change:+.1f}%) this week — no dominant macro signal from dollar."
    except Exception as e:
        return f"DXY weekly trend unavailable: {e}"
