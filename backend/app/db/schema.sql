-- StockFind Pro — database schema
-- Design principle: every fact that could change over time (fundamentals, estimates,
-- ownership, short interest) carries an `available_on` timestamp recording when that
-- fact became publicly known. All scoring/backtesting code must filter on
-- available_on <= as_of_date so historical simulations never use information that
-- would not have existed at that point in time (no look-ahead bias).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    ticker              TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    sector              TEXT NOT NULL,
    industry            TEXT NOT NULL,
    exchange            TEXT NOT NULL DEFAULT 'NASDAQ',
    ipo_date            TEXT,
    shares_outstanding  REAL,
    float_shares        REAL,
    beta                REAL DEFAULT 1.0
);

-- Daily OHLCV price bars. This is the backbone for all technical/momentum signals.
CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL REFERENCES companies(ticker),
    date        TEXT NOT NULL,          -- ISO date, e.g. 2024-03-14
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);

-- Benchmark index bars (S&P 500, Nasdaq) used for relative strength & backtest comparison.
CREATE TABLE IF NOT EXISTS benchmark_prices (
    symbol      TEXT NOT NULL,          -- 'SPX' or 'NDX'
    date        TEXT NOT NULL,
    close       REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- Quarterly fundamentals, point-in-time. `available_on` = the date this quarter's
-- figures were actually filed/released (mirrors SEC EDGAR company-facts semantics).
CREATE TABLE IF NOT EXISTS fundamentals_quarterly (
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    fiscal_period       TEXT NOT NULL,   -- e.g. 2024Q1
    period_end          TEXT NOT NULL,
    available_on        TEXT NOT NULL,   -- when this became public (filing/release date)
    revenue             REAL,
    eps                 REAL,
    fcf                 REAL,
    gross_margin        REAL,
    operating_margin    REAL,
    roic                REAL,
    roe                 REAL,
    debt                REAL,
    cash                REAL,
    shares_outstanding  REAL,
    PRIMARY KEY (ticker, fiscal_period)
);
CREATE INDEX IF NOT EXISTS idx_fund_available ON fundamentals_quarterly(ticker, available_on);

-- Analyst estimates & revisions, point-in-time.
CREATE TABLE IF NOT EXISTS estimates (
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    as_of_date          TEXT NOT NULL,
    available_on        TEXT NOT NULL,
    eps_estimate        REAL,
    revenue_estimate    REAL,
    analyst_count       INTEGER,
    revision_direction  TEXT,   -- 'up' | 'down' | 'flat'
    PRIMARY KEY (ticker, as_of_date)
);

-- Insider transactions (Form 4 style events).
CREATE TABLE IF NOT EXISTS insider_transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    transaction_date    TEXT NOT NULL,
    available_on        TEXT NOT NULL,
    insider_name        TEXT NOT NULL,
    insider_role        TEXT,
    transaction_type    TEXT NOT NULL,   -- 'buy' | 'sell'
    shares              REAL NOT NULL,
    price               REAL NOT NULL,
    value                REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_transactions(ticker, transaction_date);

-- Institutional ownership snapshots (13F-style, inherently reported with a lag).
CREATE TABLE IF NOT EXISTS institutional_ownership (
    ticker          TEXT NOT NULL REFERENCES companies(ticker),
    period_end      TEXT NOT NULL,
    available_on    TEXT NOT NULL,   -- typically 30-45 days after period_end
    pct_ownership   REAL NOT NULL,
    change_pct      REAL,            -- change vs prior period
    PRIMARY KEY (ticker, period_end)
);

-- Short interest snapshots (settlement-date reported, typically ~2x/month with a lag).
CREATE TABLE IF NOT EXISTS short_interest (
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    settlement_date     TEXT NOT NULL,
    available_on        TEXT NOT NULL,
    short_shares        REAL NOT NULL,
    days_to_cover       REAL,
    PRIMARY KEY (ticker, settlement_date)
);

-- Earnings events: actual vs estimate, guidance direction, and the market's reaction.
CREATE TABLE IF NOT EXISTS earnings_events (
    ticker              TEXT NOT NULL REFERENCES companies(ticker),
    report_date         TEXT NOT NULL,
    available_on        TEXT NOT NULL,
    eps_actual          REAL,
    eps_estimate        REAL,
    revenue_actual      REAL,
    revenue_estimate    REAL,
    guidance_change     TEXT,        -- 'raised' | 'maintained' | 'lowered'
    price_reaction_pct  REAL,        -- next-session % move
    PRIMARY KEY (ticker, report_date)
);

-- Catalyst / news-style events (contracts, M&A, buybacks, FDA, product launches).
CREATE TABLE IF NOT EXISTS catalyst_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL REFERENCES companies(ticker),
    event_date      TEXT NOT NULL,
    available_on    TEXT NOT NULL,
    event_type      TEXT NOT NULL,   -- 'contract'|'product_launch'|'regulatory'|'ma'|'buyback'|'guidance'
    description     TEXT,
    sentiment       TEXT             -- 'positive'|'negative'|'neutral'
);

-- Persisted backtest runs so results can be revisited from the dashboard.
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT NOT NULL,
    params_json     TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    metrics_json    TEXT NOT NULL,
    equity_curve_json TEXT NOT NULL
);

-- Accounts. Subscription is tracked directly on the user row since payment is
-- a placeholder gateway (no external processor/webhooks to reconcile against).
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    subscribed      INTEGER NOT NULL DEFAULT 0,
    plan            TEXT,
    subscribed_at   TEXT,
    last_active_at  TEXT
);

-- Audit trail for the admin dashboard. user_id is null for admin-initiated
-- actions (e.g. an admin toggling someone's subscription is logged against
-- the admin, not the affected user).
CREATE TABLE IF NOT EXISTS activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    event_type      TEXT NOT NULL,   -- signup | login | subscribe | unsubscribe | backtest_run | admin_login | admin_toggle_subscription
    detail          TEXT,
    created_at      TEXT NOT NULL
);
