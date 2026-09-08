from typing import Dict
from app.regime.engine import MarketRegime

class StrategySelector:
    """Dynamically assigns strategy weights based on detected market regime."""

    REGIME_WEIGHTS: Dict[MarketRegime, Dict[str, float]] = {
        MarketRegime.TRENDING_UP: {
            "MomentumScalper": 1.0,
            "BreakoutScalper": 0.8,
            "MeanReversionScalper": 0.0,
        },
        MarketRegime.TRENDING_DOWN: {
            "MomentumScalper": 1.0,
            "BreakoutScalper": 0.8,
            "MeanReversionScalper": 0.0,
        },
        MarketRegime.BREAKOUT: {
            "MomentumScalper": 0.7,
            "BreakoutScalper": 1.0,
            "MeanReversionScalper": 0.0,
        },
        MarketRegime.RANGING: {
            "MomentumScalper": 0.2,
            "BreakoutScalper": 0.2,
            "MeanReversionScalper": 1.0,
        },
        MarketRegime.VOLATILITY_EXPANSION: {
            "MomentumScalper": 0.9,
            "BreakoutScalper": 1.0,
            "MeanReversionScalper": 0.0,
        },
        MarketRegime.HIGH_RISK_EVENT: {
            "MomentumScalper": 0.0,
            "BreakoutScalper": 0.0,
            "MeanReversionScalper": 0.0,
        },
        MarketRegime.UNCERTAIN: {
            "MomentumScalper": 0.0,
            "BreakoutScalper": 0.0,
            "MeanReversionScalper": 0.0,
        },
    }

    def get_strategy_weight(self, regime: MarketRegime, strategy_name: str) -> float:
        weights = self.REGIME_WEIGHTS.get(regime, {})
        return weights.get(strategy_name, 0.0)
