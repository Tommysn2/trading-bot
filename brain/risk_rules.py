"""
Risk Rules Engine — enforces all hard limits on position sizing and circuit breakers.
These rules are NON-NEGOTIABLE. Claude cannot override them.
"""

from config.settings import (
    MAX_POSITION_PCT, MAX_POSITIONS, MIN_CASH_PCT,
    TRAILING_STOP_PCT, CIRCUIT_BREAKER_DEFENSIVE_PCT,
    CIRCUIT_BREAKER_HALT_PCT
)


class RiskEngine:
    def __init__(self, account: dict, positions: list[dict]):
        """
        account: from alpaca_client.get_account()
        positions: from alpaca_client.get_positions()
        """
        self.account = account
        self.positions = positions
        self.equity = account["equity"]
        self.cash = account["cash"]
        self.daily_pnl_pct = account["daily_pnl_pct"]
        self.n_positions = len(positions)

    # ── Circuit breaker checks ───────────────────────────────

    def circuit_breaker_status(self) -> dict:
        """
        Returns the current circuit breaker level.
        normal → defensive (-3%) → halt (-5%)
        """
        if self.daily_pnl_pct <= -CIRCUIT_BREAKER_HALT_PCT:
            return {
                "level": "halt",
                "message": f"⛔ HALT: Portfolio down {self.daily_pnl_pct:.1%} today. No new trades.",
                "allow_new_trades": False,
                "tighten_stops": True,
            }
        elif self.daily_pnl_pct <= -CIRCUIT_BREAKER_DEFENSIVE_PCT:
            return {
                "level": "defensive",
                "message": f"⚠️ DEFENSIVE: Portfolio down {self.daily_pnl_pct:.1%}. No new trades, stops tightened to 5%.",
                "allow_new_trades": False,
                "tighten_stops": True,
                "defensive_stop_pct": TRAILING_STOP_PCT / 2,
            }
        else:
            return {
                "level": "normal",
                "message": f"✅ Normal: Daily P&L {self.daily_pnl_pct:+.1%}.",
                "allow_new_trades": True,
                "tighten_stops": False,
            }

    # ── Position sizing ──────────────────────────────────────

    def max_trade_size(self, size_multiplier: float = 1.0) -> float:
        """
        Returns the maximum dollar amount allowed for the next trade.
        Respects position % limit and minimum cash buffer.
        size_multiplier from Markov signal (0.5x – 1.5x).
        """
        base_allocation = self.equity * MAX_POSITION_PCT
        adjusted = base_allocation * size_multiplier

        # Cash floor: never go below MIN_CASH_PCT in cash
        max_deployable = self.cash - (self.equity * MIN_CASH_PCT)
        if max_deployable <= 0:
            return 0

        return min(adjusted, max_deployable)

    # ── Position limit checks ────────────────────────────────

    def can_open_position(self, size_multiplier: float = 1.0) -> tuple[bool, str, float]:
        """
        Returns (can_open, reason, trade_size_dollars).
        """
        # Circuit breaker first
        cb = self.circuit_breaker_status()
        if not cb["allow_new_trades"]:
            return False, cb["message"], 0

        # Max positions
        if self.n_positions >= MAX_POSITIONS:
            return False, f"At max positions ({MAX_POSITIONS}). Wait for a close before opening new.", 0

        # Cash floor
        trade_size = self.max_trade_size(size_multiplier)
        if trade_size < 100:  # Minimum meaningful trade size
            return False, f"Insufficient free cash. Need more than £100 deployable. Current: £{trade_size:.0f}", 0

        return True, f"OK to trade. Max size: £{trade_size:.0f}", trade_size

    # ── Trailing stop management ─────────────────────────────

    def get_stop_pct(self) -> float:
        """
        Returns the trailing stop % to use, factoring in circuit breaker status.
        Normal: 10%. Defensive mode: 5%.
        """
        cb = self.circuit_breaker_status()
        if cb.get("tighten_stops"):
            return cb.get("defensive_stop_pct", TRAILING_STOP_PCT / 2)
        return TRAILING_STOP_PCT

    # ── Portfolio summary ────────────────────────────────────

    def summary(self) -> str:
        cb = self.circuit_breaker_status()
        can_open, reason, size = self.can_open_position()
        lines = [
            f"Portfolio: £{self.equity:,.0f} | Cash: £{self.cash:,.0f} | Day P&L: {self.daily_pnl_pct:+.1%}",
            f"Positions: {self.n_positions}/{MAX_POSITIONS}",
            f"Circuit breaker: {cb['level'].upper()} — {cb['message']}",
            f"New trade allowed: {'✅' if can_open else '❌'} {reason}",
            f"Active stop loss: {self.get_stop_pct():.0%} trailing",
        ]
        return "\n".join(lines)
