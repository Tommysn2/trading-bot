"""
TradingView signal client — pulls technical indicators and chart signals
into the Claude decision engine context.

How it works:
  TradingView's public screener API returns real-time technical analysis
  ratings (BUY / SELL / NEUTRAL) and indicator values for any symbol.
  We fetch these once per 30-minute decision cycle and include them
  in the context Claude uses to make trading decisions.

No API key required — uses TradingView's public screener endpoint.
For advanced data (drawing sync, alerts), install the TradingView MCP
connector from the Claude plugins page and set TV_MCP=true in .env.
"""

import requests
import os
from config.settings import MARKOV_MARKET_TICKER

TV_SCREENER_URL = "https://scanner.tradingview.com/america/scan"

# Indicators to pull for each symbol
TV_INDICATORS = [
    "Recommend.All",           # Overall TA rating (-1 to +1)
    "Recommend.MA",            # Moving averages rating
    "Recommend.Other",         # Oscillators rating
    "RSI",                     # RSI(14)
    "RSI[1]",                  # Previous RSI
    "MACD.macd",               # MACD line
    "MACD.signal",             # MACD signal line
    "EMA20",                   # 20-period EMA
    "EMA50",                   # 50-period EMA
    "EMA200",                  # 200-period EMA
    "close",                   # Current price
    "volume",                  # Current volume
    "Volatility.D",            # Daily volatility
    "High.1M",                 # 1-month high
    "Low.1M",                  # 1-month low
]


def _tv_symbol(ticker: str) -> str:
    """Convert AAPL → NASDAQ:AAPL for the TradingView screener."""
    # ETFs trade on AMEX (NYSE Arca)
    _AMEX = {"SPY", "QQQ", "IWM", "DIA", "GLD", "TLT", "XLF", "XLE",
             "XLK", "XLV", "ARKK", "ARKG", "ARKQ", "ARKW"}
    # Large-cap NYSE stocks (financials, industrials, energy, consumer)
    _NYSE = {"JPM", "BAC", "GS", "MS", "C", "WFC", "BRK.B",
             "XOM", "CVX", "COP", "BP", "SLB",
             "JNJ", "UNH", "PFE", "MRK", "ABT",
             "WMT", "HD", "MCD", "KO", "PEP", "PG", "NKE",
             "BA", "CAT", "HON", "GE", "MMM", "UPS", "FDX",
             "T", "VZ", "DIS", "BRK", "BLK", "AXP"}
    if ticker in _AMEX:
        return f"AMEX:{ticker}"
    if ticker in _NYSE:
        return f"NYSE:{ticker}"
    return f"NASDAQ:{ticker}"


def get_tv_signals(symbols: list[str]) -> dict:
    """
    Fetch TradingView technical analysis ratings for a list of symbols.
    Returns a dict keyed by symbol with rating, RSI, MACD, and EMA context.

    Falls back to an empty dict if TradingView is unreachable.
    """
    if not symbols:
        return {}

    tv_symbols = [_tv_symbol(s) for s in symbols]

    payload = {
        "symbols": {"tickers": tv_symbols, "query": {"types": []}},
        "columns": TV_INDICATORS,
    }

    try:
        resp = requests.post(TV_SCREENER_URL, json=payload, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "available": False}

    results = {}
    for item in data.get("data", []):
        raw_symbol = item.get("s", "")
        # Strip exchange prefix: NASDAQ:AAPL → AAPL
        symbol = raw_symbol.split(":")[-1] if ":" in raw_symbol else raw_symbol
        values = item.get("d", [])

        if len(values) < len(TV_INDICATORS):
            continue

        def v(i):
            val = values[i]
            return float(val) if val is not None else None

        overall   = v(0)   # -1 = strong sell, +1 = strong buy
        ma_rating = v(1)
        osc_rating = v(2)
        rsi       = v(3)
        rsi_prev  = v(4)
        macd      = v(5)
        macd_sig  = v(6)
        ema20     = v(7)
        ema50     = v(8)
        ema200    = v(9)
        close     = v(10)

        # Human-readable rating label
        if overall is None:
            rating_label = "UNKNOWN"
        elif overall >= 0.5:
            rating_label = "STRONG_BUY"
        elif overall >= 0.1:
            rating_label = "BUY"
        elif overall <= -0.5:
            rating_label = "STRONG_SELL"
        elif overall <= -0.1:
            rating_label = "SELL"
        else:
            rating_label = "NEUTRAL"

        # EMA trend context
        ema_trend = "unknown"
        if close and ema20 and ema50 and ema200:
            if close > ema20 > ema50 > ema200:
                ema_trend = "strongly bullish (price above all EMAs)"
            elif close > ema50 > ema200:
                ema_trend = "bullish (price above 50 & 200 EMA)"
            elif close < ema20 < ema50 < ema200:
                ema_trend = "strongly bearish (price below all EMAs)"
            elif close < ema50 < ema200:
                ema_trend = "bearish (price below 50 & 200 EMA)"
            else:
                ema_trend = "mixed"

        # MACD momentum
        macd_signal_txt = "unknown"
        if macd is not None and macd_sig is not None:
            if macd > macd_sig:
                macd_signal_txt = "bullish crossover" if rsi_prev and rsi and rsi > rsi_prev else "bullish"
            else:
                macd_signal_txt = "bearish"

        results[symbol] = {
            "available":    True,
            "rating":       rating_label,
            "score":        round(overall, 3) if overall is not None else None,
            "rsi":          round(rsi, 1) if rsi is not None else None,
            "macd":         macd_signal_txt,
            "ema_trend":    ema_trend,
            "close":        close,
            "note": (
                f"TV rating: {rating_label} (score {overall:.2f}) | "
                f"RSI: {rsi:.0f} | MACD: {macd_signal_txt} | EMA: {ema_trend}"
            ) if overall is not None else "No data",
        }

    return results


def get_market_tv_context() -> dict:
    """
    Returns TradingView technical context for SPY (market proxy).
    Called once per 30-minute decision cycle to add chart context.
    """
    market_ticker = MARKOV_MARKET_TICKER  # "SPY"
    signals = get_tv_signals([market_ticker])

    if "error" in signals:
        return {
            "available": False,
            "note": f"TradingView unavailable: {signals['error']}",
        }

    market = signals.get(market_ticker, {})
    if not market.get("available"):
        return {"available": False, "note": "No TradingView data for market index."}

    return {
        "available":  True,
        "market":     market_ticker,
        "rating":     market["rating"],
        "score":      market["score"],
        "rsi":        market["rsi"],
        "macd":       market["macd"],
        "ema_trend":  market["ema_trend"],
        "note":       market["note"],
    }


def get_candidate_tv_signals(candidates: list[str]) -> dict:
    """
    Returns TradingView signals for a list of candidate stocks.
    Merged into the decision engine's news/signal context.
    """
    if not candidates:
        return {}
    return get_tv_signals(candidates[:8])   # limit to 8 to stay within rate limits
