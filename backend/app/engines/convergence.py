"""
Signal Convergence — the central concept of the platform (source doc §16).
One strong metric isn't interesting; several independent signals lining up
is. This evaluates a fixed set of ten independent yes/no signals spanning
fundamentals, valuation, momentum, earnings, volume, sector, cash flow,
catalysts, insider activity and risk, and reports how many agree.

This deliberately does NOT guarantee a trade works — it only tells the
trader that several independent factors point the same direction.
"""
from __future__ import annotations


def compute_convergence(bundle: dict, sector_momentum: float | None = None) -> dict:
    s, e, t = bundle["scores"], bundle["event"], bundle["technical"]

    signals = [
        ("Strong fundamentals", s["quality"] >= 65),
        ("Strong valuation", s["value"] >= 60),
        ("Strong momentum", s["momentum"] >= 60),
        ("Positive earnings surprise", (e.get("eps_beat_pct") or -99) > 0),
        ("Increasing volume", (not t.get("insufficient_data")) and t["volume_ratio"] > 1.1),
        ("Strong sector", (sector_momentum if sector_momentum is not None else 50) >= 60),
        ("Cash flow strength", s["cash_flow"] >= 60),
        ("Active catalyst", s["catalyst"] >= 60),
        ("Insider activity positive", e.get("insider_cluster_buying", False) or
            e.get("insider_buy_value_180d", 0) > e.get("insider_sell_value_180d", 0)),
        ("Risk contained", s["risk"] >= 55),
    ]
    positive = sum(1 for _, ok in signals if ok)
    total = len(signals)
    return {
        "signals": [{"label": lbl, "positive": bool(ok)} for lbl, ok in signals],
        "positive_count": positive,
        "total": total,
        "convergence_pct": round(positive / total * 100, 0),
    }
