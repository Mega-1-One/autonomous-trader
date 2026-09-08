from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import numpy as np

@dataclass
class DisplacementCandle:
    index: int
    timestamp: str
    direction: str  # "BULLISH" or "BEARISH"
    body_size: float
    atr: float
    body_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class DisplacementEngine:
    """Quantitative Displacement Engine evaluating candle body size against ATR multiple."""

    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        min_body_percentage: float = 60.0
    ):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_body_percentage = min_body_percentage

    def calculate_atr(self, candles: List[Dict[str, Any]]) -> List[float]:
        """Calculates Average True Range (ATR) over candle series."""
        if len(candles) < 2:
            return [0.0] * len(candles)

        tr_list = [candles[0]["high"] - candles[0]["low"]]
        for i in range(1, len(candles)):
            c = candles[i]
            prev_close = candles[i - 1]["close"]
            tr = max(
                c["high"] - c["low"],
                abs(c["high"] - prev_close),
                abs(c["low"] - prev_close)
            )
            tr_list.append(tr)

        atr = []
        for i in range(len(candles)):
            if i < self.atr_period:
                atr.append(float(np.mean(tr_list[: i + 1])))
            else:
                val = float(np.mean(tr_list[i - self.atr_period + 1 : i + 1]))
                atr.append(val)
        return atr

    def detect_displacement(self, candles: List[Dict[str, Any]]) -> List[DisplacementCandle]:
        """Identifies candles meeting quantitative displacement criteria."""
        displacements: List[DisplacementCandle] = []
        if len(candles) < self.atr_period:
            return displacements

        atr_series = self.calculate_atr(candles)

        for i, c in enumerate(candles):
            total_range = c["high"] - c["low"]
            if total_range <= 0:
                continue

            body_size = abs(c["close"] - c["open"])
            body_percent = (body_size / total_range) * 100.0
            atr_val = atr_series[i]

            if body_size >= (atr_val * self.atr_multiplier) and body_percent >= self.min_body_percentage:
                direction = "BULLISH" if c["close"] > c["open"] else "BEARISH"
                displacements.append(
                    DisplacementCandle(
                        index=i,
                        timestamp=c["timestamp"],
                        direction=direction,
                        body_size=body_size,
                        atr=atr_val,
                        body_percentage=body_percent
                    )
                )

        return displacements
