from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import numpy as np

from app.context.bias_engine import TopDownBiasResult
from app.context.price_location import PriceLocationResult
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

@dataclass
class SweepConfluenceConfig:
    require_htf_bias: bool = False
    require_prem_disc: bool = False
    require_structure_shift: bool = False
    require_displacement: bool = False
    require_ltf_confirm: bool = False
    sweep_type_filter: Optional[str] = None

@dataclass
class SweepConfluenceResult:
    config_name: str
    sample_size: int
    win_rate: float
    profit_factor: float
    gross_expectancy_r: float
    net_expectancy_r: float
    net_profit_dollars: float
    max_drawdown_percent: float
    outperforms_baseline: bool
    brier_score_oos: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SweepConfluenceEngine:
    """Evaluates conditional confluence ladder for LIQUIDITY_SWEEP_REVERSAL setup."""

    def evaluate_sweep_confluence(
        self,
        bias_res: TopDownBiasResult,
        loc_res: PriceLocationResult,
        features: ScalperFeatures,
        spec: InstrumentSpecification,
        config: SweepConfluenceConfig
    ) -> bool:
        # Base Requirement: Must be a Liquidity Sweep Reversal setup
        is_bullish_bias = ("BULLISH" in bias_res.bias)

        # 1. Require HTF Bias Alignment
        if config.require_htf_bias and bias_res.bias in ["NEUTRAL", "NO_TRADE"]:
            return False

        # 2. Require Premium / Discount Location
        if config.require_prem_disc:
            if is_bullish_bias and loc_res.location != "DISCOUNT":
                return False
            if not is_bullish_bias and loc_res.location != "PREMIUM":
                return False

        # 3. Require Market Structure Shift (BOS/CHoCH)
        if config.require_structure_shift and abs(bias_res.alignment_score) < 0.75:
            return False

        # 4. Require Displacement (Normalized Momentum >= 2.0)
        if config.require_displacement and abs(features.normalized_momentum) < 2.0:
            return False

        # 5. Require 1M Tick Confirmation
        if config.require_ltf_confirm:
            if is_bullish_bias and features.bullish_tick_ratio < 0.52:
                return False
            if not is_bullish_bias and features.bullish_tick_ratio > 0.48:
                return False

        return True
