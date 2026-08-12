from __future__ import annotations

import json
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask import session as flask_session

from . import scan_service
from .auth import subscription_required
from .util import to_jsonable
from ..backtest.engine import run_backtest
from ..db.database import log_activity, session
from ..engines.sector_rotation import compute_sector_rotation
from ..engines.strategies import STRATEGY_MODULES

api = Blueprint("api", __name__, url_prefix="/api")

STRATEGY_META = [
    {"strategy_id": "quality_value", "label": "Great Company at a Good Price", "badge": "🟢 VALUE + QUALITY",
     "modes": ["investor"], "short": "Quality",
     "description": "Growing, high-ROIC, well-financed businesses trading below an estimated fair value."},
    {"strategy_id": "momentum_breakout", "label": "Momentum Breakout Finder", "badge": "🔥 BREAKOUT",
     "modes": ["swing"], "short": "Breakout",
     "description": "Confirmed uptrends with volume evidence of real institutional demand, not just a price pop."},
    {"strategy_id": "earnings_momentum", "label": "Earnings Momentum", "badge": "🚀 EARNINGS",
     "modes": ["swing"], "short": "Earnings",
     "description": "Beats on EPS & revenue, raised guidance, a positive market reaction, and rising estimates — all agreeing."},
    {"strategy_id": "fallen_angel", "label": "Fallen Angel", "badge": "🟠 RECOVERY",
     "modes": ["investor"], "short": "Fallen Angel",
     "description": "Down sharply but fundamentals still healthy — with an explicit check for value-trap red flags."},
    {"strategy_id": "undervalued_quality", "label": "Undervalued Quality", "badge": "⭐ HIGH-CONVICTION",
     "modes": ["investor"], "short": "Undervalued",
     "description": "High quality, strong growth, strong balance sheet, and a cheap valuation, all at once."},
    {"strategy_id": "institutional_accumulation", "label": "Institutional Accumulation", "badge": "🏦 ACCUMULATION",
     "modes": ["investor", "swing"], "short": "Accumulation",
     "description": "Signs of steady institutional buying — rising reported ownership, volume and trend together."},
    {"strategy_id": "insider_signal", "label": "Insider Signal", "badge": "🟢 INSIDER BUYING",
     "modes": ["investor"], "short": "Insider",
     "description": "Multiple insiders buying in the same window — the strongest version of this signal."},
    {"strategy_id": "short_squeeze", "label": "Short Squeeze Watch", "badge": "🔥 SQUEEZE WATCH",
     "modes": ["active"], "short": "Squeeze",
     "description": "High short interest with rising price and volume. A positioning setup, not a quality signal."},
    {"strategy_id": "mean_reversion", "label": "Mean Reversion", "badge": "🟠 OVERSOLD",
     "modes": ["swing"], "short": "Reversion",
     "description": "Oversold AND fundamentally healthy — deliberately distinct from a stock that is just oversold."},
]

MODES = [
    {"id": "all", "label": "All Opportunities"},
    {"id": "investor", "label": "🟢 Investor", "description": "Quality companies, undervalued companies, compounders."},
    {"id": "swing", "label": "🟠 Swing Trader", "description": "Breakouts, momentum, earnings reactions, oversold setups."},
    {"id": "active", "label": "🔴 Active Trader", "description": "Unusual volume, volatility expansion, short interest."},
]


def _parse_as_of() -> date:
    raw = request.args.get("as_of")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return scan_service.default_as_of()


@api.get("/health")
def health():
    return jsonify({"status": "ok", "latest_data_date": scan_service.default_as_of().isoformat()})


@api.get("/strategies")
def strategies():
    return jsonify({"strategies": STRATEGY_META, "modes": MODES})


@api.get("/universe")
@subscription_required
def universe():
    return jsonify({"companies": to_jsonable(scan_service.provider.get_universe())})


@api.get("/sectors")
@subscription_required
def sectors():
    as_of = _parse_as_of()
    rows = scan_service.get_sector_rotation(as_of)
    return jsonify({"as_of": as_of.isoformat(), "sectors": to_jsonable(rows)})


@api.get("/scan")
@subscription_required
def scan():
    as_of = _parse_as_of()
    mode = request.args.get("mode", "all")
    strategy_id = request.args.get("strategy")
    sector = request.args.get("sector")
    qualifying_only = request.args.get("qualifying_only", "true").lower() != "false"
    limit = int(request.args.get("limit", 100))

    results = scan_service.get_full_scan(as_of)

    def matches(opp: dict) -> bool:
        if sector and opp["sector"] != sector:
            return False
        if strategy_id:
            ids = {q["strategy_id"] for q in opp["qualifying_strategies"]}
            if strategy_id not in ids:
                return False
        elif mode != "all":
            if qualifying_only:
                if not any(mode in q["modes"] for q in opp["qualifying_strategies"]):
                    return False
            else:
                if not any(mode in r["modes"] for r in opp["all_strategies"]):
                    return False
        elif qualifying_only and not opp["qualifying_strategies"]:
            return False
        return True

    filtered = [o for o in results if matches(o)]
    counts = {
        "high_conviction": sum(1 for o in results if o["overall_signal"]["tier"] == "green"),
        "watch": sum(1 for o in results if o["overall_signal"]["tier"] == "amber"),
        "risk_warning": sum(1 for o in results if o["overall_signal"]["tier"] == "red"),
        "total_scanned": len(results),
    }
    return jsonify({
        "as_of": as_of.isoformat(),
        "count": len(filtered),
        "counts": counts,
        "results": to_jsonable(filtered[:limit]),
    })


@api.get("/radar")
@subscription_required
def radar():
    as_of = _parse_as_of()
    results = scan_service.get_full_scan(as_of)

    top_opportunity = results[0] if results else None
    signal_feed = []
    for opp in results:
        for q in opp["qualifying_strategies"]:
            signal_feed.append({
                "ticker": opp["ticker"], "name": opp["name"], "strategy_id": q["strategy_id"],
                "label": q["label"], "badge": q["badge"], "opportunity_score": q["opportunity_score"],
                "headline": q["headline"],
            })
    signal_feed.sort(key=lambda r: r["opportunity_score"], reverse=True)

    counts = {
        "high_conviction": sum(1 for o in results if o["overall_signal"]["tier"] == "green"),
        "watch": sum(1 for o in results if o["overall_signal"]["tier"] == "amber"),
        "risk_warning": sum(1 for o in results if o["overall_signal"]["tier"] == "red"),
    }
    return jsonify({
        "as_of": as_of.isoformat(),
        "counts": counts,
        "top_opportunity": to_jsonable(top_opportunity),
        "signal_feed": to_jsonable(signal_feed[:40]),
    })


@api.get("/stock/<ticker>")
@subscription_required
def stock_detail(ticker: str):
    as_of = _parse_as_of()
    detail = scan_service.get_stock_detail(ticker.upper(), as_of)
    if not detail:
        return jsonify({"error": f"Unknown ticker or insufficient data: {ticker}"}), 404
    return jsonify(to_jsonable(detail))


@api.post("/backtest")
@subscription_required
def backtest():
    body = request.get_json(force=True) or {}
    try:
        start_date = date.fromisoformat(body.get("start_date", "2016-06-01"))
        end_date = date.fromisoformat(body.get("end_date", scan_service.default_as_of().isoformat()))
    except ValueError:
        return jsonify({"error": "start_date/end_date must be ISO dates (YYYY-MM-DD)"}), 400

    strategy_id = body.get("strategy_id")
    rules = body.get("rules")
    top_n = int(body.get("top_n", 12))
    sector_filter = body.get("sector")

    if not strategy_id and not rules:
        rules = {"min_roic": 0.15, "min_eps_growth": 0.10, "require_above_200ma": True,
                  "min_momentum_score": 60, "min_volume_ratio": 1.0}

    result = run_backtest(scan_service.provider, start_date, end_date, top_n=top_n,
                           strategy_id=strategy_id, rules=rules, sector_filter=sector_filter)
    if "error" in result:
        return jsonify(result), 400

    with session() as conn:
        cur = conn.execute(
            "INSERT INTO backtest_runs (strategy_name, params_json, start_date, end_date, created_at, metrics_json, equity_curve_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (strategy_id or "custom_rules", json.dumps(to_jsonable({"strategy_id": strategy_id, "rules": rules, "top_n": top_n, "sector": sector_filter})),
             start_date.isoformat(), end_date.isoformat(), datetime.utcnow().isoformat(),
             json.dumps(to_jsonable(result["metrics"])),
             json.dumps(to_jsonable({"equity_curve": result["equity_curve"], "benchmark_curve": result["benchmark_curve"]}))),
        )
        run_id = cur.lastrowid

    log_activity(flask_session.get("user_id"), "backtest_run", strategy_id or "custom_rules")
    result["id"] = run_id
    return jsonify(to_jsonable(result))


@api.get("/backtest")
@subscription_required
def backtest_list():
    with session() as conn:
        rows = conn.execute(
            "SELECT id, strategy_name, params_json, start_date, end_date, created_at, metrics_json FROM backtest_runs ORDER BY id DESC LIMIT 25"
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "strategy_name": r["strategy_name"], "params": json.loads(r["params_json"]),
            "start_date": r["start_date"], "end_date": r["end_date"], "created_at": r["created_at"],
            "metrics": json.loads(r["metrics_json"]),
        })
    return jsonify({"runs": out})


@api.get("/backtest/<int:run_id>")
@subscription_required
def backtest_get(run_id: int):
    with session() as conn:
        row = conn.execute("SELECT * FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    curve = json.loads(row["equity_curve_json"])
    return jsonify({
        "id": row["id"], "strategy_name": row["strategy_name"], "params": json.loads(row["params_json"]),
        "start_date": row["start_date"], "end_date": row["end_date"], "created_at": row["created_at"],
        "metrics": json.loads(row["metrics_json"]),
        "equity_curve": curve["equity_curve"], "benchmark_curve": curve["benchmark_curve"],
    })
