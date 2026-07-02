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

SYSTEM_PROMPT = """You are an autonomous stock trading bot running in DEMO mode (paper money).
Your mission: find the best available trade every 30 minutes and execute it.

You have three data tiers to evaluate:

TIER 1 — SIGNAL-FLAGGED stocks (congressional buys, insider Form 4, ARK Invest):
These are HIGH CONVICTION. A politician or C-suite exec just bought this. Prioritise these.
Combine with TradingView technicals — if TV says BUY or STRONG_BUY, this is a trade.

TIER 2 — WATCHLIST stocks (permanent list of quality US stocks):
Evaluate using TradingView signals only. BUY when:
  - TradingView rating is BUY or STRONG_BUY (score >= 0.1)
  - RSI is between 40-70 (not overbought, not oversold breakdown)
  - MACD is bullish
  - EMA trend is bullish or strongly bullish
  - Markov regime is bull or sideways (not bear)
One strong watchlist stock with aligned signals beats waiting for a signal that never comes.

TIER 3 — SELL decisions:
Recommend SELL only for positions already in the portfolio showing significant loss (-8%+)
or if regime flips to bear and the position is a long.

HARD RULES (never break these):
1. HOLD if risk engine says no new trades (circuit breaker active or at max positions)
2. HOLD if market is closed or in the lunch avoid window (12:00-1:30 PM ET)
3. HOLD if Markov conviction is "avoid" or "strong avoid" (signal < -0.2)
4. Never buy if RSI > 75 (overbought)
5. Never buy if there is a confirmed high-impact macro event today (FOMC, CPI, NFP)

In DEMO mode: BE DECISIVE. You are learning. A trade that loses teaches more than 10 HOLDs.
If signals are mixed but not clearly bad, favour action over inaction.

Output ONLY valid JSON — no prose, no explanation outside the JSON:
{
  "action": "BUY or SELL or HOLD",
  "ticker": "TICKER or null",
  "confidence": 0.0,
  "reasoning": "2-3 sentences. Which signals aligned? What is the thesis?",
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

    # Signal-sourced candidates (Congress / Insider / ARK)
    sources = ctx.get("candidate_sources", {})
    signal_flagged = sources.get("signal_flagged", [])
    ct   = sources.get("congressional", [])
    ins  = sources.get("insider_form4", [])
    ark  = sources.get("ark_invest", [])

    lines.append("\n=== TIER 1 — SIGNAL-FLAGGED STOCKS (highest priority) ===")
    if signal_flagged:
        if ct:
            lines.append("  Congressional buys (Capitol Trades): " + ", ".join(ct))
        if ins:
            lines.append("  Executive buys (SEC Form 4 / OpenInsider): " + ", ".join(ins))
        if ark:
            lines.append("  ARK Invest daily buys: " + ", ".join(ark))
    else:
        lines.append("  None today — no congressional/insider/ARK signals.")

    # Watchlist (always evaluated)
    watchlist = sources.get("watchlist", [])
    lines.append("\n=== TIER 2 — WATCHLIST (evaluate via TradingView technicals) ===")
    if watchlist:
        lines.append("  " + ", ".join(watchlist))
    else:
        lines.append("  (all watchlist stocks are already in Tier 1 signals)")

    # News per candidate (signal-flagged stocks only)
    news = ctx.get("news", {})
    if news:
        lines.append("\nNEWS ANALYSIS (signal-flagged stocks):")
        for ticker, n in news.items():
            lines.append("  " + ticker + ": " + n.get("summary", "No data"))

    lines.append("\n=== YOUR DECISION ===")
    lines.append("Review all tiers. Find the strongest setup. Output your decision as JSON.")
    lines.append("Tier 1 stocks with aligned TV signals = BUY.")
    lines.append("Tier 2 stocks with STRONG_BUY TV rating + RSI 40-70 + bullish MACD = BUY.")
    lines.append("If nothing looks good, output HOLD with your reasoning.")

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
