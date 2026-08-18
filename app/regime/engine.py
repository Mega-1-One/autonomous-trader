from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional

from app.scalper.features import ScalperFeatures

class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    BREAKOUT = "BREAKOUT"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    HIGH_RISK_EVENT = "HIGH_RISK_EVENT"
    UNCERTAIN = "UNCERTAIN"

@dataclass
class RegimeState:
    regime: MarketRegime
    confidence: float
    allow_trading: bool
    reasons: list[str]

class MarketRegimeEngine:
    """Classifies real-time market regime and determines system trade allowance."""

    def evaluate_regime(
        self,
        features: ScalperFeatures,
        event_lockout: bool = False
    ) -> RegimeState:
        reasons = []

        if event_lockout:
            return RegimeState(
                regime=MarketRegime.HIGH_RISK_EVENT,
                confidence=1.0,
                allow_trading=False,
                reasons=["Active high-impact macro event lockout"]
            )

        # Spread & Volatility Anomaly Check
        if features.spread_pips > 5.0:
            return RegimeState(
                regime=MarketRegime.UNCERTAIN,
                confidence=0.9,
                allow_trading=False,
                reasons=[f"Extreme spread detected ({features.spread_pips} pips)"]
            )

        # Breakout Detection
        if features.is_micro_breakout_high or features.is_micro_breakout_low:
            direction_str = "UP" if features.is_micro_breakout_high else "DOWN"
            return RegimeState(
                regime=MarketRegime.BREAKOUT,
                confidence=0.85,
                allow_trading=True,
                reasons=[f"Micro price breakout detected {direction_str}"]
            )

        # Momentum & Trend Detection
        if features.momentum_5s > 0.3 and features.bullish_tick_ratio >= 0.6:
            return RegimeState(
                regime=MarketRegime.TRENDING_UP,
                confidence=0.8,
                allow_trading=True,
                reasons=["Strong bullish momentum and tick imbalance"]
            )
        elif features.momentum_5s < -0.3 and features.bearish_tick_ratio >= 0.6:
            return RegimeState(
                regime=MarketRegime.TRENDING_DOWN,
                confidence=0.8,
                allow_trading=True,
                reasons=["Strong bearish momentum and tick imbalance"]
            )

        # Ranging vs Compression Detection
        if abs(features.momentum_5s) < 0.1 and 0.4 <= features.bullish_tick_ratio <= 0.6:
            return RegimeState(
                regime=MarketRegime.RANGING,
                confidence=0.75,
                allow_trading=True,
                reasons=["Low price momentum and balanced tick flow"]
            )

        return RegimeState(
            regime=MarketRegime.UNCERTAIN,
            confidence=0.5,
            allow_trading=True,
            reasons=["Mixed market features"]
        )
