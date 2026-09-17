from dataclasses import dataclass, asdict
from typing import List, Dict, Any

from app.intelligence.analyzer import AnalysisResult
from app.intelligence.cost_analyzer import CostFilterResult
from app.intelligence.ev_engine import ExpectedValueEstimate

@dataclass
class FusedOpportunity2:
    opportunity_score: float         # Final score (0.0 to 1.0)
    approved: bool
    direction: str                   # "BUY", "SELL", or "NONE"
    recommended_strategy: str
    bullish_evidence: float
    bearish_evidence: float
    conflicting_evidence: bool
    cost_penalty: float
    ev_estimate: ExpectedValueEstimate
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ev_estimate"] = self.ev_estimate.to_dict()
        return d

class SignalFusionEngine2:
    """Signal Fusion 2.0 Architecture aggregating multi-factor evidence with conflict detection."""

    ANALYZER_WEIGHTS: Dict[str, float] = {
        "MarketStructureAnalyzer": 0.20,
        "TechnicalAnalyzer": 0.18,
        "LiquidityAnalyzer": 0.15,
        "CostFilter": 0.15,
        "MomentumAnalyzer": 0.10,
        "VolatilityAnalyzer": 0.10,
        "SessionAnalyzer": 0.05,
        "MeanReversionAnalyzer": -0.05,
    }

    def evaluate_multi_factor(
        self,
        results: List[AnalysisResult],
        cost_result: CostFilterResult,
        ev_estimate: ExpectedValueEstimate,
        min_opportunity_score: float = 0.65
    ) -> FusedOpportunity2:
        reasons = []
        bullish_score = 0.0
        bearish_score = 0.0

        for r in results:
            weight = self.ANALYZER_WEIGHTS.get(r.analyzer_name, 0.10)
            if r.direction == "BUY":
                bullish_score += (r.confidence * weight)
                reasons.extend([f"[{r.analyzer_name}] {reason}" for reason in r.reasons])
            elif r.direction == "SELL":
                bearish_score += (r.confidence * weight)
                reasons.extend([f"[{r.analyzer_name}] {reason}" for reason in r.reasons])

        # 1. Conflict Detection Gate
        conflicting_evidence = (bullish_score > 0.15 and bearish_score > 0.15)
        if conflicting_evidence:
            reasons.append(f"DIRECTIONAL CONFLICT DETECTED: Bullish ({bullish_score:.2f}) vs Bearish ({bearish_score:.2f})")
            return FusedOpportunity2(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                recommended_strategy="NONE",
                bullish_evidence=round(bullish_score, 2),
                bearish_evidence=round(bearish_score, 2),
                conflicting_evidence=True,
                cost_penalty=0.0,
                ev_estimate=ev_estimate,
                reasons=reasons
            )

        # 2. Cost Filter Gate
        cost_penalty = 0.0 if cost_result.passed else 0.30
        if not cost_result.passed:
            reasons.extend(cost_result.reasons)
            return FusedOpportunity2(
                opportunity_score=0.0,
                approved=False,
                direction="NONE",
                recommended_strategy="NONE",
                bullish_evidence=round(bullish_score, 2),
                bearish_evidence=round(bearish_score, 2),
                conflicting_evidence=False,
                cost_penalty=cost_penalty,
                ev_estimate=ev_estimate,
                reasons=reasons
            )

        # 3. Determine Dominant Direction & Final Opportunity Score
        if bullish_score > bearish_score:
            direction = "BUY"
            raw_score = bullish_score
            rec_strategy = "TrendContinuation"
        elif bearish_score > bullish_score:
            direction = "SELL"
            raw_score = bearish_score
            rec_strategy = "TrendContinuation"
        else:
            direction = "NONE"
            raw_score = 0.0
            rec_strategy = "NONE"

        final_score = round(max(0.0, min(1.0, raw_score - cost_penalty)), 2)
        approved = (final_score >= min_opportunity_score and direction != "NONE" and ev_estimate.expected_value_dollars > 0)

        if not approved:
            reasons.append(f"OpportunityScore ({final_score:.2f}) or Net EV (${ev_estimate.expected_value_dollars:.2f}) insufficient")

        return FusedOpportunity2(
            opportunity_score=final_score,
            approved=approved,
            direction=direction,
            recommended_strategy=rec_strategy,
            bullish_evidence=round(bullish_score, 2),
            bearish_evidence=round(bearish_score, 2),
            conflicting_evidence=False,
            cost_penalty=cost_penalty,
            ev_estimate=ev_estimate,
            reasons=reasons
        )
