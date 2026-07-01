"""
Trading Bot — The Trading Tavern Dashboard
Six animated agents patrol the tavern doing their jobs.
Railway assigns a public URL to this web process automatically.
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

# ── Tavern HTML ───────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Trading Tavern</title>
<style>
:root {
  --wood-dark:  #120a03;
  --wood-mid:   #1e0f05;
  --wood:       #2c1508;
  --wood-light: #3d2010;
  --bar:        #4a2a0f;
  --parchment:  #f5e6c8;
  --parch-dim:  #c9b48a;
  --ink:        #1a0c05;
  --gold:       #c9a227;
  --gold-light: #e8c547;
  --amber:      #ff9500;
  --fire:       #ff4500;
  --green:      #6dff6d;
  --red:        #ff5555;
  --muted:      #7a6045;
  --border:     #5a3515;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--wood-dark);
  color: var(--parchment);
  font-family: Georgia, 'Times New Roman', serif;
  min-height: 100vh;
  overflow-x: hidden;
}

/* ── TAVERN SIGN ── */
.sign {
  background: linear-gradient(180deg, #3a1e08 0%, var(--wood) 100%);
  border-bottom: 3px solid var(--gold);
  padding: 11px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.6);
}
.sign-title {
  font-size: 17px;
  font-weight: bold;
  color: var(--gold-light);
  text-shadow: 0 0 12px rgba(201,162,39,0.6);
  letter-spacing: 2px;
}
.mode-badge {
  font-family: monospace;
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 3px;
  border: 1px solid;
  font-weight: bold;
  letter-spacing: 1px;
}
.badge-demo { color: #4a9eff; border-color: #4a9eff; background: rgba(74,158,255,0.1); }
.badge-live { color: var(--amber); border-color: var(--amber); background: rgba(255,149,0,0.1); }
.ml-auto { margin-left: auto; }
.market-ind { display: flex; align-items: center; gap: 6px; font-size: 12px; font-family: monospace; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-open   { background: var(--green); box-shadow: 0 0 8px var(--green); animation: blink 2s infinite; }
.dot-closed { background: var(--muted); }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
.timer { font-family: monospace; font-size: 11px; color: var(--muted); }
.refresh-btn {
  background: transparent; border: 1px solid var(--border); color: var(--gold);
  padding: 5px 14px; border-radius: 4px; cursor: pointer;
  font-family: Georgia, serif; font-size: 12px;
}
.refresh-btn:hover { border-color: var(--gold); background: rgba(201,162,39,0.08); }

/* ── MAIN ── */
.main { padding: 14px; }

/* ── TOP ROW ── */
.top-row {
  display: grid;
  grid-template-columns: 1fr 90px 1fr;
  gap: 12px;
  margin-bottom: 14px;
  align-items: start;
}

/* Notice board */
.notice-board {
  background: #2a1a08;
  border: 3px solid var(--border);
  border-radius: 3px;
  padding: 12px 14px;
  transform: rotate(-0.6deg);
  box-shadow: 4px 4px 0 rgba(0,0,0,0.6);
  position: relative;
}
.notice-board::before {
  content: '📋  NOTICE BOARD';
  display: block;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--gold);
  margin-bottom: 9px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.notice-pin {
  position: absolute; top: -8px; left: 50%;
  transform: translateX(-50%);
  width: 14px; height: 14px;
  background: var(--amber); border-radius: 50%;
  border: 2px solid var(--gold);
}
.nb-row { display: flex; justify-content: space-between; margin: 5px 0; font-size: 13px; }
.nb-label { color: var(--muted); font-size: 11px; }
.nb-val { font-weight: bold; }
.nb-val.pos { color: var(--green); }
.nb-val.neg { color: var(--red); }

/* Fire */
.fireplace { text-align: center; padding: 6px 0; }
.fire { font-size: 44px; display: block; animation: flicker 0.5s infinite alternate;
  filter: drop-shadow(0 0 18px rgba(255,69,0,0.9)); }
@keyframes flicker { 0%{transform:scale(1) rotate(-1deg)} 100%{transform:scale(1.06) rotate(1.5deg)} }
.fire-glow {
  width: 70px; height: 16px; margin: 0 auto;
  background: radial-gradient(ellipse, rgba(255,69,0,0.35) 0%, transparent 70%);
}

/* Chalkboard */
.chalkboard {
  background: #152a15;
  border: 4px solid var(--border);
  border-radius: 3px;
  padding: 12px 14px;
  transform: rotate(0.4deg);
  box-shadow: 4px 4px 0 rgba(0,0,0,0.6);
  font-family: monospace;
}
.chalkboard::before {
  content: '🗒  MARKET STATUS';
  display: block;
  font-size: 10px;
  letter-spacing: 2px;
  color: #90c890;
  margin-bottom: 9px;
  padding-bottom: 6px;
  border-bottom: 1px solid #1e3e1e;
}
.ck-line { margin: 5px 0; font-size: 12px; color: #c8f0c8; }
.ck-lbl { color: #5a805a; font-size: 10px; letter-spacing: 1px; }
.r-bull  { color: var(--green); font-weight: bold; }
.r-side  { color: var(--amber); font-weight: bold; }
.r-bear  { color: var(--red);   font-weight: bold; }
.kz-on   { color: var(--amber); }
.kz-off  { color: #3a5a3a; }
.win-ok  { color: var(--green); }
.win-no  { color: var(--muted); }

/* ── BAR COUNTER ── */
.bar-counter {
  height: 10px;
  background: linear-gradient(to right, var(--bar), #6a3a15, var(--bar));
  border-top: 2px solid var(--gold);
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

/* ── FLOOR ── */
.floor {
  background: repeating-linear-gradient(
    90deg,
    #1e0f05 0px, #1e0f05 55px,
    #261308 55px, #261308 57px
  );
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 12px;
}

/* ── CHARACTERS ── */
.chars {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.char { display: flex; flex-direction: column; align-items: center; gap: 5px; }

/* Speech bubble */
.bubble {
  background: rgba(245, 230, 200, 0.10);
  border: 1px solid var(--gold);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--parchment);
  text-align: center;
  max-width: 160px;
  min-height: 38px;
  display: flex; align-items: center; justify-content: center;
  position: relative;
  line-height: 1.4;
}
.bubble::after {
  content: '';
  position: absolute; bottom: -7px; left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: var(--gold);
}

/* Sprite */
.sprite {
  font-size: 42px;
  line-height: 1;
  animation: idle 3s ease-in-out infinite;
}
@keyframes idle { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }
.sprite.active  { animation: act  0.9s ease-in-out infinite; }
@keyframes act  { 0%,100%{transform:translateY(0) scale(1)} 50%{transform:translateY(-7px) scale(1.06)} }
.sprite.happy   { animation: jump 0.45s ease-in-out 4; }
@keyframes jump { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-14px)} }
.sprite.alert   { animation: flash 0.4s ease-in-out infinite; }
@keyframes flash{ 0%,100%{opacity:1} 50%{opacity:0.3} }
.sprite.sleep   { animation: sway 4s ease-in-out infinite; opacity:0.5; }
@keyframes sway { 0%,100%{transform:rotate(-3deg)} 50%{transform:rotate(3deg)} }

.char-name { font-size: 11px; letter-spacing: 1.5px; color: var(--gold); text-transform: uppercase; }
.char-role { font-size: 10px; color: var(--muted); }

/* ── ACTIVITY LOG ── */
.log-wrap {
  background: var(--wood-mid);
  border: 1px solid var(--border);
  border-top: 3px solid var(--gold);
  border-radius: 4px;
  padding: 12px 16px;
}
.log-title { font-size: 10px; letter-spacing: 2px; color: var(--gold); text-transform: uppercase; margin-bottom: 10px; }
.log-scroll { max-height: 200px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
.log-row { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px solid rgba(90,53,21,0.35); font-size: 12px; align-items: flex-start; }
.log-row:last-child { border-bottom: none; }
.log-time { color: var(--muted); font-family: monospace; font-size: 11px; white-space: nowrap; min-width: 38px; }
.log-icon { flex-shrink: 0; width: 22px; text-align: center; }
.log-msg  { color: var(--parchment); line-height: 1.4; }
.log-msg .hl   { color: var(--gold-light); }
.log-msg .pos  { color: var(--green); }
.log-msg .neg  { color: var(--red); }
.log-msg .dim  { color: var(--muted); font-size: 10px; }

@media(max-width:600px){
  .top-row,.chars{ grid-template-columns:1fr; }
  .fireplace{ display:none; }
}
</style>
</head>
<body>

<!-- SIGN -->
<div class="sign">
  <span class="sign-title">⚔️ THE TRADING TAVERN</span>
  <div id="mode-badge"></div>
  <div id="market-badge" class="market-ind"></div>
  <div class="ml-auto"></div>
  <span class="timer" id="timer">Loading...</span>
  <button class="refresh-btn" onclick="refreshAll()">↺ Refresh</button>
</div>

<div class="main">

  <!-- TOP ROW: notice board | fire | chalkboard -->
  <div class="top-row">

    <div class="notice-board">
      <div class="notice-pin"></div>
      <div class="nb-row"><span class="nb-label">Treasury</span>    <span class="nb-val" id="nb-eq">—</span></div>
      <div class="nb-row"><span class="nb-label">Reserves</span>    <span class="nb-val" id="nb-cash">—</span></div>
      <div class="nb-row"><span class="nb-label">Today's haul</span><span class="nb-val" id="nb-pnl">—</span></div>
      <div class="nb-row"><span class="nb-label">Open trades</span> <span class="nb-val" id="nb-pos">—</span></div>
    </div>

    <div class="fireplace">
      <span class="fire">🔥</span>
      <div class="fire-glow"></div>
    </div>

    <div class="chalkboard">
      <div class="ck-line"><span class="ck-lbl">REGIME  </span><span id="ck-regime">—</span></div>
      <div class="ck-line"><span class="ck-lbl">SIGNAL  </span><span id="ck-signal">—</span></div>
      <div class="ck-line"><span class="ck-lbl">SESSION </span><span id="ck-session">—</span></div>
      <div class="ck-line"><span class="ck-lbl">WINDOW  </span><span id="ck-window">—</span></div>
    </div>

  </div>

  <!-- BAR COUNTER -->
  <div class="bar-counter"></div>

  <!-- TAVERN FLOOR WITH AGENTS -->
  <div class="floor">
    <div class="chars">

      <div class="char">
        <div class="bubble" id="b-sage">Awaiting the market's whisper...</div>
        <div class="sprite" id="s-sage">🧠</div>
        <div class="char-name">The Sage</div>
        <div class="char-role">Decision Engine · Claude Haiku</div>
      </div>

      <div class="char">
        <div class="bubble" id="b-banker">Counting the treasury...</div>
        <div class="sprite" id="s-banker">💰</div>
        <div class="char-name">The Banker</div>
        <div class="char-role">Portfolio Manager</div>
      </div>

      <div class="char">
        <div class="bubble" id="b-trader">Blade at the ready...</div>
        <div class="sprite" id="s-trader">⚔️</div>
        <div class="char-name">The Trader</div>
        <div class="char-role">Trade Executor</div>
      </div>

      <div class="char">
        <div class="bubble" id="b-scout">Reading the stars...</div>
        <div class="sprite" id="s-scout">🔭</div>
        <div class="char-name">The Scout</div>
        <div class="char-role">Markov Regime Detector</div>
      </div>

      <div class="char">
        <div class="bubble" id="b-watch">All quiet on the floor...</div>
        <div class="sprite" id="s-watch">📊</div>
        <div class="char-name">The Watchman</div>
        <div class="char-role">Position Monitor</div>
      </div>

      <div class="char">
        <div class="bubble" id="b-scribe">Scanning the scrolls...</div>
        <div class="sprite" id="s-scribe">📜</div>
        <div class="char-name">The Scribe</div>
        <div class="char-role">News &amp; Data</div>
      </div>

    </div>
  </div>

  <!-- ACTIVITY LOG -->
  <div class="log-wrap">
    <div class="log-title">⚡ Tavern Log — Recent Activity</div>
    <div class="log-scroll" id="log"></div>
  </div>

</div>

<script>
const REFRESH = 30;
let cd = REFRESH;
let logEntries = [];
let lastStatus = null;
let tradesLoaded = false;

function f(n, plus) {
  if (n == null) return '—';
  const s = Math.abs(n).toLocaleString('en-GB', {minimumFractionDigits:2, maximumFractionDigits:2});
  return (n < 0 ? '-£' : (plus && n > 0 ? '+£' : '£')) + s;
}
function pct(n) { return n == null ? '' : (n>=0?'+':'')+(n*100).toFixed(2)+'%'; }
function ftime(iso) {
  return new Date(iso).toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit'});
}
function fdt(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB',{day:'2-digit',month:'2-digit'}) + ' ' +
         d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
}

function addLog(time, icon, html) {
  logEntries.unshift({time, icon, html});
  if (logEntries.length > 25) logEntries.pop();
  renderLog();
}

function renderLog() {
  const el = document.getElementById('log');
  if (!logEntries.length) {
    el.innerHTML = '<div style="color:var(--muted);font-style:italic;padding:8px 0">The tavern is quiet... market opens at 2:30 PM UK time</div>';
    return;
  }
  el.innerHTML = logEntries.map(e =>
    `<div class="log-row">
      <span class="log-time">${e.time}</span>
      <span class="log-icon">${e.icon}</span>
      <span class="log-msg">${e.html}</span>
    </div>`).join('');
}

function set(id, txt) { const e=document.getElementById(id); if(e) e.textContent=txt; }
function setH(id, html){ const e=document.getElementById(id); if(e) e.innerHTML=html; }
function cls(id, c) { const e=document.getElementById(id); if(e) e.className='sprite '+c; }

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    if (!d.ok) return;

    const a   = d.account;
    const reg = d.regime;
    const s   = d.session;
    const pos = d.positions;

    // Sign badges
    setH('mode-badge', `<span class="mode-badge badge-${d.mode.toLowerCase()}">${d.mode}</span>`);
    setH('market-badge', d.market_open
      ? `<span class="dot dot-open"></span> MARKET OPEN`
      : `<span class="dot dot-closed"></span> MARKET CLOSED`);

    // Notice board
    const pnl = a.daily_pnl;
    setH('nb-eq',   `<span>${f(a.equity)}</span>`);
    setH('nb-cash', `<span>${f(a.cash)}</span>`);
    document.getElementById('nb-pnl').innerHTML =
      `<span class="${pnl >= 0 ? 'pos' : 'neg'}">${f(pnl,true)} (${pct(a.daily_pnl_pct)})</span>`;
    set('nb-pos', pos.length + (pos.length === 1 ? ' trade' : ' trades'));

    // Chalkboard
    const rc = reg.state === 'bull' ? 'r-bull' : reg.state === 'bear' ? 'r-bear' : 'r-side';
    setH('ck-regime', `<span class="${rc}">● ${reg.state.toUpperCase()}</span>`);
    setH('ck-signal', `<span class="${pnl>=0?'r-bull':'r-bear'}">${(reg.signal*100).toFixed(0)}%</span>` +
      ` <span style="color:var(--muted);font-size:10px">Bull ${(reg.p_bull*100).toFixed(0)}% / Bear ${(reg.p_bear*100).toFixed(0)}%</span>`);
    setH('ck-session', s.time_et + ' ET ' + s.day +
      (s.in_kill_zone ? ' <span class="kz-on">⚡ Kill Zone</span>' : ''));
    setH('ck-window', s.can_trade
      ? `<span class="win-ok">✓ Open for trades</span>`
      : `<span class="win-no">✗ ${s.trade_reason}</span>`);

    // ── Agent bubbles & animations ──

    // 🧠 SAGE
    if (!d.market_open) {
      set('b-sage', 'Resting by the fire... market is closed');
      cls('s-sage', 'sleep');
    } else if (!s.can_trade) {
      set('b-sage', `Taking a break — ${s.trade_reason}`);
      cls('s-sage', '');
    } else {
      set('b-sage', `Deliberating... ${reg.conviction} conviction. Signal: ${(reg.signal*100).toFixed(0)}%`);
      cls('s-sage', 'active');
    }

    // 💰 BANKER
    set('b-banker', `Treasury: ${f(a.equity)} · ${pos.length} position${pos.length!==1?'s':''}`);
    cls('s-banker', pnl > 0 ? 'happy' : pnl < 0 ? 'alert' : '');

    // ⚔️ TRADER
    if (!d.market_open) {
      set('b-trader', 'Sheathed. Awaiting dawn...');
      cls('s-trader', 'sleep');
    } else {
      set('b-trader', s.can_trade ? 'Ready to strike on the Sage\'s word' : 'Standing by...');
      cls('s-trader', s.can_trade ? 'active' : '');
    }

    // 🔭 SCOUT
    const scoutMsg = `${reg.state.toUpperCase()} regime · ${reg.conviction}`;
    set('b-scout', scoutMsg);
    cls('s-scout', reg.state === 'bear' ? 'alert' : reg.state === 'bull' ? 'active' : '');

    // 📊 WATCHMAN
    if (pos.length === 0) {
      set('b-watch', 'No open positions. All clear.');
      cls('s-watch', '');
    } else {
      const pnlSum = pos.reduce((a, p) => a + (p.unrealized_pnl || 0), 0);
      set('b-watch', `Watching ${pos.length} trade${pos.length>1?'s':''} · ${f(pnlSum,true)} unrealised`);
      cls('s-watch', pnlSum >= 0 ? 'active' : 'alert');
    }

    // 📜 SCRIBE
    set('b-scribe', d.market_open
      ? 'Scanning news feeds and macro events...'
      : 'Archives sealed until market opens');
    cls('s-scribe', d.market_open ? 'active' : 'sleep');

    // ── Log events on state change ──
    const now = s.time_et || '--:--';
    if (lastStatus) {
      if (lastStatus.regime?.state !== reg.state) {
        const newRc = reg.state === 'bull' ? 'pos' : reg.state === 'bear' ? 'neg' : '';
        addLog(now, '🔭', `Scout reports: regime shifted to <span class="${newRc}">${reg.state.toUpperCase()}</span> — ${reg.conviction} conviction`);
      }
      if (!lastStatus.market_open && d.market_open) {
        addLog(now, '🔔', '<span class="hl">Market opened — all agents to their posts!</span>');
      }
      if (lastStatus.market_open && !d.market_open) {
        addLog(now, '🌙', 'Market closed — agents standing down for the night');
      }
      if (s.in_kill_zone && !lastStatus.session?.in_kill_zone) {
        addLog(now, '⚡', '<span class="hl">NY Kill Zone active</span> — Sage on high alert for entries');
      }
    } else {
      // First load
      addLog(now, '🏰', `Tavern opened · Mode: <span class="hl">${d.mode}</span> · Market: ${d.market_open ? '<span class="pos">OPEN</span>' : '<span class="dim">CLOSED</span>'}`);
      addLog(now, '🔭', `Scout reading: <span class="${rc}">${reg.state.toUpperCase()}</span> regime · Signal ${(reg.signal*100).toFixed(0)}%`);
      addLog(now, '💰', `Banker: Treasury ${f(a.equity)} · Cash ${f(a.cash)}`);
      if (pos.length > 0) {
        for (const p of pos) {
          const ppc = p.unrealized_pnl >= 0 ? 'pos' : 'neg';
          addLog(now, '📊', `Watchman: holding <span class="hl">${p.symbol}</span> · P&L <span class="${ppc}">${f(p.unrealized_pnl,true)} (${(p.unrealized_pnl_pct*100).toFixed(1)}%)</span>`);
        }
      }
    }

    lastStatus = d;
  } catch(e) { console.error('status:', e); }
}

async function fetchTrades() {
  try {
    const r = await fetch('/api/trades');
    const d = await r.json();
    if (!d.ok) return;

    if (d.trades.length > 0) {
      const last = d.trades[0];
      const isBuy = last.action === 'BUY';
      set('b-trader', `Last: ${last.action} ${last.ticker}${last.notional ? ' '+f(last.notional) : ''}`);
      if (isBuy) cls('s-trader', 'happy');
    }

    if (!tradesLoaded && d.trades.length > 0) {
      tradesLoaded = true;
      for (const t of d.trades.slice(0, 10)) {
        const isBuy = t.action === 'BUY';
        const ppc   = t.pnl != null ? (t.pnl >= 0 ? 'pos' : 'neg') : '';
        const pnlHtml = t.pnl != null
          ? ` · P&L <span class="${ppc}">${f(t.pnl, true)}</span>` : '';
        const reason = t.reasoning
          ? `<br><span class="dim">↳ ${t.reasoning.substring(0,90)}${t.reasoning.length>90?'…':''}</span>`
          : '';
        addLog(fdt(t.timestamp), isBuy ? '⚔️' : '🪙',
          `Trader ${isBuy ? '<span class="pos">acquired</span>' : '<span class="neg">sold</span>'} <span class="hl">${t.ticker}</span>` +
          (t.notional ? ` for ${f(t.notional)}` : '') + pnlHtml + reason);
      }
    }

    if (d.trades.length === 0) {
      set('b-trader', 'No trades yet — awaiting the Sage\'s order');
    }
  } catch(e) { console.error('trades:', e); }
}

async function refreshAll() {
  cd = REFRESH;
  set('timer', 'Refreshing…');
  await Promise.all([fetchStatus(), fetchTrades()]);
  set('timer', `Refreshes in ${cd}s`);
}

setInterval(() => {
  cd--;
  set('timer', `Refreshes in ${cd}s`);
  if (cd <= 0) refreshAll();
}, 1000);

renderLog();
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

        t212      = Trading212Client()
        account   = t212.get_account()
        positions = t212.get_positions()
        regime    = get_regime_signal()
        session   = get_session_context()

        return jsonify({
            "ok":          True,
            "mode":        os.getenv("T212_MODE", "demo").upper(),
            "market_open": t212.is_market_open(),
            "timestamp":   datetime.now(pytz.UTC).isoformat(),
            "account":     account,
            "positions":   positions,
            "regime": {
                "state":      regime.get("current_state"),
                "signal":     regime.get("signal"),
                "conviction": regime.get("conviction"),
                "p_bull":     regime.get("p_bull_tomorrow"),
                "p_bear":     regime.get("p_bear_tomorrow"),
                "summary":    regime.get("summary"),
            },
            "session": {
                "time_et":      session.get("time_et"),
                "day":          session.get("day"),
                "can_trade":    session.get("can_open_new_trade"),
                "trade_reason": session.get("trade_window_reason"),
                "in_kill_zone": session.get("in_kill_zone"),
            },
        })
    except Exception as e:
        log.error(f"[Dashboard] /api/status: {e}")
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
        result = _client().table("daily_summaries").select("*").order("timestamp", desc=True).limit(7).execute()
        return jsonify({"ok": True, "summaries": result.data or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/learning")
def api_learning():
    try:
        from database.supabase_client import _client
        result = _client().table("learning_log").select("*").order("timestamp", desc=True).limit(5).execute()
        return jsonify({"ok": True, "entries": result.data or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Bot scheduler thread ──────────────────────────────────────

def _run_bot():
    try:
        from scheduler.main_loop import run_bot
        run_bot()
    except Exception as e:
        log.critical(f"[Dashboard] Scheduler crashed: {e}\n{traceback.format_exc()}")


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    bot_thread = threading.Thread(target=_run_bot, daemon=True, name="bot-scheduler")
    bot_thread.start()
    log.info("[Dashboard] Bot scheduler started in background thread")

    port = int(os.getenv("PORT", 8080))
    log.info(f"[Dashboard] Web server on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
