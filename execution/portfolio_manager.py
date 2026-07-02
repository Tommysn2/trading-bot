"""
Portfolio Manager — high-level coordinator between data, brain, and execution layers.
Called by the scheduler. Gathers all signals, checks rules, fires decisions.
"""

from data.trading212_client import Trading212Client as AlpacaClient
import data.capitol_trades as _ct
import data.insider_trades as _it
import data.ark_trades as _ark
from data.forex_factory import is_no_trade_day
from config.settings import WATCHLIST
from data.news_checker import check_ticker_news, check_macro_news
from data.dxy_monitor import get_dxy_bias
from data.earnings_calendar import filter_earnings_safe
from data.pm_session_range import get_pm_range_for_context, check_pm_sweep
from data.tradingview_client import get_market_tv_context, get_candidate_tv_signals
from brain.markov_regime import get_regime_signal
from brain.session_filter import get_session_context, is_friday_review_time
from brain.risk_rules import RiskEngine
from brain.decision_engine import make_decision
from execution.trade_executor import TradeExecutor


class PortfolioManager:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.executor = TradeExecutor()

    def run_position_check(self) -> dict:
        """
        Runs every 5 minutes.
        Checks circuit breaker and tightens stops if needed.
        """
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()
        risk_engine = RiskEngine(account, positions)

        cb = risk_engine.circuit_breaker_status()
        stop_actions = []

        if cb["level"] in ("defensive", "halt"):
            stop_actions = self.executor.check_and_tighten_stops(risk_engine)

        return {
            "type":           "position_check",
            "circuit_breaker": cb["level"],
            "positions":      len(positions),
            "daily_pnl_pct":  account["daily_pnl_pct"],
            "stop_actions":   stop_actions,
        }

    def run_trade_decision(self) -> dict:
        """
        Runs every 30 minutes during market hours.
        Full decision cycle: gather all signals -> ask Claude -> execute if warranted.
        """
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()
        risk_engine = RiskEngine(account, positions)

        # -- Early exits ------------------------------------------------

        if not self.alpaca.is_market_open():
            return {"type": "trade_decision", "result": "skipped", "reason": "Market closed."}

        no_trade, events = is_no_trade_day()
        if no_trade:
            return {"type": "trade_decision", "result": "skipped",
                    "reason": f"Macro event day: {', '.join(events)}"}

        if is_friday_review_time():
            regime = get_regime_signal()
            result = self.executor.friday_weekend_decision(risk_engine, regime)
            return {"type": "friday_review", **result}

        # -- Gather signals ---------------------------------------------

        session    = get_session_context()
        regime     = get_regime_signal()
        dxy        = get_dxy_bias()
        macro_news = check_macro_news(hours_back=2)

        # PM session range — fetch once, pass to sweep check to avoid duplicate download
        pm_range = get_pm_range_for_context()
        pm_sweep = check_pm_sweep(
            regime_signal=regime.get("current_state", "sideways"),
            pm_range=pm_range,   # reuses already-fetched data — no extra Stooq call
        )

        tv_market = get_market_tv_context()

        # Signal candidates from three external sources
        ct_candidates      = _ct.get_buy_candidates()
        insider_candidates = _it.get_buy_candidates()
        ark_candidates     = _ark.get_buy_candidates()

        # Deduplicate and combine signal sources
        seen: set = set()
        signal_candidates = []
        for ticker in ct_candidates + insider_candidates + ark_candidates:
            if ticker and ticker not in seen:
                seen.add(ticker)
                signal_candidates.append(ticker)

        # Always append watchlist — bot never idles with empty candidates
        watchlist_additions = [t for t in WATCHLIST if t not in seen]

        # Earnings risk: only check signal stocks (yfinance is slow — 5s timeout each)
        # Watchlist stocks are trusted blue-chips — no earnings check needed
        safe_signals, _risky = filter_earnings_safe(signal_candidates)
        safe_candidates = safe_signals + watchlist_additions

        # News for first 5 candidates (budget API calls)
        news = {}
        for ticker in safe_candidates[:5]:
            news[ticker] = check_ticker_news(ticker, hours_back=4)

        # TradingView signals — full candidate list in one POST request
        tv_signals = get_candidate_tv_signals(safe_candidates)

        can_open, reason, trade_size = risk_engine.can_open_position()

        context = {
            "regime":  regime,
            "session": session,
            "risk": {
                "can_open":  can_open,
                "reason":    reason,
                "trade_size": trade_size,
                "cb_level":  risk_engine.circuit_breaker_status()["level"],
            },
            "candidates": safe_candidates,
            "candidate_sources": {
                "congressional": ct_candidates,
                "insider_form4": insider_candidates,
                "ark_invest":    ark_candidates,
                "watchlist":     watchlist_additions,
                "signal_flagged": signal_candidates,
            },
            "news":     news,
            "dxy":      dxy,
            "macro": {
                "no_trade_today":    no_trade,
                "events":            events,
                "macro_news_count":  macro_news.get("headline_count", 0),
            },
            "pm_range":  pm_range,
            "pm_sweep":  pm_sweep,
            "tv_market": tv_market,
            "tv_signals": tv_signals,
            "positions": positions,
            "account":   account,
        }

        decision  = make_decision(context)
        execution = self.executor.execute(decision, risk_engine)

        return {
            "type":          "trade_decision",
            "regime":        regime.get("current_state"),
            "session_valid": session.get("can_open_new_trade"),
            "candidates":    safe_candidates,
            "decision":      decision,
            "execution":     execution,
        }

    def run_nightly_summary(self) -> dict:
        """Runs at 4:30 PM ET after market close."""
        account   = self.alpaca.get_account()
        positions = self.alpaca.get_positions()
        regime    = get_regime_signal()

        return {
            "type":           "nightly_summary",
            "date":           __import__("datetime").date.today().isoformat(),
            "equity":         account["equity"],
            "daily_pnl":      account["daily_pnl"],
            "daily_pnl_pct":  account["daily_pnl_pct"],
            "open_positions": len(positions),
            "positions":      positions,
            "regime":         regime.get("current_state"),
            "regime_signal":  regime.get("signal"),
        }
