"""
Markov Regime Detection — the quant hedge fund method.
Classifies market as Bull / Bear / Sideways using a 20-day rolling return window.
Builds a 3x3 transition matrix from SPY history.
Signal = P(Bull tomorrow) - P(Bear tomorrow) -> determines trade direction and size.

Robust version: retries yfinance on failure, falls back to cached regime,
falls back to a neutral sideways default so the bot never crashes.
"""

import numpy as np
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import (
    MARKOV_LOOKBACK_DAYS, MARKOV_BULL_THRESHOLD,
    MARKOV_BEAR_THRESHOLD, MARKOV_MARKET_TICKER
)

log = logging.getLogger(__name__)

STATES = {"bull": 0, "sideways": 1, "bear": 2}
STATE_NAMES = {0: "bull", 1: "sideways", 2: "bear"}

# Default fallback when all data sources fail — neutral sideways
_FALLBACK_REGIME = {
    "current_state": "sideways",
    "p_bull_tomorrow": 0.38,
    "p_sideways_tomorrow": 0.34,
    "p_bear_tomorrow": 0.28,
    "signal": 0.10,
    "direction": "long",
    "conviction": "low",
    "size_multiplier": 0.7,
    "summary": (
        "Market state: SIDEWAYS (fallback — live data unavailable). "
        "Signal: +10% (Bull 38% - Bear 28%). "
        "Conviction: low. Position size: 0.7x normal."
    ),
    "fallback": True,
}


def _download_stooq(ticker: str, years: int = 3) -> pd.DataFrame:
    """
    Download historical daily data from Stooq.com — free, no API key, no rate limits.
    Stooq ticker format: SPY -> spy.us
    """
    import requests
    from io import StringIO

    stooq_symbol = ticker.lower() + ".us"
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"

    resp = requests.get(url, timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text), index_col="Date", parse_dates=True)
    df = df.sort_index()

    # Filter to requested years
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
    df = df[df.index >= cutoff]

    if df.empty or len(df) < 30:
        raise ValueError(f"Stooq returned insufficient data for {ticker}")

    # Rename to match yfinance format
    df = df.rename(columns={"Close": "Close", "Open": "Open", "High": "High",
                             "Low": "Low", "Volume": "Volume"})
    return df


def _download_yfinance_fallback(ticker: str) -> pd.DataFrame:
    """Fallback to yfinance with a hard thread timeout."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FT

    def _fetch():
        return yf.download(ticker, period="1y", interval="1d",
                           progress=False, auto_adjust=True, threads=False)

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            df = ex.submit(_fetch).result(timeout=12)
        except FT:
            raise ValueError(f"yfinance timed out for {ticker}")

    if df is None or df.empty:
        raise ValueError(f"yfinance returned empty data for {ticker}")
    return df


def _try_download(ticker: str) -> pd.DataFrame:
    """
    Try Stooq first (no rate limits), fall back to yfinance.
    """
    # Primary: Stooq (free, reliable, no rate limits on Railway)
    try:
        df = _download_stooq(ticker, years=3)
        log.info(f"[Markov] Stooq: {len(df)} rows for {ticker}")
        return df
    except Exception as e:
        log.warning(f"[Markov] Stooq failed: {e} — trying yfinance")

    # Fallback: yfinance with timeout
    try:
        df = _download_yfinance_fallback(ticker)
        log.info(f"[Markov] yfinance fallback: {len(df)} rows for {ticker}")
        return df
    except Exception as e:
        log.warning(f"[Markov] yfinance also failed: {e}")

    raise ValueError(f"All data sources failed for {ticker}")


class MarkovRegime:
    def __init__(self, ticker: str = None):
        self.ticker = ticker or MARKOV_MARKET_TICKER
        self.transition_matrix = None
        self.current_state = None
        self.history = None

    def load(self, years: int = 5):
        """Load price history and build the transition matrix."""
        df = _try_download(self.ticker)

        closes = df["Close"].squeeze()
        self.history = closes

        # Label every day with a state based on 20-day rolling return
        rolling_return = closes.pct_change(MARKOV_LOOKBACK_DAYS)
        states = rolling_return.apply(self._classify_return).dropna()
        self.state_series = states

        # Build transition matrix from the labeled history
        self.transition_matrix = self._build_transition_matrix(states)
        self.current_state = states.iloc[-1]
        return self

    def get_signal(self) -> dict:
        """
        Returns the trading signal for today.
        Signal = P(Bull tomorrow) - P(Bear tomorrow)
        Positive -> go long (bigger = more conviction)
        Negative -> go short / avoid
        """
        if self.transition_matrix is None:
            self.load()

        current_idx = STATES[self.current_state]
        row = self.transition_matrix[current_idx]

        p_bull = row[STATES["bull"]]
        p_sideways = row[STATES["sideways"]]
        p_bear = row[STATES["bear"]]
        signal = p_bull - p_bear

        if signal > 0.4:
            size_multiplier = 1.5
            conviction = "high"
        elif signal > 0.2:
            size_multiplier = 1.0
            conviction = "medium"
        elif signal > 0:
            size_multiplier = 0.7
            conviction = "low"
        elif signal > -0.2:
            size_multiplier = 0.0
            conviction = "avoid"
        else:
            size_multiplier = 0.0
            conviction = "strong avoid"

        return {
            "current_state": self.current_state,
            "p_bull_tomorrow": round(p_bull, 3),
            "p_sideways_tomorrow": round(p_sideways, 3),
            "p_bear_tomorrow": round(p_bear, 3),
            "signal": round(signal, 3),
            "direction": "long" if signal > 0 else "short_or_cash",
            "conviction": conviction,
            "size_multiplier": size_multiplier,
            "summary": (
                f"Market state: {self.current_state.upper()}. "
                f"Signal: {signal:+.1%} (Bull {p_bull:.0%} - Bear {p_bear:.0%}). "
                f"Conviction: {conviction}. Position size: {size_multiplier}x normal."
            ),
            "fallback": False,
        }

    def get_matrix_display(self) -> str:
        """Returns the 3x3 transition matrix as a readable string."""
        if self.transition_matrix is None:
            self.load()
        lines = ["Markov Transition Matrix (rows=today, cols=tomorrow):"]
        lines.append(f"{'':12} {'->Bull':>8} {'->Side':>8} {'->Bear':>8}")
        for from_state, idx in STATES.items():
            row = self.transition_matrix[idx]
            lines.append(
                f"{from_state.capitalize():12} {row[0]:>8.1%} {row[1]:>8.1%} {row[2]:>8.1%}"
            )
        return "\n".join(lines)

    # ── Private ─────────────────────────────────────────────

    def _classify_return(self, r: float) -> str:
        if pd.isna(r):
            return None
        if r >= MARKOV_BULL_THRESHOLD:
            return "bull"
        elif r <= MARKOV_BEAR_THRESHOLD:
            return "bear"
        else:
            return "sideways"

    def _build_transition_matrix(self, states: pd.Series) -> np.ndarray:
        """Count all state transitions and convert to probability matrix."""
        matrix = np.zeros((3, 3))
        labels = states.tolist()
        for i in range(len(labels) - 1):
            from_s = labels[i]
            to_s   = labels[i + 1]
            if from_s and to_s:
                matrix[STATES[from_s]][STATES[to_s]] += 1

        # Normalise each row to sum to 1
        row_sums = matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        return matrix / row_sums


# ── Convenience function ─────────────────────────────────────

_regime_cache: dict = {}


def get_regime_signal(ticker: str = None, force_refresh: bool = False) -> dict:
    """
    Cached convenience wrapper. Refreshes once per day.
    Falls back to last known signal, then to a neutral default.
    Never raises — always returns a usable dict.
    """
    global _regime_cache
    ticker = ticker or MARKOV_MARKET_TICKER
    today = datetime.now().date().isoformat()

    # Return today's cached value if available
    if not force_refresh and ticker in _regime_cache and _regime_cache[ticker].get("date") == today:
        return _regime_cache[ticker]["signal"]

    try:
        regime = MarkovRegime(ticker)
        regime.load()
        signal = regime.get_signal()
        _regime_cache[ticker] = {"date": today, "signal": signal}
        log.info(f"[Markov] Regime: {signal['current_state'].upper()} | Signal: {signal['signal']:+.1%} | {signal['conviction']}")
        return signal
    except Exception as e:
        log.error(f"[Markov] Failed to compute regime for {ticker}: {e}")

        # Fall back to yesterday's cached signal if we have one
        if ticker in _regime_cache:
            stale = _regime_cache[ticker]["signal"]
            log.warning(f"[Markov] Using stale cached signal from {_regime_cache[ticker]['date']}")
            return {**stale, "fallback": True, "summary": "[CACHED] " + stale.get("summary", "")}

        # Last resort: return neutral default so the bot keeps running
        log.warning("[Markov] No cache available — using neutral fallback regime")
        return _FALLBACK_REGIME
