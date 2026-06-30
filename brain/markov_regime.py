"""
Markov Regime Detection — the quant hedge fund method.
Classifies market as Bull / Bear / Sideways using a 20-day rolling return window.
Builds a 3×3 transition matrix from SPY history.
Signal = P(Bull tomorrow) − P(Bear tomorrow) → determines trade direction and size.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from config.settings import (
    MARKOV_LOOKBACK_DAYS, MARKOV_BULL_THRESHOLD,
    MARKOV_BEAR_THRESHOLD, MARKOV_MARKET_TICKER
)

STATES = {"bull": 0, "sideways": 1, "bear": 2}
STATE_NAMES = {0: "bull", 1: "sideways", 2: "bear"}


class MarkovRegime:
    def __init__(self, ticker: str = None):
        self.ticker = ticker or MARKOV_MARKET_TICKER
        self.transition_matrix = None
        self.current_state = None
        self.history = None

    def load(self, years: int = 5):
        """Load price history and build the transition matrix."""
        df = yf.download(self.ticker, period=f"{years}y", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError(f"No data returned for {self.ticker}")

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
        Positive → go long (bigger = more conviction)
        Negative → go short / avoid
        """
        if self.transition_matrix is None:
            self.load()

        current_idx = STATES[self.current_state]
        row = self.transition_matrix[current_idx]

        p_bull = row[STATES["bull"]]
        p_sideways = row[STATES["sideways"]]
        p_bear = row[STATES["bear"]]
        signal = p_bull - p_bear

        # Position size multiplier: scale between 0.5x and 1.5x based on conviction
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
            )
        }

    def get_matrix_display(self) -> str:
        """Returns the 3x3 transition matrix as a readable string."""
        if self.transition_matrix is None:
            self.load()
        lines = ["Markov Transition Matrix (rows=today, cols=tomorrow):"]
        lines.append(f"{'':12} {'→Bull':>8} {'→Side':>8} {'→Bear':>8}")
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
        row_sums[row_sums == 0] = 1  # avoid div by zero
        return matrix / row_sums


# ── Convenience function ─────────────────────────────────────

_regime_cache = {}

def get_regime_signal(ticker: str = None, force_refresh: bool = False) -> dict:
    """
    Cached convenience wrapper. Refreshes once per day.
    """
    global _regime_cache
    ticker = ticker or MARKOV_MARKET_TICKER
    today = datetime.now().date().isoformat()

    if not force_refresh and ticker in _regime_cache and _regime_cache[ticker].get("date") == today:
        return _regime_cache[ticker]["signal"]

    regime = MarkovRegime(ticker)
    regime.load()
    signal = regime.get_signal()
    _regime_cache[ticker] = {"date": today, "signal": signal}
    return signal
