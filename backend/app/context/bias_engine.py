from dataclasses import dataclass, asdict
from typing import List, Dict, Any

from app.context.timeframe_engine import Candle

@dataclass
class TopDownBiasResult:
    bias: str                     # "STRONG_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEARISH", "NO_TRADE"
    alignment_score: float        # -1.0 to +1.0
    tf_directions: Dict[str, str] # e.g. {"4h": "BUY", "1h": "BUY", "15m": "BUY", "5m": "BUY"}
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BiasEngine:
    """Evaluates Top-Down Market Structure alignment across 4h, 1h, 15m, and 5m timeframes."""

    def evaluate_bias(self, tf_candles: Dict[str, List[Candle]]) -> TopDownBiasResult:
        tf_dirs = {}
        scores = []
        reasons = []

        for tf in ["4h", "1h", "15m", "5m"]:
            candles = tf_candles.get(tf, [])
            if len(candles) < 10:
                tf_dirs[tf] = "NEUTRAL"
                scores.append(0.0)
                continue

            closes = [c.close for c in candles[-10:]]
            sma = sum(closes) / len(closes)
            curr = closes[-1]

            if curr > sma:
                tf_dirs[tf] = "BUY"
                scores.append(1.0)
                reasons.append(f"[{tf}] Bullish structure above SMA10")
            elif curr < sma:
                tf_dirs[tf] = "SELL"
                scores.append(-1.0)
                reasons.append(f"[{tf}] Bearish structure below SMA10")
            else:
                tf_dirs[tf] = "NEUTRAL"
                scores.append(0.0)

        avg_score = sum(scores) / len(scores) if scores else 0.0

        if avg_score >= 0.75:
            bias = "STRONG_BULLISH"
        elif avg_score >= 0.25:
            bias = "BULLISH"
        elif avg_score <= -0.75:
            bias = "STRONG_BEARISH"
        elif avg_score <= -0.25:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return TopDownBiasResult(
            bias=bias,
            alignment_score=round(avg_score, 2),
            tf_directions=tf_dirs,
            reasons=reasons
        )
