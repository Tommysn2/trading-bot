"""
Supabase client — logs every trade and self-learning entry to Postgres.
Free tier: 500MB storage, unlimited reads/writes.
Tables: trades, daily_summaries, learning_log
"""

from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from datetime import datetime
import pytz


def _client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def log_trade(trade: dict) -> dict:
    """
    Inserts a trade record into the trades table.
    trade keys: ticker, action, price, qty, notional, regime, signal_strength,
                reasoning, confidence, source (capitol_trades/manual), timestamp
    """
    data = {
        "ticker": trade.get("ticker"),
        "action": trade.get("action"),           # BUY or SELL
        "price": trade.get("price"),
        "qty": trade.get("qty"),
        "notional": trade.get("notional"),
        "regime": trade.get("regime"),
        "signal_strength": trade.get("confidence"),
        "reasoning": trade.get("reasoning"),
        "source": trade.get("source", "bot"),
        "timestamp": datetime.now(pytz.UTC).isoformat(),
        "pnl": trade.get("pnl"),                # filled on close
        "pnl_pct": trade.get("pnl_pct"),        # filled on close
    }
    result = _client().table("trades").insert(data).execute()
    return result.data[0] if result.data else {}


def log_daily_summary(summary: dict) -> dict:
    """Inserts end-of-day portfolio summary."""
    data = {
        "date": summary.get("date"),
        "equity": summary.get("equity"),
        "daily_pnl": summary.get("daily_pnl"),
        "daily_pnl_pct": summary.get("daily_pnl_pct"),
        "open_positions": summary.get("open_positions"),
        "regime": summary.get("regime"),
        "regime_signal": summary.get("regime_signal"),
        "notes": summary.get("notes", ""),
        "timestamp": datetime.now(pytz.UTC).isoformat(),
    }
    result = _client().table("daily_summaries").insert(data).execute()
    return result.data[0] if result.data else {}


def log_learning_entry(entry: dict) -> dict:
    """Logs a self-learning cycle result."""
    data = {
        "week_start": entry.get("week_start"),
        "trades_analysed": entry.get("trades_analysed"),
        "worst_pattern": entry.get("worst_pattern"),
        "hypothesis": entry.get("hypothesis"),
        "outcome": entry.get("outcome"),    # "accepted" | "reverted" | "testing"
        "metric_before": entry.get("metric_before"),
        "metric_after": entry.get("metric_after"),
        "timestamp": datetime.now(pytz.UTC).isoformat(),
    }
    result = _client().table("learning_log").insert(data).execute()
    return result.data[0] if result.data else {}


def get_recent_trades(limit: int = 50) -> list[dict]:
    """Fetches the most recent trades for self-learning analysis."""
    result = (
        _client()
        .table("trades")
        .select("*")
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_trade_stats() -> dict:
    """Returns aggregate win rate, avg P&L, best/worst patterns."""
    trades = get_recent_trades(limit=200)
    closed = [t for t in trades if t.get("pnl") is not None]

    if not closed:
        return {"message": "No closed trades yet."}

    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl") or 0) <= 0]

    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed)
    avg_win = sum(t.get("pnl", 0) or 0 for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("pnl", 0) or 0 for t in losses) / len(losses) if losses else 0

    return {
        "total_trades": len(closed),
        "win_rate": len(wins) / len(closed),
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": abs(avg_win / avg_loss) if avg_loss else float("inf"),
        "by_regime": _group_by(closed, "regime"),
    }


def _group_by(trades: list[dict], field: str) -> dict:
    groups = {}
    for t in trades:
        key = t.get(field, "unknown")
        if key not in groups:
            groups[key] = {"count": 0, "total_pnl": 0, "wins": 0}
        groups[key]["count"] += 1
        groups[key]["total_pnl"] += t.get("pnl", 0) or 0
        if (t.get("pnl") or 0) > 0:
            groups[key]["wins"] += 1
    for k in groups:
        n = groups[k]["count"]
        groups[k]["win_rate"] = groups[k]["wins"] / n if n > 0 else 0
    return groups
