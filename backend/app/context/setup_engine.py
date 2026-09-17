from dataclasses import dataclass, asdict
from typing import Dict, Any, List

from app.context.bias_engine import TopDownBiasResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class ContextualSetup:
    setup_type: str                  # "TREND_CONTINUATION", "LIQUIDITY_SWEEP_REVERSAL", "BREAKOUT_RETEST", "NONE"
    direction: str                   # "BUY", "SELL", or "NONE"
    approved: bool
    top_down_bias: str
    alignment_score: float
    tick_timing_confirmed: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SetupEngine:
    """Combines Top-Down Bias with short-term Contextual Setup & Tick Execution Timing."""

    def evaluate_setup(
        self,
        bias_res: TopDownBiasResult,
        features: ScalperFeatures,
        spec: InstrumentSpecification
    ) -> ContextualSetup:
        reasons = []

        # 1. Require Clear Top-Down Bias
        if bias_res.bias in ["NEUTRAL", "NO_TRADE"]:
            reasons.append("Rejected: Top-Down Bias is NEUTRAL or CONFLICTED")
            return ContextualSetup(
                setup_type="NONE", direction="NONE", approved=False,
                top_down_bias=bias_res.bias, alignment_score=bias_res.alignment_score,
                tick_timing_confirmed=False, reasons=reasons
            )

        direction = "BUY" if "BULLISH" in bias_res.bias else "SELL"

        # 2. Tick Engine Confirming Execution Timing
        tick_timing_confirmed = False
        if direction == "BUY" and features.bullish_tick_ratio >= 0.52:
            tick_timing_confirmed = True
            reasons.append(f"Tick Timing Confirmed: Bullish Tick Ratio ({features.bullish_tick_ratio:.2f}) >= 0.52")
        elif direction == "SELL" and features.bullish_tick_ratio <= 0.48:
            tick_timing_confirmed = True
            reasons.append(f"Tick Timing Confirmed: Bearish Tick Ratio ({1.0 - features.bullish_tick_ratio:.2f}) >= 0.52")
        else:
            reasons.append(f"Tick Timing Rejected: Tick Ratio ({features.bullish_tick_ratio:.2f}) lacks short-term alignment with {direction} bias")

        approved = tick_timing_confirmed and abs(bias_res.alignment_score) >= 0.50

        return ContextualSetup(
            setup_type="TREND_CONTINUATION",
            direction=direction,
            approved=approved,
            top_down_bias=bias_res.bias,
            alignment_score=bias_res.alignment_score,
            tick_timing_confirmed=tick_timing_confirmed,
            reasons=reasons
        )
