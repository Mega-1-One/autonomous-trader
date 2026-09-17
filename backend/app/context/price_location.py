from dataclasses import dataclass
from typing import List

from app.context.timeframe_engine import Candle

@dataclass
class PriceLocationResult:
    location: str                    # "PREMIUM", "DISCOUNT", "EQUILIBRIUM"
    percentile: float                # 0.0 (low) to 1.0 (high)
    swing_high: float
    swing_low: float
    equilibrium_price: float

class PriceLocationEngine:
    """Evaluates whether current price is in Premium, Discount, or Equilibrium within HTF dealing range."""

    def evaluate_location(self, candles: List[Candle], current_price: float) -> PriceLocationResult:
        if len(candles) < 20:
            return PriceLocationResult(
                location="EQUILIBRIUM", percentile=0.5,
                swing_high=current_price * 1.01, swing_low=current_price * 0.99,
                equilibrium_price=current_price
            )

        highs = [c.high for c in candles[-20:]]
        lows = [c.low for c in candles[-20:]]

        swing_high = max(highs)
        swing_low = min(lows)
        rng = max(1e-5, swing_high - swing_low)
        percentile = min(1.0, max(0.0, (current_price - swing_low) / rng))

        if percentile >= 0.65:
            loc = "PREMIUM"
        elif percentile <= 0.35:
            loc = "DISCOUNT"
        else:
            loc = "EQUILIBRIUM"

        return PriceLocationResult(
            location=loc,
            percentile=round(percentile, 2),
            swing_high=round(swing_high, 5),
            swing_low=round(swing_low, 5),
            equilibrium_price=round((swing_high + swing_low) / 2.0, 5)
        )
