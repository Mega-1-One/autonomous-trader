from dataclasses import dataclass
from typing import Dict, Any, Optional

from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class CostFilterResult:
    passed: bool
    total_transaction_cost_dollars: float
    expected_edge_dollars: float
    cost_to_target_ratio: float
    reasons: list[str]

class CostFilter:
    """Cost-Aware Filter evaluating spread, commission ($7/lot), slippage, and net expected edge."""

    def __init__(self, commission_per_lot: float = 7.0, base_slippage_pips: float = 0.1):
        self.commission_per_lot = commission_per_lot
        self.base_slippage_pips = base_slippage_pips

    def evaluate_cost(
        self,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        target_distance_pips: float = 4.5,
        volume: float = 0.05
    ) -> CostFilterResult:
        reasons = []

        pip_unit = spec.pip_size
        contract = spec.contract_size

        # 1. Spread Cost
        spread_cost_pips = features.spread_pips

        # 2. Commission Cost ($7.00 per lot round-trip)
        comm_dollars = volume * self.commission_per_lot
        comm_pips = comm_dollars / (contract * volume * pip_unit) if volume > 0 else 0.0

        # 3. Velocity-Dependent Slippage Cost
        slippage_pips = self.base_slippage_pips + abs(features.price_velocity) * 0.1

        # Total Transaction Cost in Pips
        total_cost_pips = spread_cost_pips + comm_pips + slippage_pips
        total_cost_dollars = total_cost_pips * pip_unit * contract * volume

        expected_edge_pips = target_distance_pips
        expected_edge_dollars = expected_edge_pips * pip_unit * contract * volume

        cost_to_target_ratio = round(total_cost_pips / max(0.001, target_distance_pips), 2)

        # Net Edge Gate: Net Expected Edge must be at least 1.5x total transaction cost
        passed = (target_distance_pips >= (total_cost_pips * 1.5))

        if not passed:
            reasons.append(f"Transaction cost ({total_cost_pips:.2f} pips / ${total_cost_dollars:.2f}) consumes expected target ({target_distance_pips:.2f} pips / ${expected_edge_dollars:.2f})")
        else:
            reasons.append(f"Positive Net Edge Verified: Target ({target_distance_pips:.2f} pips) > 1.5x Cost ({total_cost_pips:.2f} pips)")

        return CostFilterResult(
            passed=passed,
            total_transaction_cost_dollars=round(total_cost_dollars, 2),
            expected_edge_dollars=round(expected_edge_dollars, 2),
            cost_to_target_ratio=cost_to_target_ratio,
            reasons=reasons
        )
