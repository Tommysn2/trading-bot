"""
Trade Executor — converts decisions from the brain into live Alpaca orders.
All orders go through the risk engine first. Logs every action.
"""

from data.trading212_client import Trading212Client as AlpacaClient  # same interface
from brain.risk_rules import RiskEngine
from config.settings import TRAILING_STOP_PCT
import time


class TradeExecutor:
    def __init__(self):
        self.alpaca = AlpacaClient()

    def execute(self, decision: dict, risk_engine: RiskEngine) -> dict:
        """
        Takes a decision from decision_engine.make_decision() and executes it.
        Returns an execution result dict.
        """
        action = decision.get("action", "HOLD").upper()
        ticker = decision.get("ticker")
        confidence = decision.get("confidence", 0)
        reasoning = decision.get("reasoning", "")

        result = {
            "action": action,
            "ticker": ticker,
            "confidence": confidence,
            "reasoning": reasoning,
            "executed": False,
            "order": None,
            "error": None,
        }

        if action == "HOLD" or not ticker:
            result["message"] = "HOLD — no trade executed."
            return result

        try:
            if action == "BUY":
                # Final risk check — get how much we're allowed to trade
                can_open, reason, trade_size = risk_engine.can_open_position(
                    size_multiplier=min(confidence * 1.5, 1.5)  # high confidence = bigger position
                )
                if not can_open:
                    result["message"] = f"Risk check blocked BUY: {reason}"
                    result["error"] = reason
                    return result

                # Execute buy
                order = self.alpaca.buy(ticker, notional=trade_size)
                result["order"] = order
                result["executed"] = True
                result["trade_size"] = trade_size
                result["message"] = f"BUY {ticker} £{trade_size:.0f} — {reasoning}"

                # Set trailing stop immediately after fill
                time.sleep(2)  # brief wait for order to process
                stop = self.alpaca.set_trailing_stop(ticker, trail_percent=risk_engine.get_stop_pct() * 100)
                result["trailing_stop"] = stop

            elif action == "SELL":
                # Confirm we actually hold this position
                position = self.alpaca.get_position(ticker)
                if not position:
                    result["message"] = f"SELL {ticker} — position not found, nothing to sell."
                    return result

                order = self.alpaca.sell(ticker)
                result["order"] = order
                result["executed"] = True
                result["message"] = f"SELL {ticker} — {reasoning}"

        except Exception as e:
            result["error"] = str(e)
            result["message"] = f"Execution error: {e}"

        return result

    def check_and_tighten_stops(self, risk_engine: RiskEngine) -> list[dict]:
        """
        Called every 5 minutes when positions are open.
        If circuit breaker is in defensive mode, tightens all trailing stops.
        """
        cb = risk_engine.circuit_breaker_status()
        if not cb.get("tighten_stops"):
            return []

        positions = self.alpaca.get_positions()
        results = []
        for pos in positions:
            try:
                # Cancel existing stop orders and replace with tighter stop
                self.alpaca.cancel_all_orders()
                new_stop = self.alpaca.set_trailing_stop(
                    pos["symbol"],
                    trail_percent=cb.get("defensive_stop_pct", TRAILING_STOP_PCT / 2) * 100
                )
                results.append({
                    "ticker": pos["symbol"],
                    "action": "stop_tightened",
                    "new_stop_pct": cb.get("defensive_stop_pct"),
                    "order": new_stop
                })
            except Exception as e:
                results.append({"ticker": pos["symbol"], "action": "stop_tighten_failed", "error": str(e)})

        return results

    def friday_weekend_decision(self, risk_engine: RiskEngine, regime_signal: dict) -> dict:
        """
        Called at 3:30 PM ET on Fridays.
        Decision: hold positions over weekend, or close all to cash?
        Rules:
          - Bear regime → close all to cash
          - Defensive/Halt circuit breaker → close all
          - Bull regime + no major news risk → hold
        """
        positions = self.alpaca.get_positions()
        if not positions:
            return {"action": "nothing_to_close", "message": "No positions to review for weekend."}

        should_close = False
        reason = ""

        # Close if bear regime
        if regime_signal.get("current_state") == "bear":
            should_close = True
            reason = "Bear market regime detected — closing all positions for weekend."

        # Close if circuit breaker active
        cb = risk_engine.circuit_breaker_status()
        if cb["level"] in ("defensive", "halt"):
            should_close = True
            reason = f"Circuit breaker {cb['level']} — closing all positions for weekend."

        if should_close:
            closed = []
            for pos in positions:
                try:
                    self.alpaca.sell(pos["symbol"])
                    closed.append(pos["symbol"])
                except Exception as e:
                    closed.append(f"{pos['symbol']} (FAILED: {e})")
            return {
                "action": "closed_all",
                "tickers": closed,
                "reason": reason
            }
        else:
            return {
                "action": "holding",
                "tickers": [p["symbol"] for p in positions],
                "reason": f"Bull/sideways regime ({regime_signal.get('current_state')}) — holding over weekend."
            }
