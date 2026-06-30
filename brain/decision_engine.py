"""
Decision Engine — the brain that asks Claude to make the final trading call.
Assembles all data signals, sends them to Claude Haiku, and parses the response.
Claude's decision is always subject to the hard risk rules from risk_rules.py.
"""

import json
import re
from anthropic import Anthropic
from config.settings import CLAUDE_MODEL_FAST, ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a professional stock trading bot assistant with expertise in:
- Markov regime detection and quantitative market analysis
- Congressional trading signal interpretation (Capitol Trades)
- ICT (Inner Circle Trader) session timing and market structure
- News-driven momentum trading (fresh news = continuation, no news = mean reversion)
- Macro filters (DXY, Forex Factory events)
- ICT PM session range sweeps (previous day 1:30-4 PM high/low = key liquidity levels)
- TradingView technical analysis signals (EMA trends, RSI, MACD, overall rating)

Your job is to analyse ALL the provided signals and recommend ONE of three actions:
  BUY <TICKER> -- buy this stock now
  SELL <TICKER> -- sell this stock now
  HOLD -- do nothing

Rules you MUST follow:
1. Never recommend buying if the Markov signal conviction is "avoid" or "strong avoid"
2. Never recommend buying outside the valid trading session window
3. Always respect the risk engine decision -- if it says no new trades, output HOLD
4. Consider news: fresh positive news = stronger buy signal; no news behind a move = consider fading
5. DXY rising strongly = reduce aggression on long entries
6. Output your recommendation as valid JSON only -- no prose outside the JSON block.

Output format (JSON only):
{
  "action": "BUY or SELL or HOLD",
  "ticker": "TICKER or null",
  "confidence": 0.0,
  "reasoning": "2-3 sentences explaining the decision",
  "key_signals": ["signal 1", "signal 2", "signal 3"]
}"""


def make_decision(context: dict) -> dict:
    """
    Takes a context dict with all market signals and returns a decision dict.
    """
    prompt = _build_prompt(context)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        decision = _parse_json(text)
        decision["raw_response"] = text
        return decision

    except Exception as e:
        return {
            "action": "HOLD",
            "ticker": None,
            "confidence": 0,
            "reasoning": "Decision engine error: " + str(e),
            "key_signals": ["error"],
            "raw_response": str(e)
        }


def _build_prompt(ctx: dict) -> str:
    """Assembles the context dict into a readable prompt for Claude."""
    lines = ["=== MARKET CONTEXT FOR TRADING DECISION ===\n"]

    # Regime signal
    r = ctx.get("regime", {})
    lines.append("MARKOV REGIME: " + r.get("summary", "Not available"))

    # Session context
    s = ctx.get("session", {})
    lines.append("\nSESSION: " + s.get("time_et", "?") + " ET (" + s.get("day", "?") + ")")
    lines.append("  Can open new trade: " + str(s.get("can_open_new_trade", False)) + " -- " + s.get("trade_window_reason", ""))
    lines.append("  In Kill Zone: " + str(s.get("in_kill_zone", False)) + " -- " + s.get("kill_zone_reason", ""))

    # Risk engine
    risk = ctx.get("risk", {})
    lines.append("\nRISK ENGINE: " + risk.get("reason", "Not available"))
    lines.append("  Can open position: " + str(risk.get("can_open", False)))
    lines.append("  Max trade size: £" + str(round(risk.get("trade_size", 0))))
    lines.append("  Circuit breaker: " + risk.get("cb_level", "unknown"))

    # Portfolio
    acc = ctx.get("account", {})
    positions = ctx.get("positions", [])
    equity = acc.get("equity", 0)
    cash = acc.get("cash", 0)
    pnl_pct = acc.get("daily_pnl_pct", 0)
    lines.append("\nPORTFOLIO: Equity £{:,.0f} | Cash £{:,.0f} | Day P&L {:+.1%}".format(equity, cash, pnl_pct))

    if positions:
        pos_strs = [p["symbol"] + " " + "{:+.1%}".format(p["unrealized_pnl_pct"]) for p in positions]
        lines.append("  Open positions ({}): {}".format(len(positions), ", ".join(pos_strs)))
    else:
        lines.append("  Open positions: None")

    # DXY
    dxy = ctx.get("dxy", {})
    lines.append("\nDXY: " + dxy.get("note", "Not available"))

    # Macro events
    macro = ctx.get("macro", {})
    if macro.get("no_trade_today"):
        lines.append("\nMACRO EVENT TODAY -- no new trades: " + ", ".join(macro.get("events", [])))
    else:
        lines.append("\nMACRO: No high-impact events today.")

    # ICT PM Session Range
    pm_range = ctx.get("pm_range", {})
    pm_sweep = ctx.get("pm_sweep", {})
    if pm_range.get("available"):
        lines.append("\nICT PM SESSION RANGE (prev day 1:30-4 PM ET):")
        lines.append("  " + pm_range.get("note", ""))
        sweep_signal = pm_sweep.get("signal", "unavailable")
        sweep_note   = pm_sweep.get("note", "")
        if sweep_signal == "bullish_sweep":
            lines.append("  ⚡ BULLISH SWEEP: " + sweep_note)
        elif sweep_signal == "bearish_sweep":
            lines.append("  ⚡ BEARISH SWEEP: " + sweep_note)
        elif sweep_signal == "no_sweep":
            lines.append("  No sweep at open: " + sweep_note)
        else:
            lines.append("  PM sweep: " + sweep_note)
    else:
        lines.append("\nICT PM SESSION RANGE: Unavailable.")

    # TradingView market context
    tv_market = ctx.get("tv_market", {})
    if tv_market.get("available"):
        lines.append("\nTRADINGVIEW MARKET (SPY): " + tv_market.get("note", ""))
    else:
        lines.append("\nTRADINGVIEW: Unavailable.")

    # TradingView per-ticker signals
    tv_signals = ctx.get("tv_signals", {})
    if tv_signals:
        lines.append("\nTRADINGVIEW TICKER SIGNALS:")
        for sym, sig in tv_signals.items():
            if sig.get("available"):
                lines.append("  " + sym + ": " + sig.get("note", ""))

    # Capitol Trades candidates
    candidates = ctx.get("candidates", [])
    if candidates:
        lines.append("\nCAPITOL TRADES CANDIDATES (congressional buy signals): " + ", ".join(candidates))
    else:
        lines.append("\nCAPITOL TRADES: No new signals this week.")

    # News per candidate
    news = ctx.get("news", {})
    if news:
        lines.append("\nNEWS ANALYSIS:")
        for ticker, n in news.items():
            lines.append("  " + ticker + ": " + n.get("summary", "No data"))

    lines.append("\n=== YOUR TASK ===")
    lines.append("Based on ALL signals above, output your trading decision as JSON.")
    lines.append("If no action is warranted, output HOLD with reasoning.")

    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {
        "action": "HOLD",
        "ticker": None,
        "confidence": 0,
        "reasoning": "Could not parse response: " + text[:120],
        "key_signals": ["parse_error"],
    }
