from dataclasses import dataclass
from typing import List, Optional

from app.scalper.signal import ScalpSignal
from app.regime.engine import RegimeState, MarketRegime

@dataclass
class FusedOpportunity:
    opportunity_score: float   # Score from 0.0 to 1.0 (NOT win probability)
    approved: bool
    direction: str
    reasons: List[str]
    signal: Optional[ScalpSignal]

class SignalFusionEngine:
    """Aggregates strategy signals, regime context, conflict detection, and generates OpportunityScore."""

    def evaluate_opportunity(
        self,
        signal: ScalpSignal,
        regime_state: RegimeState,
        strategy_weight: float = 1.0,
        min_opportunity_score: float = 0.65
    ) -> FusedOpportunity:
        reasons = list(signal.reasons)

        # 1. Regime Allowance Check
        if not regime_state.allow_trading:
            return FusedOpportunity(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                reasons=[f"NO TRADE: Regime {regime_state.regime.value} disallows trading"] + regime_state.reasons,
                signal=signal
            )

        # 2. Conflict Detection (e.g., BUY signal during TRENDING_DOWN regime)
        if signal.direction == "BUY" and regime_state.regime == MarketRegime.TRENDING_DOWN:
            return FusedOpportunity(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                reasons=["SIGNAL CONFLICT: BUY signal generated during TRENDING_DOWN regime"],
                signal=signal
            )
        elif signal.direction == "SELL" and regime_state.regime == MarketRegime.TRENDING_UP:
            return FusedOpportunity(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                reasons=["SIGNAL CONFLICT: SELL signal generated during TRENDING_UP regime"],
                signal=signal
            )

        if signal.status != "APPROVED":
            return FusedOpportunity(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                reasons=reasons,
                signal=signal
            )

        # 3. Calculate Deterministic Opportunity Score
        score = round(signal.confidence_score * regime_state.confidence * strategy_weight, 2)

        approved = score >= min_opportunity_score
        if not approved:
            reasons.append(f"OpportunityScore ({score}) below threshold ({min_opportunity_score})")

        return FusedOpportunity(
            opportunity_score=score,
            approved=approved,
            direction=signal.direction,
            reasons=reasons,
            signal=signal
        )
