from typing import List
import numpy as np

from app.intelligence.analyzer import AnalysisResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

class MarketStructureAnalyzer:
    """Evaluates swing highs, swing lows, BOS (Break of Structure), and CHoCH."""

    def analyze(self, features: ScalperFeatures, spec: InstrumentSpecification, tick_history: List[float]) -> AnalysisResult:
        now = features.timestamp
        direction = "NEUTRAL"
        confidence = 0.0
        reasons = []

        if len(tick_history) < 30:
            return AnalysisResult(
                analyzer_name="MarketStructureAnalyzer",
                symbol=features.symbol,
                timestamp=now,
                direction="NEUTRAL",
                confidence=0.0,
                strength=0.0,
                features={},
                reasons=["Insufficient history for structure analysis"],
                valid_until=now + 10.0
            )

        prices = np.array(tick_history)
        recent_high = np.max(prices[-30:-5])
        recent_low = np.min(prices[-30:-5])
        curr_price = prices[-1]

        if curr_price > recent_high:
            direction = "BUY"
            confidence = 0.80
            reasons.append(f"BOS Bullish: Broken recent swing high ({recent_high})")
        elif curr_price < recent_low:
            direction = "SELL"
            confidence = 0.80
            reasons.append(f"BOS Bearish: Broken recent swing low ({recent_low})")

        return AnalysisResult(
            analyzer_name="MarketStructureAnalyzer",
            symbol=features.symbol,
            timestamp=now,
            direction=direction,
            confidence=confidence,
            strength=0.8,
            features={"swing_high": recent_high, "swing_low": recent_low},
            reasons=reasons,
            valid_until=now + 10.0
        )
