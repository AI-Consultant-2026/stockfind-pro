# StockFind Pro — Multi-Strategy Opportunity Scanner (MVP)

A working implementation of the StockFind Pro spec: a market scanner built around
**opportunity detection** rather than a single "good stock" score. It runs ten
independent strategy engines, a signal-convergence calculator, a deterministic
quant scoring layer with a template-based "AI analyst" explainer on top, and a
point-in-time backtesting engine — end to end, runnable locally right now.

Because no live market-data API keys were available for this build, the app ships
with a **simulated but internally consistent** dataset (10.7 years of daily OHLCV,
quarterly fundamentals, estimates, insider transactions, institutional ownership,
short interest, earnings events and catalysts for 63 fictional companies) generated
by `backend/app/seed.py`. Every engine, strategy, and the backtester is written
against a `DataProvider` interface, so swapping in Finnhub / Alpha Vantage / SEC
EDGAR later is a matter of implementing one adapter class — see
`backend/app/data_providers/live_stubs.py`.

## Quick start

Requires **Python 3.10+** (numpy 2.1.1 won't install on older versions).

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed            # generates stockfind.db (~10s)
python -m app.main            # serves API + dashboard on http://localhost:8000
```

Open `http://localhost:8000`. That's the whole setup — no external services, no
API keys, no database server (SQLite file, generated in place).

Re-run `python -m app.seed` any time to regenerate the simulated universe with a
fresh (seeded, so reproducible) random draw. Note `app.seed` resets the whole
database, including any accounts you've created — re-sign-up after reseeding.

### Accounts & subscription

The dashboard sits behind a sign-up/log-in gate, and behind that, a "subscribe"
paywall (`$19/mo` or `$179/yr` — placeholder plans, not tied to a real price
list). Both the frontend gate and the API itself enforce this: every data
endpoint (`/api/scan`, `/api/radar`, `/api/stock/*`, `/api/sectors`,
`/api/backtest*`, `/api/universe`) requires a subscribed session, returning
`401` if logged out or `402` if logged in but not subscribed.

Payment is a **placeholder gateway** — there is no Stripe/PayPal/etc.
integration. Clicking "Subscribe" just flips `subscribed=1` on your account row
in SQLite; no card is ever collected and no money moves. Wiring in a real
processor means replacing `POST /api/auth/subscribe` in
`backend/app/api/auth.py` with a real Checkout session and a webhook that
flips the same flag once payment actually clears.

### Admin dashboard

`/admin` is a separate, staff-only page — a distinct login from regular user
accounts, credentials set via env vars:

```bash
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=some-strong-password
```

If unset, it defaults to `admin@stockfindpro.local` / `changeme` — **set both
env vars before deploying anywhere public.** It shows account stats (total
users, subscribed/free split, signups today/7d, backtests run), a searchable
user table with a Grant/Revoke button (comps or revokes a subscription without
touching payment), and a real activity log (`activity_log` table) recording
every signup, login, subscribe/unsubscribe, backtest run, and admin action —
all API endpoints are under `/api/admin/*` and gated by their own
`admin_required` session check, independent of the regular user auth.

## What's actually implemented

Every numbered section of the source spec has a corresponding piece of code:

| Spec section | Implementation |
|---|---|
| §1 Market Scanner (all the raw data fields) | `backend/app/data_gen.py` + `db/schema.sql` |
| §2 Multiple opportunity scores, not one | `engines/fundamental.py`, `technical.py`, `momentum.py`, `risk.py`, `event.py` → Quality / Growth / Momentum / Value / Cash Flow / Catalyst / Risk |
| §3–§12 The ten strategies | `engines/strategies/*.py` + `engines/sector_rotation.py` |
| §13–§14 Main screen / Opportunity Radar | `frontend/` dashboard, `/api/scan`, `/api/radar` |
| §15 Per-opportunity "setup" | `engines/ai_analyst.py` (setup quality, why-it-appeared) |
| §16 Signal Convergence | `engines/convergence.py` |
| §17 Why? / Why Not? | `engines/ai_analyst.py` |
| §18 Backtesting | `backend/app/backtest/engine.py`, `/api/backtest`, Backtesting tab |
| §19 AI explains, doesn't score | Every score is a plain deterministic formula (`engines/scoring_utils.py`); `ai_analyst.py` only writes prose about numbers that already exist |
| §20 Architecture diagram | Mirrored directly in the module layout below |
| §21 Point-in-time data / primary sources | `available_on` timestamps throughout the schema; `data_providers/live_stubs.py` documents the EDGAR/Finnhub/Alpha Vantage wiring |
| §22 Three modes | Investor / Swing Trader / Active Trader mode switch, tagged per-strategy |
| §23 Two rankings, no "buy" language | `fundamental_opportunity` / `trading_opportunity` / `overall_signal` in `engines/ranking.py` — labels are always "meets criteria, worth investigating," never a buy call |

## Architecture

```
        DATA SOURCES (SimulatedProvider today; Finnhub/AlphaVantage/EDGAR stubs)
                         |
                data_providers/base.py  (DataProvider interface, as_of-filtered)
                         |
        +----------------+----------------+
        |                |                |
   engines/          engines/         engines/
  fundamental.py    technical.py      event.py
   (Quality,          (Momentum          (Catalyst score,
    Growth,            score inputs,      insider/inst/short
    Value,             RSI/MACD/ATR/      interest, earnings
    Cash Flow)         Bollinger/RS)      surprises)
        |                |                |
        +----------------+----------------+
                         |
              engines/factor_engine.py   (score_stock: one ScoreBundle per ticker/date)
                         |
              engines/strategies/*.py    (10 opportunity strategies)
                         |
              engines/convergence.py     (Signal Convergence %)
                         |
              engines/ranking.py         (Fundamental/Trading Opportunity, Overall Signal)
                         |
              engines/ai_analyst.py      (Why / Why Not / narrative — template over real numbers)
                         |
        +----------------+----------------+
        |                                 |
   api/routes.py (Flask)          backtest/engine.py
   /scan /radar /stock /sectors    (point-in-time monthly-rebalance
   /strategies /backtest           simulation; reuses factor_engine
        |                          so live scan and backtest share
   frontend/ (dashboard)           one code path — no separate,
                                   possibly-inconsistent backtest logic)
```

## Project layout

```
backend/
  app/
    db/schema.sql, database.py       — SQLite schema + connection helpers
    seed_universe.py                 — the 63-ticker fictional universe + archetypes
    data_gen.py, seed.py             — simulated market data generator
    data_providers/
      base.py                        — DataProvider interface (the abstraction boundary)
      simulated.py                   — reads the generated SQLite DB, point-in-time filtered
      live_stubs.py                  — documented, unimplemented Finnhub/AlphaVantage/EDGAR adapters
    engines/
      scoring_utils.py                — shared 0-100 normalization rubric
      technical.py, fundamental.py, event.py, momentum.py, risk.py
      factor_engine.py                — orchestrates one full ScoreBundle
      strategies/                     — the 10 opportunity strategies
      sector_rotation.py, convergence.py, ranking.py, ai_analyst.py
    backtest/engine.py                — point-in-time backtesting engine
    api/routes.py, scan_service.py, util.py
    main.py                           — Flask app entrypoint
  requirements.txt
frontend/
  index.html, styles.css, app.js      — vanilla JS dashboard (no build step)
README.md
```

## API reference

All endpoints are under `/api`. `as_of=YYYY-MM-DD` is accepted on the read
endpoints to replay any historical date using only data that would have been
available then (defaults to the latest date in the dataset).

- `GET /api/scan?mode=&strategy=&sector=&qualifying_only=&limit=` — ranked opportunity list
- `GET /api/radar` — Opportunity Radar: tier counts + top signal feed
- `GET /api/stock/<ticker>` — full detail for one stock (scores, checklist, Why/Why-Not, raw metrics)
- `GET /api/sectors` — sector rotation ranking
- `GET /api/strategies` — strategy + mode metadata (drives the UI filter chips)
- `POST /api/backtest` — run a backtest (`strategy_id` OR `rules`, `start_date`, `end_date`, `top_n`, `sector`)
- `GET /api/backtest`, `GET /api/backtest/<id>` — persisted run history

## Backtesting methodology & bias notes

- Monthly-rebalance, equal-weight simulation. At each rebalance date the
  screen only sees data whose `available_on <= that date` — the exact same
  `score_stock()` code path the live scanner uses, so there is no separate
  (and potentially inconsistent) backtest-only scoring logic.
- Reports: total/annualized return, S&P 500 comparison, max drawdown, Sharpe,
  Sortino, win rate, average gain/loss, profit factor, number of trades, and
  average turnover per rebalance.
- **Known limitation (documented, not silently ignored):** the simulated
  universe is fixed — no company ever delists — so this MVP does not model
  survivorship bias. Pointed at real data, the fix is to source a genuine
  point-in-time index-constituent list per rebalance date, not apply today's
  constituent list retroactively. See the docstring in `backtest/engine.py`.

## Going live: wiring in real data

1. Implement `LiveProvider` in `data_providers/live_stubs.py` against Finnhub
   (quotes, financials, estimates, insiders, institutional ownership),
   Alpha Vantage (time series, technicals) and SEC EDGAR's Company Facts API
   (US fundamentals straight from filings).
2. Keep stamping every fact with when it actually became public
   (`available_on`), not "today" — that discipline is what keeps the
   backtester honest.
3. Cache fetched data into the same SQLite tables (or swap SQLite for
   Postgres — the schema is already normalized for that) on a schedule,
   rather than hitting rate-limited free-tier APIs on the request path.
4. Set `DATA_PROVIDER=live` plus the relevant API key env vars — nothing
   above the provider layer changes.

## Known simplifications (MVP scope)

- **Simulated data.** Tickers and company names are fictional. Prices/fundamentals
  are generated with a documented, seeded model (`data_gen.py`) tuned to produce
  realistic-looking valuation multiples and volatility — not real market history.
- **"AI Analyst" is a template, not an LLM call.** Every score is a deterministic
  formula; `ai_analyst.py` only writes prose about numbers that already exist,
  per the spec's explicit instruction that AI should explain, not score. Swapping
  in a real LLM call for nicer phrasing (without letting it touch the numbers) is
  a one-function change — see that module's docstring.
- **Fair value is a simple justified-multiple heuristic** (bounded 8×–45× trailing
  EPS, scaled by the Growth/Quality scores), not a DCF — documented as such in
  `fundamental.py` so nobody mistakes it for more than it is.
- **Payment is a placeholder gateway, not a real processor.** Accounts and
  sessions are real (email/password, hashed, server-enforced); the "Subscribe"
  button just flips a database flag. No card is ever collected.
- **"Add to Research List" doesn't persist** — it's still a UI affordance only,
  unrelated to the new accounts system.
- **No password reset flow.** Signup/login/logout only.
- Dashboard is dark-theme only (no light-mode toggle) for this pass.

## Design principle carried through the whole codebase

> The application should say: "This stock currently meets your selected opportunity
> criteria and deserves further investigation." Not "buy this stock."

Every label in the scoring and ranking engines (`WATCH SETUP`, `HIGH-CONVICTION
WATCH`, `RISK WARNING`, badges like `🟢 VALUE + QUALITY ALERT`) is worded that way
on purpose, and the dashboard never renders anything as investment advice.
