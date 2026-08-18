from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class AdaptiveExitV2Levels:
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance_pips: float
    target_distance_pips: float
    rr_ratio: float
    cost_ratio_percent: float
    expected_holding_seconds: float
    minimum_viable_target_pips: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MinimumViableTargetEngine:
    """Calculates minimum target required for positive EV given fixed ECN transaction costs."""

    def calculate_minimum_target(
        self,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        total_cost_dollars: float = 0.50,
        volume: float = 0.05,
        target_cost_ratio_max: float = 0.20
    ) -> float:
        pip_unit = spec.pip_size
        cost_pips = total_cost_dollars / (100.0 * volume * pip_unit) if pip_unit > 0 else 1.0
        min_target_pips = round(cost_pips / target_cost_ratio_max, 1)
        return max(3.0, min_target_pips)

class AdaptiveExitEngineV2:
    """Adaptive Exit Engine v2 dynamically sizing SL/TP based on ATR, Market Structure, and Cost Ratio."""

    def __init__(self):
        self.min_target_engine = MinimumViableTargetEngine()

    def calculate_exit_levels(
        self,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        direction: str,
        regime: str = "TRENDING_UP",
        atr_multiple_target: float = 1.5,
        atr_multiple_stop: float = 1.0
    ) -> AdaptiveExitV2Levels:
        pip_unit = spec.pip_size
        entry = features.ask if direction == "BUY" else features.bid

        vol_pips = max(1.0, features.volatility_50t / pip_unit)
        stop_dist_pips = max(2.0, vol_pips * atr_multiple_stop)
        target_dist_pips = max(self.min_target_engine.calculate_minimum_target(features, spec), vol_pips * atr_multiple_target)

        # Structure-based adjustment
        if direction == "BUY":
            sl = round(entry - (stop_dist_pips * pip_unit), spec.digits)
            tp = round(entry + (target_dist_pips * pip_unit), spec.digits)
        else:
            sl = round(entry + (stop_dist_pips * pip_unit), spec.digits)
            tp = round(entry - (target_dist_pips * pip_unit), spec.digits)

        total_cost_pips = features.spread_pips + 0.7 + 0.1
        cost_ratio = round((total_cost_pips / max(0.1, target_dist_pips)) * 100.0, 1)
        rr_ratio = round(target_dist_pips / max(0.1, stop_dist_pips), 2)
        holding_sec = 60.0 if regime == "TRENDING_UP" else 30.0

        return AdaptiveExitV2Levels(
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            stop_distance_pips=round(stop_dist_pips, 1),
            target_distance_pips=round(target_dist_pips, 1),
            rr_ratio=rr_ratio,
            cost_ratio_percent=cost_ratio,
            expected_holding_seconds=holding_sec,
            minimum_viable_target_pips=round(total_cost_pips * 5.0, 1)
        )
