-- Run this in Supabase SQL editor to create the required tables.
-- Go to: https://supabase.com → your project → SQL Editor → New query

-- 1. Trades table (every buy/sell the bot makes)
CREATE TABLE IF NOT EXISTS trades (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    price       NUMERIC(12, 4),
    qty         NUMERIC(12, 6),
    notional    NUMERIC(12, 2),
    regime      TEXT,                  -- bull / sideways / bear
    signal_strength NUMERIC(4, 3),    -- 0.0 to 1.0 confidence
    reasoning   TEXT,
    source      TEXT DEFAULT 'bot',    -- bot / manual
    pnl         NUMERIC(12, 2),        -- filled when position closes
    pnl_pct     NUMERIC(8, 4),         -- % return on this trade
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for querying recent trades quickly
CREATE INDEX IF NOT EXISTS trades_timestamp_idx ON trades (timestamp DESC);
CREATE INDEX IF NOT EXISTS trades_ticker_idx ON trades (ticker);

-- 2. Daily summaries table
CREATE TABLE IF NOT EXISTS daily_summaries (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    equity          NUMERIC(12, 2),
    daily_pnl       NUMERIC(12, 2),
    daily_pnl_pct   NUMERIC(8, 4),
    open_positions  INTEGER,
    regime          TEXT,
    regime_signal   NUMERIC(6, 3),     -- Markov signal value
    notes           TEXT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Self-learning log
CREATE TABLE IF NOT EXISTS learning_log (
    id              BIGSERIAL PRIMARY KEY,
    week_start      DATE,
    trades_analysed INTEGER,
    worst_pattern   TEXT,              -- e.g. "bear regime trades"
    hypothesis      TEXT,              -- the proposed rule change
    outcome         TEXT,              -- testing / accepted / reverted
    metric_before   NUMERIC(8, 4),     -- win rate or P&L before change
    metric_after    NUMERIC(8, 4),     -- win rate or P&L after 2 weeks
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable Row Level Security (optional but recommended)
-- For now, the bot uses the service_role key so RLS not required.
