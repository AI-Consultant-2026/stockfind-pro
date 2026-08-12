from . import (
    quality_value,
    momentum_breakout,
    earnings_momentum,
    fallen_angel,
    undervalued_quality,
    institutional_accumulation,
    insider_signal,
    short_squeeze,
    mean_reversion,
)

STRATEGY_MODULES = [
    quality_value,
    momentum_breakout,
    earnings_momentum,
    fallen_angel,
    undervalued_quality,
    institutional_accumulation,
    insider_signal,
    short_squeeze,
    mean_reversion,
]


def evaluate_all(bundle: dict) -> list[dict]:
    return [mod.evaluate(bundle) for mod in STRATEGY_MODULES]
