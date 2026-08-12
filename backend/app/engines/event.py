"""
Event engine — earnings surprises, guidance, insider activity, institutional
ownership trend, short interest and catalyst headlines, rolled up into a
Catalyst score. Also surfaces the individual signals strategies need
(e.g. "multiple insiders buying", "guidance raised") without collapsing them.

Important distinction the source doc calls out explicitly: institutional
ownership and short-interest data are inherently reported with a lag. Every
value returned here carries the `as_of_period`/`available_on` it was actually
reported on, and the API/frontend must label it as such rather than implying
it is real-time.
"""
from __future__ import annotations

from .scoring_utils import band, weighted_avg, clip


def compute_event_signals(earnings: list[dict], insiders: list[dict], inst_ownership: list[dict],
                           short_interest: dict | None, catalysts: list[dict]) -> dict:
    latest_earnings = earnings[0] if earnings else None

    eps_beat = None
    revenue_beat = None
    guidance = None
    earnings_price_reaction = None
    if latest_earnings:
        if latest_earnings.get("eps_estimate"):
            eps_beat = (latest_earnings["eps_actual"] - latest_earnings["eps_estimate"]) / abs(latest_earnings["eps_estimate"])
        if latest_earnings.get("revenue_estimate"):
            revenue_beat = (latest_earnings["revenue_actual"] - latest_earnings["revenue_estimate"]) / abs(latest_earnings["revenue_estimate"])
        guidance = latest_earnings.get("guidance_change")
        earnings_price_reaction = latest_earnings.get("price_reaction_pct")

    # Insider signal
    buys = [t for t in insiders if t["transaction_type"] == "buy"]
    sells = [t for t in insiders if t["transaction_type"] == "sell"]
    buy_value = sum(t["value"] for t in buys)
    sell_value = sum(t["value"] for t in sells)
    distinct_buyers = len({t["insider_name"] for t in buys})
    cluster_buying = distinct_buyers >= 3
    net_insider_value = buy_value - sell_value

    # Institutional ownership trend (needs >=2 snapshots to compute a delta)
    inst_trend_pct = None
    inst_latest_pct = None
    inst_period = None
    if inst_ownership:
        inst_latest_pct = inst_ownership[-1]["pct_ownership"]
        inst_period = inst_ownership[-1]["period_end"]
        if len(inst_ownership) >= 2:
            inst_trend_pct = inst_ownership[-1]["pct_ownership"] - inst_ownership[-2]["pct_ownership"]

    # Catalyst headlines
    positive_catalysts = [c for c in catalysts if c["sentiment"] == "positive"]
    negative_catalysts = [c for c in catalysts if c["sentiment"] == "negative"]

    catalyst_score = weighted_avg([
        (band(eps_beat, -0.10, 0.15, default=50), 1.3),
        (band(revenue_beat, -0.08, 0.10, default=50), 1.0),
        (85 if guidance == "raised" else (50 if guidance == "maintained" else (15 if guidance == "lowered" else 50)), 1.1),
        (band(earnings_price_reaction, -8, 10, default=50), 0.9),
        (70 if cluster_buying else (60 if net_insider_value > 0 else (45 if net_insider_value < 0 else 50)), 0.7),
        (band(inst_trend_pct, -3, 3, default=50), 0.6),
        (clip(50 + len(positive_catalysts) * 12 - len(negative_catalysts) * 15), 0.6),
    ])

    return {
        "eps_beat_pct": round(eps_beat * 100, 2) if eps_beat is not None else None,
        "revenue_beat_pct": round(revenue_beat * 100, 2) if revenue_beat is not None else None,
        "guidance_change": guidance,
        "earnings_price_reaction_pct": earnings_price_reaction,
        "latest_earnings_date": latest_earnings["report_date"] if latest_earnings else None,
        "insider_buy_value_180d": buy_value,
        "insider_sell_value_180d": sell_value,
        "insider_distinct_buyers_180d": distinct_buyers,
        "insider_cluster_buying": cluster_buying,
        "institutional_ownership_pct": inst_latest_pct,
        "institutional_ownership_trend_pct": inst_trend_pct,
        "institutional_ownership_as_of": inst_period,
        "short_interest_pct_float": (short_interest["short_shares"] / short_interest.get("_float_shares", 1) * 100)
            if short_interest and short_interest.get("_float_shares") else None,
        "days_to_cover": short_interest["days_to_cover"] if short_interest else None,
        "positive_catalysts": [c["description"] for c in positive_catalysts],
        "negative_catalysts": [c["description"] for c in negative_catalysts],
        "catalyst_score": catalyst_score,
    }
