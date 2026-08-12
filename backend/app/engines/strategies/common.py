"""Shared helpers for the ten opportunity-strategy modules."""
from __future__ import annotations


def checklist_result(strategy_id: str, label: str, badge: str, mode: list[str],
                      checklist: list[tuple[str, bool]], opportunity_score: float,
                      qualify_threshold: int = 0, headline: str = "",
                      gate_indices: tuple[int, ...] = ()) -> dict:
    """`gate_indices` names checklist positions (0-based) that are hallmark
    conditions for this strategy — e.g. "actually fell a lot" for Fallen
    Angel, or "short interest is actually high" for Short Squeeze. A strategy
    only qualifies if every gate is true AND at least `qualify_threshold`
    checklist items overall are true, so a stock can't earn a strategy's
    label purely on secondary/supporting conditions."""
    signals_met = sum(1 for _, ok in checklist if ok)
    signals_total = len(checklist)
    gates_ok = all(checklist[i][1] for i in gate_indices) if gate_indices else True
    return {
        "strategy_id": strategy_id,
        "label": label,
        "badge": badge,
        "modes": mode,
        "opportunity_score": round(opportunity_score, 1),
        "signals_met": signals_met,
        "signals_total": signals_total,
        "checklist": [{"label": lbl, "met": bool(ok)} for lbl, ok in checklist],
        "qualifies": gates_ok and signals_met >= qualify_threshold,
        "headline": headline,
    }
