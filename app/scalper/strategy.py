import hashlib
import time
from typing import List, Optional

from app.scalper.features import ScalperFeatures
from app.scalper.signal import ScalpSignal
from app.scalper.instrument import InstrumentSpecification

class ScalpStrategyEngine:
    """Normalized Momentum & Micro-Breakout Scalping Strategy Engine."""

    def __init__(
        self,
        max_allowed_spread: float = 3.0,
        min_tick_velocity: float = 1.0,
        min_imbalance_edge: float = 0.05,
        min_norm_momentum: float = 0.8,
        rr_ratio: float = 1.5,
        sl_pips: float = 3.0
    ):
        self.max_allowed_spread = max_allowed_spread
        self.min_tick_velocity = min_tick_velocity
        self.min_imbalance_edge = min_imbalance_edge
        self.min_norm_momentum = min_norm_momentum
        self.rr_ratio = rr_ratio
        self.sl_pips = sl_pips

    def generate_signal(
        self,
        features: ScalperFeatures,
        spec: Optional[InstrumentSpecification] = None,
        point_size: float = 0.001,
        digits: int = 3
    ) -> ScalpSignal:
        reasons: List[str] = []
        now = features.timestamp

        if spec is None:
            spec = InstrumentSpecification.get_default_spec(features.symbol)

        pip_unit = spec.pip_size

        # 1. Spread Check
        if features.spread_pips > self.max_allowed_spread:
            reasons.append(f"Spread too high ({features.spread_pips} > {self.max_allowed_spread})")

        # 2. Velocity Check
        if features.tick_velocity_5s < self.min_tick_velocity:
            reasons.append(f"Tick velocity too low ({features.tick_velocity_5s} < {self.min_tick_velocity})")

        # Evaluate BUY Conditions (Normalized Momentum + Imbalance Edge)
        is_buy = (
            features.spread_pips <= self.max_allowed_spread and
            features.tick_velocity_5s >= self.min_tick_velocity and
            features.bullish_tick_ratio >= (0.50 + self.min_imbalance_edge) and
            features.normalized_momentum >= self.min_norm_momentum and
            features.price_acceleration >= 0
        )

        # Evaluate SELL Conditions (Normalized Momentum + Imbalance Edge)
        is_sell = (
            features.spread_pips <= self.max_allowed_spread and
            features.tick_velocity_5s >= self.min_tick_velocity and
            features.bearish_tick_ratio >= (0.50 + self.min_imbalance_edge) and
            features.normalized_momentum <= -self.min_norm_momentum and
            features.price_acceleration <= 0
        )

        direction = "NONE"
        status = "REJECTED"
        confidence = 0.0

        if is_buy:
            direction = "BUY"
            status = "APPROVED"
            confidence = round(min(1.0, 0.5 + features.bullish_tick_ratio * 0.5), 2)
            reasons.extend(["bullish_tick_imbalance", "positive_normalized_momentum", "micro_acceleration"])
            entry = features.ask
            sl = round(entry - (self.sl_pips * pip_unit), spec.digits)
            tp = round(entry + (self.sl_pips * self.rr_ratio * pip_unit), spec.digits)
        elif is_sell:
            direction = "SELL"
            status = "APPROVED"
            confidence = round(min(1.0, 0.5 + features.bearish_tick_ratio * 0.5), 2)
            reasons.extend(["bearish_tick_imbalance", "negative_normalized_momentum", "micro_deceleration"])
            entry = features.bid
            sl = round(entry + (self.sl_pips * pip_unit), spec.digits)
            tp = round(entry - (self.sl_pips * self.rr_ratio * pip_unit), spec.digits)
        else:
            entry = features.bid
            sl = entry
            tp = entry

        # Deterministic Signal ID Fingerprint
        time_bucket = int(now)
        hash_input = f"{features.symbol}_{direction}_{time_bucket}".encode("utf-8")
        signal_id = f"SIG_{hashlib.md5(hash_input).hexdigest()[:12].upper()}"

        return ScalpSignal(
            signal_id=signal_id,
            timestamp=now,
            symbol=features.symbol,
            direction=direction,
            status=status,
            confidence_score=confidence,
            entry_reference=entry,
            stop_reference=sl,
            target_reference=tp,
            spread=features.spread_pips,
            momentum=features.momentum_5s,
            velocity=features.tick_velocity_5s,
            volatility=features.volatility_50t,
            reasons=reasons,
            expiry_time=now + 10.0
        )
