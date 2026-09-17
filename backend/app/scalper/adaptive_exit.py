from dataclasses import dataclass

from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class AdaptiveExitLevels:
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance_pips: float
    target_distance_pips: float
    expected_holding_seconds: float

class AdaptiveExitEngine:
    """Calculates volatility-adaptive and structure-based SL, TP, and holding target durations."""

    def calculate_levels(
        self,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        direction: str,
        rr_ratio: float = 1.5
    ) -> AdaptiveExitLevels:
        pip_unit = spec.pip_size
        entry = features.ask if direction == "BUY" else features.bid

        # Structure / Volatility distance calculation
        vol_pips = max(1.0, features.volatility_50t / pip_unit)
        stop_dist_pips = max(3.0, vol_pips * 1.5)
        target_dist_pips = round(stop_dist_pips * rr_ratio, 1)

        if direction == "BUY":
            sl = round(entry - (stop_dist_pips * pip_unit), spec.digits)
            tp = round(entry + (target_dist_pips * pip_unit), spec.digits)
        else:
            sl = round(entry + (stop_dist_pips * pip_unit), spec.digits)
            tp = round(entry - (target_dist_pips * pip_unit), spec.digits)

        holding_sec = 30.0 if vol_pips <= 2.0 else 15.0

        return AdaptiveExitLevels(
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            stop_distance_pips=round(stop_dist_pips, 1),
            target_distance_pips=target_dist_pips,
            expected_holding_seconds=holding_sec
        )
