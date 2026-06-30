# Trading Bot — Setup Guide

**Total time remaining:** ~10 minutes | **Monthly cost:** ~£5 (Railway Hobby)

---

## ✅ ALREADY DONE — skip these

| Done | What |
|------|------|
| ✅ | **Anthropic API key** — set in `.env` |
| ✅ | **Supabase** — project created, anon key set in `.env`, all 3 tables migrated |
| ✅ | **Trading 212 client** — UK broker integration built (replaces Alpaca) |
| ✅ | **TradingView signals** — live screener wired into every decision (no key needed) |
| ✅ | **ICT PM range + Markov regime** — all 29 bot files pass syntax check |
| ✅ | **Railway config** — `railway.json` + `Procfile` already set up |

---

## ⚡ YOUR 4 REMAINING ACTIONS

### 1. Trading 212 — get API key (2 min, phone required)
Open the **Trading 212 app** on your phone  
→ Settings → API (Beta) → Generate key  
→ Paste into `.env` as `T212_API_KEY`  
→ Leave `T212_MODE=demo` until ready to go live

### 2. Telegram — create bot (3 min, phone required)
Open Telegram on your phone → search **@BotFather** → `/newbot`  
→ Paste token into `.env` as `TELEGRAM_BOT_TOKEN`  
→ Send your new bot any message, then open:  
`https://api.telegram.org/botYOUR_TOKEN/getUpdates`  
→ Grab the `"id"` from `"chat"` → paste as `TELEGRAM_CHAT_ID`

### 3. Deploy to Railway (5 min)

**Option A — Railway CLI (fastest):**
Open a terminal (PowerShell/CMD) in your `trading-bot` folder and run:
```
pip install railway
railway login
```
Railway will open your browser, you click **Connect**. Then:
```
railway init
railway variables set ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
railway variables set SUPABASE_URL=YOUR_SUPABASE_URL
railway variables set SUPABASE_KEY=YOUR_SUPABASE_KEY
railway variables set T212_MODE=demo
railway variables set T212_API_KEY=PASTE_YOUR_T212_API_KEY_HERE
railway variables set T212_SECRET_KEY=PASTE_YOUR_T212_SECRET_KEY_HERE
railway variables set TELEGRAM_BOT_TOKEN=PASTE_YOUR_TOKEN_HERE
railway variables set TELEGRAM_CHAT_ID=PASTE_YOUR_CHAT_ID_HERE
railway up
```

**Option B — GitHub + Railway dashboard (no terminal):**
1. Right-click `push_to_github.ps1` → **Run with PowerShell** (pushes code to GitHub)
2. Go to [railway.com/new](https://railway.com/new) → **Deploy a GitHub Repo** → select `Tommysn2/trading-bot`
3. In the Railway project → **Variables** tab → add all 7 variables from your `.env` file
4. Railway auto-deploys. Click **Deploy** if it doesn't start automatically.

> ⚠️ **Railway requires upgrading from Trial** — click "Choose a Plan" and pick **Hobby ($5/mo)**. Without it, your bot will go offline after the trial credit runs out.

### 4. Upgrade Railway plan (required for 24/7 uptime)
Go to [railway.com/account/billing](https://railway.com/account/billing) → Choose **Hobby ($5/mo)**  
This keeps the bot running 24/7. Without it, Railway pauses after free credit.

---

## ENVIRONMENT VARIABLES (copy these into Railway)

Once your Railway project is created, go to **Variables** tab and add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | *(copy from your `.env` file)* |
| `SUPABASE_URL` | *(copy from your `.env` file)* |
| `SUPABASE_KEY` | *(copy from your `.env` file)* |
| `T212_API_KEY` | *(from your Trading 212 app — API Key)* |
| `T212_SECRET_KEY` | *(from your Trading 212 app — Secret Key)* |
| `T212_MODE` | `demo` |
| `TELEGRAM_BOT_TOKEN` | *(from @BotFather)* |
| `TELEGRAM_CHAT_ID` | *(from getUpdates URL)* |

---

## AFTER DEPLOYMENT — verify it's working

Railway → your project → **Deployments** tab → click the active deployment → **View Logs**

You should see lines like:
```
[Scheduler] Bot started. Waiting for market open...
[Position check] 0 positions | Day P&L: +0.0% | CB: normal
[Decision] HOLD — Market regime: sideways. No strong signals.
```

**Check Telegram** — you should receive "Bot started" message.

---

## WHAT THE BOT DOES EACH DAY

| Time (ET) | Action |
|---|---|
| Market open | Position check every 5 min |
| 7–10 AM | NY Kill Zone — highest priority entries |
| Every 30 min | Full signal scan → Claude Haiku decision → trade if warranted |
| 12–1:30 PM | Lunch — no new entries |
| 3:30 PM Fri | Weekend decision — hold or go cash |
| 4:30 PM | Nightly summary → Telegram + Supabase |
| Sunday 8 AM | Self-learning review — Sonnet proposes rule improvements |

---

## GO LIVE (when ready, after 2-4 weeks demo)

1. Open Trading 212 app → Settings → API (Beta) → toggle to **Live mode** → generate live key
2. In Railway → Variables → update `T212_API_KEY` to your live key, set `T212_MODE=live`
3. Railway auto-redeploys
4. Telegram will confirm: **"Bot started — LIVE mode"**

Start with £200–300 to verify execution before depositing full amount.

---

## COSTS

| Item | Monthly |
|---|---|
| Railway Hobby | $5 (~£4) |
| Anthropic (Haiku + Sonnet) | ~£3–4 |
| Supabase | Free |
| Trading 212 | Free (commission-free) |
| Telegram | Free |
| **Total** | **~£7–8/month** |
