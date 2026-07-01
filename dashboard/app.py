"""
Trading Bot — Mission Control Dashboard
Web server that serves the live dashboard AND runs the bot scheduler in a background thread.
Railway assigns this process a public URL automatically.

Access: https://your-app.up.railway.app
"""

import os
import threading
import logging
import traceback
from datetime import datetime
import pytz
from flask import Flask, jsonify

log = logging.getLogger(__name__)
app = Flask(__name__)

# ── Dashboard HTML ────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot — Mission Control</title>
<style>
:root {
  --bg:     #070b12;
  --card:   #0c1220;
  --border: #162032;
  --text:   #c5d8f0;
  --muted:  #4a6080;
  --teal:   #00d4aa;
  --green:  #00cc88;
  --red:    #ff3355;
  --amber:  #ffaa00;
  --blue:   #4a9eff;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  padding: 14px;
  min-height: 100vh;
}

/* ── Header ── */
.header {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 18px;
  margin-bottom: 10px;
}
.header-title { font-size: 15px; font-weight: bold; color: var(--teal); letter-spacing: 0.5px; }
.badge { padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; letter-spacing: 1px; }
.badge-demo { background: #0d1e3a; color: var(--blue); border: 1px solid var(--blue); }
.badge-live { background: #1a0f00; color: var(--amber); border: 1px solid var(--amber); }
.ml-auto { margin-left: auto; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }
.dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }
.dot-gray  { background: var(--muted); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.market-open   { color: var(--green); }
.market-closed { color: var(--muted); }
.timer-txt { color: var(--muted); font-size: 11px; }
.refresh-btn {
  background: transparent; border: 1px solid var(--border);
  color: var(--teal); padding: 5px 14px; border-radius: 4px;
  cursor: pointer; font-family: inherit; font-size: 12px;
}
.refresh-btn:hover { border-color: var(--teal); background: #081e18; }

/* ── Portfolio stats ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 10px;
}
.stat-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 18px;
}
.stat-label { font-size: 10px; letter-spacing: 2px; color: var(--muted); text-transform: uppercase; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: bold; color: var(--text); line-height: 1; }
.stat-sub   { font-size: 12px; color: var(--muted); margin-top: 5px; }
.positive { color: var(--green) !important; }
.negative { color: var(--red)   !important; }

/* ── Signals bar ── */
.signals-bar {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 11px 18px;
  display: flex; gap: 20px; align-items: center; flex-wrap: wrap;
  margin-bottom: 10px;
}
.sig-label { font-size: 10px; letter-spacing: 1.5px; color: var(--muted); text-transform: uppercase; margin-right: 6px; }
.sep { color: var(--border); }
.regime-bull     { color: var(--green); font-weight: bold; }
.regime-sideways { color: var(--amber); font-weight: bold; }
.regime-bear     { color: var(--red);   font-weight: bold; }
.kill-zone-on  { color: var(--amber); }
.kill-zone-off { color: var(--muted); }

/* ── Sections ── */
.section {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 18px; margin-bottom: 10px;
}
.sec-title {
  font-size: 10px; letter-spacing: 2px; color: var(--muted);
  text-transform: uppercase; margin-bottom: 12px;
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
}

/* ── Positions grid ── */
.pos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
.pos-card {
  background: #0f1a2e; border: 1px solid var(--border);
  border-radius: 6px; padding: 12px 14px;
}
.pos-ticker { font-size: 20px; font-weight: bold; color: var(--teal); margin-bottom: 8px; }
.pos-row { display: flex; justify-content: space-between; margin: 3px 0; }
.pos-key { color: var(--muted); font-size: 11px; }
.pos-val { font-size: 11px; }
.pos-pnl {
  margin-top: 8px; font-size: 16px; font-weight: bold;
  padding-top: 8px; border-top: 1px solid var(--border);
}

/* ── Trades table ── */
.trades-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.trades-tbl th {
  text-align: left; color: var(--muted); font-size: 10px;
  letter-spacing: 1.5px; text-transform: uppercase;
  padding: 4px 8px 8px 0; border-bottom: 1px solid var(--border);
}
.trades-tbl td { padding: 7px 8px 7px 0; border-bottom: 1px solid #0f1827; vertical-align: top; }
.trades-tbl tr:last-child td { border-bottom: none; }
.action-buy  { color: var(--green); font-weight: bold; }
.action-sell { color: var(--red);   font-weight: bold; }
.reason-row td { color: var(--muted); font-size: 11px; padding-top: 0; }

/* ── Weekly bars ── */
.week-bars { display: flex; gap: 6px; align-items: flex-end; height: 64px; margin-top: 4px; }
.wb-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.wb { width: 100%; border-radius: 3px 3px 0 0; min-height: 4px; }
.wb.pos { background: var(--green); opacity: 0.8; }
.wb.neg { background: var(--red);   opacity: 0.8; }
.wb-day  { font-size: 10px; color: var(--muted); }
.wb-pnl  { font-size: 9px; }

/* ── Learning ── */
.learn-entry { padding: 10px 0; border-bottom: 1px solid var(--border); }
.learn-entry:last-child { border-bottom: none; }
.learn-week { color: var(--muted); font-size: 11px; margin-bottom: 4px; }
.learn-line { margin: 3px 0; }
.outcome-testing  { color: var(--amber); }
.outcome-accepted { color: var(--green); }
.outcome-reverted { color: var(--red); }

/* ── Two col ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }

/* ── Empty ── */
.empty { color: var(--muted); font-style: italic; padding: 14px 0; text-align: center; }

@media (max-width: 720px) {
  .stats-row, .two-col { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-title">🤖 TRADING BOT — MISSION CONTROL</div>
  <div id="mode-badge"></div>
  <div id="market-badge"></div>
  <div class="ml-auto"></div>
  <div class="timer-txt" id="timer-txt">Loading...</div>
  <button class="refresh-btn" onclick="refreshAll()">↺ Refresh</button>
</div>

<!-- PORTFOLIO STATS -->
<div class="stats-row">
  <div class="stat-card">
    <div class="stat-label">Portfolio Value</div>
    <div class="stat-value" id="equity">—</div>
    <div class="stat-sub"  id="equity-sub"></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Free Cash</div>
    <div class="stat-value" id="cash">—</div>
    <div class="stat-sub"  id="cash-sub"></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Today's P&amp;L</div>
    <div class="stat-value" id="daily-pnl">—</div>
    <div class="stat-sub"  id="pnl-sub"></div>
  </div>
</div>

<!-- SIGNALS BAR -->
<div class="signals-bar">
  <div><span class="sig-label">Regime</span><span id="regime-d">—</span></div>
  <span class="sep">|</span>
  <div><span class="sig-label">Signal</span><span id="signal-d">—</span></div>
  <span class="sep">|</span>
  <div><span class="sig-label">Session</span><span id="session-d">—</span></div>
  <span class="sep">|</span>
  <div><span class="sig-label">Trade window</span><span id="window-d">—</span></div>
</div>

<!-- OPEN POSITIONS -->
<div class="section">
  <div class="sec-title">Open Positions</div>
  <div class="pos-grid" id="pos-grid"><div class="empty">Loading...</div></div>
</div>

<!-- TRADE HISTORY + WEEKLY P&L -->
<div class="two-col">
  <div class="section" style="margin:0">
    <div class="sec-title">Trade History</div>
    <div id="trades-list"><div class="empty">Loading...</div></div>
  </div>
  <div class="section" style="margin:0">
    <div class="sec-title">Weekly P&amp;L</div>
    <div id="weekly-pnl"><div class="empty">Loading...</div></div>
  </div>
</div>

<!-- SELF-LEARNING LOG -->
<div class="section">
  <div class="sec-title">🧠 Self-Learning Log</div>
  <div id="learning-log"><div class="empty">Loading...</div></div>
</div>

<script>
const REFRESH = 30;
let cd = REFRESH;

function fgbp(n, showPlus) {
  if (n == null) return '—';
  const abs = Math.abs(n).toLocaleString('en-GB', {minimumFractionDigits:2, maximumFractionDigits:2});
  const sign = n < 0 ? '-' : (showPlus ? '+' : '');
  return sign + '£' + abs;
}
function fpct(n) {
  if (n == null) return '';
  return (n >= 0 ? '+' : '') + (n * 100).toFixed(2) + '%';
}
function fdt(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', {day:'2-digit', month:'2-digit'}) + ' ' +
         d.toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit'});
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();
    if (!d.ok) return;

    // Mode
    const mode = d.mode;
    document.getElementById('mode-badge').innerHTML =
      `<span class="badge badge-${mode.toLowerCase()}">${mode}</span>`;

    // Market
    document.getElementById('market-badge').innerHTML = d.market_open
      ? `<span class="market-open"><span class="dot dot-green"></span>MARKET OPEN</span>`
      : `<span class="market-closed"><span class="dot dot-gray"></span>MARKET CLOSED</span>`;

    // Portfolio
    const a = d.account;
    document.getElementById('equity').textContent = fgbp(a.equity);
    document.getElementById('equity-sub').textContent = 'Buying power: ' + fgbp(a.buying_power);
    document.getElementById('cash').textContent = fgbp(a.cash);
    document.getElementById('cash-sub').textContent =
      d.positions.length + ' position' + (d.positions.length !== 1 ? 's' : '') + ' open';

    const pnlEl = document.getElementById('daily-pnl');
    pnlEl.textContent = fgbp(a.daily_pnl, true);
    pnlEl.className = 'stat-value ' + (a.daily_pnl > 0 ? 'positive' : a.daily_pnl < 0 ? 'negative' : '');
    document.getElementById('pnl-sub').textContent = fpct(a.daily_pnl_pct);

    // Regime
    const reg = d.regime;
    const rc = 'regime-' + reg.state;
    document.getElementById('regime-d').innerHTML =
      `<span class="${rc}">● ${reg.state.toUpperCase()}</span>`;
    document.getElementById('signal-d').innerHTML =
      `<span class="${reg.signal >= 0 ? 'positive' : 'negative'}">${(reg.signal*100).toFixed(0)}%</span>` +
      `<span style="color:var(--muted);font-size:11px"> Bull=${(reg.p_bull*100).toFixed(0)}% Bear=${(reg.p_bear*100).toFixed(0)}% · ${reg.conviction}</span>`;

    // Session
    const s = d.session;
    document.getElementById('session-d').innerHTML =
      s.time_et + ' ET ' + s.day +
      (s.in_kill_zone ? ' <span class="kill-zone-on">● Kill Zone</span>' : '');
    document.getElementById('window-d').innerHTML = s.can_trade
      ? `<span class="positive">✓ Open</span>`
      : `<span style="color:var(--muted)">✗ ${s.trade_reason}</span>`;

    // Positions
    const grid = document.getElementById('pos-grid');
    if (!d.positions.length) {
      grid.innerHTML = '<div class="empty">No open positions</div>';
    } else {
      grid.innerHTML = d.positions.map(p => {
        const pc = p.unrealized_pnl >= 0 ? 'positive' : 'negative';
        return `<div class="pos-card">
          <div class="pos-ticker">${p.symbol}</div>
          <div class="pos-row"><span class="pos-key">Shares</span><span class="pos-val">${p.qty}</span></div>
          <div class="pos-row"><span class="pos-key">Entry</span><span class="pos-val">${fgbp(p.avg_entry_price)}</span></div>
          <div class="pos-row"><span class="pos-key">Current</span><span class="pos-val">${fgbp(p.current_price)}</span></div>
          <div class="pos-row"><span class="pos-key">Value</span><span class="pos-val">${fgbp(p.market_value)}</span></div>
          <div class="pos-pnl ${pc}">${fgbp(p.unrealized_pnl, true)} (${(p.unrealized_pnl_pct*100).toFixed(1)}%)</div>
        </div>`;
      }).join('');
    }
  } catch(e) { console.error('status:', e); }
}

async function fetchTrades() {
  try {
    const res = await fetch('/api/trades');
    const d = await res.json();
    if (!d.ok) return;
    const el = document.getElementById('trades-list');
    if (!d.trades.length) {
      el.innerHTML = '<div class="empty">No trades yet — first decision at 2:30 PM UK time today</div>';
      return;
    }
    let rows = '';
    for (const t of d.trades) {
      const pc = t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : '';
      rows += `<tr>
        <td>${fdt(t.timestamp)}</td>
        <td class="action-${(t.action||'').toLowerCase()}">${t.action||'—'}</td>
        <td><b>${t.ticker||'—'}</b></td>
        <td>${t.notional ? fgbp(t.notional) : '—'}</td>
        <td class="${pc}">${t.pnl != null ? fgbp(t.pnl, true) : '—'}</td>
      </tr>`;
      if (t.reasoning) {
        rows += `<tr class="reason-row"><td colspan="5">↳ ${t.reasoning.substring(0,120)}${t.reasoning.length>120?'…':''}</td></tr>`;
      }
    }
    el.innerHTML = `<table class="trades-tbl">
      <thead><tr><th>Time</th><th>Action</th><th>Ticker</th><th>Size</th><th>P&amp;L</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  } catch(e) { console.error('trades:', e); }
}

async function fetchSummaries() {
  try {
    const res = await fetch('/api/summaries');
    const d = await res.json();
    if (!d.ok) return;
    const el = document.getElementById('weekly-pnl');
    if (!d.summaries.length) {
      el.innerHTML = '<div class="empty">Daily summaries appear after each market close (4:30 PM ET)</div>';
      return;
    }
    const items = d.summaries.slice(0, 7).reverse();
    const maxAbs = Math.max(...items.map(s => Math.abs(s.daily_pnl || 0)), 1);
    const total = d.summaries.reduce((a, s) => a + (s.daily_pnl || 0), 0);
    const bars = items.map(s => {
      const pnl = s.daily_pnl || 0;
      const h = Math.max(4, Math.round(Math.abs(pnl) / maxAbs * 50));
      const cls = pnl >= 0 ? 'pos' : 'neg';
      const day = new Date(s.date).toLocaleDateString('en-GB', {weekday:'short'});
      const pc = pnl >= 0 ? 'positive' : 'negative';
      return `<div class="wb-wrap">
        <div class="wb-pnl ${pc}">${fgbp(pnl, true).replace('£','')}</div>
        <div class="wb ${cls}" style="height:${h}px"></div>
        <div class="wb-day">${day}</div>
      </div>`;
    }).join('');
    const tc = total >= 0 ? 'positive' : 'negative';
    el.innerHTML = `<div class="week-bars">${bars}</div>
      <div style="color:var(--muted);font-size:11px;margin-top:10px">
        ${items.length}-day total: <span class="${tc}">${fgbp(total, true)}</span>
      </div>`;
  } catch(e) { console.error('summaries:', e); }
}

async function fetchLearning() {
  try {
    const res = await fetch('/api/learning');
    const d = await res.json();
    if (!d.ok) return;
    const el = document.getElementById('learning-log');
    if (!d.entries.length) {
      el.innerHTML = '<div class="empty">First self-learning review fires Sunday 8 AM ET</div>';
      return;
    }
    el.innerHTML = d.entries.map(e => `
      <div class="learn-entry">
        <div class="learn-week">Week of ${e.week_start} · ${e.trades_analysed||0} trades analysed</div>
        <div class="learn-line"><b>Worst pattern:</b> ${e.worst_pattern||'—'}</div>
        <div class="learn-line"><b>Hypothesis:</b> ${e.hypothesis||'—'}</div>
        <div class="learn-line">Status: <span class="outcome-${e.outcome}">${(e.outcome||'').toUpperCase()}</span>
          ${e.metric_before!=null ? ' · Win rate before: '+(e.metric_before*100).toFixed(0)+'%' : ''}
          ${e.metric_after!=null  ? ' → after: '+(e.metric_after*100).toFixed(0)+'%' : ''}
        </div>
      </div>`).join('');
  } catch(e) { console.error('learning:', e); }
}

async function refreshAll() {
  cd = REFRESH;
  document.getElementById('timer-txt').textContent = 'Refreshing…';
  await Promise.all([fetchStatus(), fetchTrades(), fetchSummaries(), fetchLearning()]);
  document.getElementById('timer-txt').textContent = `Refreshes in ${cd}s`;
}

setInterval(() => {
  cd--;
  document.getElementById('timer-txt').textContent = `Refreshes in ${cd}s`;
  if (cd <= 0) refreshAll();
}, 1000);

refreshAll();
</script>
</body>
</html>"""


# ── API routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return DASHBOARD_HTML


@app.route("/api/status")
def api_status():
    try:
        from data.trading212_client import Trading212Client
        from brain.markov_regime import get_regime_signal
        from brain.session_filter import get_session_context

        t212 = Trading212Client()
        account   = t212.get_account()
        positions = t212.get_positions()
        regime    = get_regime_signal()
        session   = get_session_context()

        return jsonify({
            "ok": True,
            "mode":        os.getenv("T212_MODE", "demo").upper(),
            "market_open": t212.is_market_open(),
            "timestamp":   datetime.now(pytz.UTC).isoformat(),
            "account":     account,
            "positions":   positions,
            "regime": {
                "state":     regime.get("current_state"),
                "signal":    regime.get("signal"),
                "conviction":regime.get("conviction"),
                "p_bull":    regime.get("p_bull_tomorrow"),
                "p_bear":    regime.get("p_bear_tomorrow"),
                "summary":   regime.get("summary"),
            },
            "session": {
                "time_et":     session.get("time_et"),
                "day":         session.get("day"),
                "can_trade":   session.get("can_open_new_trade"),
                "trade_reason":session.get("trade_window_reason"),
                "in_kill_zone":session.get("in_kill_zone"),
            },
        })
    except Exception as e:
        log.error(f"[Dashboard] /api/status error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/trades")
def api_trades():
    try:
        from database.supabase_client import get_recent_trades
        return jsonify({"ok": True, "trades": get_recent_trades(limit=30)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/summaries")
def api_summaries():
    try:
        from database.supabase_client import _client
        result = (
            _client()
            .table("daily_summaries")
            .select("*")
            .order("timestamp", desc=True)
            .limit(7)
            .execute()
        )
        return jsonify({"ok": True, "summaries": result.data or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/learning")
def api_learning():
    try:
        from database.supabase_client import _client
        result = (
            _client()
            .table("learning_log")
            .select("*")
            .order("timestamp", desc=True)
            .limit(5)
            .execute()
        )
        return jsonify({"ok": True, "entries": result.data or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Bot scheduler thread ──────────────────────────────────────

def _run_bot():
    """Runs the trading bot scheduler in a background daemon thread."""
    try:
        from scheduler.main_loop import run_bot
        run_bot()
    except Exception as e:
        log.critical(f"[Dashboard] Bot scheduler thread crashed: {e}\n{traceback.format_exc()}")


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Launch the bot in a background thread
    bot_thread = threading.Thread(target=_run_bot, daemon=True, name="bot-scheduler")
    bot_thread.start()
    log.info("[Dashboard] Bot scheduler started in background thread")

    # Start the Flask web server (Railway assigns PORT)
    port = int(os.getenv("PORT", 8080))
    log.info(f"[Dashboard] Web server starting on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
