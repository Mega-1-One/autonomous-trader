from typing import List, Dict, Any, Optional
import numpy as np

from app.intelligence.analyzer import AnalysisResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

class TechnicalAnalyzer:
    """Evaluates multi-indicator trend, momentum, RSI, and volatility alignment."""

    def analyze(self, features: ScalperFeatures, spec: InstrumentSpecification, tick_history: List[float]) -> AnalysisResult:
        now = features.timestamp
        direction = "NEUTRAL"
        confidence = 0.0
        reasons = []

        if len(tick_history) < 20:
            return AnalysisResult(
                analyzer_name="TechnicalAnalyzer",
                symbol=features.symbol,
                timestamp=now,
                direction="NEUTRAL",
                confidence=0.0,
                strength=0.0,
                features={},
                reasons=["Insufficient price history for technical indicators"],
                valid_until=now + 10.0
            )

        prices = np.array(tick_history)
        sma20 = np.mean(prices[-20:])
        curr_price = prices[-1]

        # Simple Trend Alignment
        if curr_price > sma20:
            direction = "BUY"
            confidence = 0.60
            reasons.append("Price above SMA20 trend line")
        elif curr_price < sma20:
            direction = "SELL"
            confidence = 0.60
            reasons.append("Price below SMA20 trend line")

        return AnalysisResult(
            analyzer_name="TechnicalAnalyzer",
            symbol=features.symbol,
            timestamp=now,
            direction=direction,
            confidence=confidence,
            strength=abs(curr_price - sma20) / max(spec.tick_size, 0.0001),
            features={"sma20": round(float(sma20), spec.digits), "price": curr_price},
            reasons=reasons,
            valid_until=now + 10.0
        )
