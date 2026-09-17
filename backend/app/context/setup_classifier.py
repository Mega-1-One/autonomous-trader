from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

from app.context.bias_engine import TopDownBiasResult
from app.context.price_location import PriceLocationResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class SetupClassificationResult:
    setup_type: str                  # "TREND_CONTINUATION", "LIQUIDITY_SWEEP_REVERSAL", "BREAKOUT_RETEST", "RANGE_REVERSAL", "NO_SETUP"
    direction: str                   # "BUY", "SELL", or "NONE"
    approved: bool
    quality_score: float             # 0.0 to 1.0
    price_location: str
    ltf_confirmation: str
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SetupClassifier:
    """Classifies contextual setups independently with price location and lower-timeframe entry confirmation."""

    def classify_setup(
        self,
        bias_res: TopDownBiasResult,
        loc_res: PriceLocationResult,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        target_setup_filter: Optional[str] = None
    ) -> SetupClassificationResult:
        if bias_res.bias in ["NEUTRAL", "NO_TRADE"]:
            return SetupClassificationResult(
                setup_type="NO_SETUP", direction="NONE", approved=False,
                quality_score=0.0, price_location=loc_res.location,
                ltf_confirmation="NONE", reasons=["Top-Down Bias is neutral"]
            )

        # Determine setup type & direction based on context
        is_bullish = ("BULLISH" in bias_res.bias)
        direction = "BUY" if is_bullish else "SELL"

        # 1. Trend Continuation Setup
        if is_bullish and loc_res.location in ["DISCOUNT", "EQUILIBRIUM"]:
            st_type = "TREND_CONTINUATION"
        elif not is_bullish and loc_res.location in ["PREMIUM", "EQUILIBRIUM"]:
            st_type = "TREND_CONTINUATION"
        # 2. Liquidity Sweep Reversal Setup
        elif is_bullish and loc_res.location == "PREMIUM":
            st_type = "LIQUIDITY_SWEEP_REVERSAL"
            direction = "SELL"
        elif not is_bullish and loc_res.location == "DISCOUNT":
            st_type = "LIQUIDITY_SWEEP_REVERSAL"
            direction = "BUY"
        else:
            st_type = "BREAKOUT_RETEST"

        if target_setup_filter and st_type != target_setup_filter:
            return SetupClassificationResult(
                setup_type="NO_SETUP", direction="NONE", approved=False,
                quality_score=0.0, price_location=loc_res.location,
                ltf_confirmation="NONE", reasons=[f"Filtered out: {st_type} != {target_setup_filter}"]
            )

        # 3. LTF Execution Trigger Confirmation
        ltf_confirmed = False
        if direction == "BUY" and features.bullish_tick_ratio >= 0.52:
            ltf_confirmed = True
            ltf_type = "1M_TICK_MOMENTUM_CONFIRMED"
        elif direction == "SELL" and features.bullish_tick_ratio <= 0.48:
            ltf_confirmed = True
            ltf_type = "1M_TICK_MOMENTUM_CONFIRMED"
        else:
            ltf_type = "UNCONFIRMED"

        q_score = round((abs(bias_res.alignment_score) * 0.5) + (0.5 if ltf_confirmed else 0.0), 2)
        approved = ltf_confirmed and q_score >= 0.60

        return SetupClassificationResult(
            setup_type=st_type,
            direction=direction,
            approved=approved,
            quality_score=q_score,
            price_location=loc_res.location,
            ltf_confirmation=ltf_type,
            reasons=[f"Setup: {st_type} ({direction}) | Location: {loc_res.location} | Quality: {q_score}"]
        )
