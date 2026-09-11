from typing import List, Dict, Any, Optional
import numpy as np

from app.intelligence.analyzer import AnalysisResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

class LiquidityAnalyzer:
    """Detects liquidity sweeps, equal highs/lows, and post-sweep rejection."""

    def analyze(self, features: ScalperFeatures, spec: InstrumentSpecification, tick_history: List[float]) -> AnalysisResult:
        now = features.timestamp
        direction = "NEUTRAL"
        confidence = 0.0
        reasons = []

        if len(tick_history) < 20:
            return AnalysisResult(
                analyzer_name="LiquidityAnalyzer",
                symbol=features.symbol,
                timestamp=now,
                direction="NEUTRAL",
                confidence=0.0,
                strength=0.0,
                features={},
                reasons=["Insufficient data for liquidity sweep detection"],
                valid_until=now + 10.0
            )

        prices = np.array(tick_history)
        recent_high = np.max(prices[-20:-2])
        recent_low = np.min(prices[-20:-2])
        curr_price = prices[-1]

        # Liquidity Sweep Reversal Check
        if prices[-2] > recent_high and curr_price < recent_high:
            direction = "SELL"
            confidence = 0.75
            reasons.append("Buy-side liquidity sweep & rejection detected")
        elif prices[-2] < recent_low and curr_price > recent_low:
            direction = "BUY"
            confidence = 0.75
            reasons.append("Sell-side liquidity sweep & rejection detected")

        return AnalysisResult(
            analyzer_name="LiquidityAnalyzer",
            symbol=features.symbol,
            timestamp=now,
            direction=direction,
            confidence=confidence,
            strength=0.75 if direction != "NEUTRAL" else 0.0,
            features={"recent_high": recent_high, "recent_low": recent_low},
            reasons=reasons,
            valid_until=now + 10.0
        )
