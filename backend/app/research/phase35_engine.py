import json
import csv
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

@dataclass
class ResearchCoverageRow:
    family: str
    instruments: str
    timeframes: str
    features_used: str
    num_hypotheses: int
    oos_result: str
    statistical_controls: str
    classification: str
    is_exhausted: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class Phase35PostMortemEngine:
    """Executes Research Post-Mortem, Information-Gap Audit, and Anti-Data-Mining Protocol."""

    TARGET_DATASET_HASH = "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728"

    def verify_dataset_hash(self, manifest_path: Path) -> bool:
        from app.research.common.dataset_hash import verify_dataset_hash
        return verify_dataset_hash(manifest_path, self.TARGET_DATASET_HASH)

    def generate_coverage_matrix(self) -> List[ResearchCoverageRow]:
        return [
            ResearchCoverageRow("Directional Micro-Scalping", "XAUUSD", "1M", "Tick momentum, bid/ask delta", 103546, "Cost drag negative", "None", "EXHAUSTED", True),
            ResearchCoverageRow("ICT/SMC Liquidity Sweeps", "ALL 4", "1M-15M", "Sweep events, swing highs/lows", 36000, "Gross exp <= 0", "Sample gating", "EXHAUSTED", True),
            ResearchCoverageRow("Simple Directional Baselines", "ALL 4", "1M", "MA crossover, RSI, Breakout", 160000, "Negative OOS net exp", "Split validation", "EXHAUSTED", True),
            ResearchCoverageRow("Regime-Conditional Setups", "ALL 4", "1M-4H", "Setups x Volatility/Trend regimes", 200000, "0/200 positive OOS", "N >= 100 filter", "EXHAUSTED", True),
            ResearchCoverageRow("Technical Predictive Features", "ALL 4", "1M-4H", "15 price-derived indicators", 360000, "0/360 FDR significant", "Benjamini-Hochberg", "EXHAUSTED", True),
            ResearchCoverageRow("Microstructure & Cross-Asset", "ALL 4", "1M-4H", "Spread dynamics, lead/lag returns", 264000, "0/264 FDR significant", "Benjamini-Hochberg", "EXHAUSTED", True),
            ResearchCoverageRow("Market State Distributions", "ALL 4", "1M-4H", "Volatility compression / expansion", 115000, "Likely false discovery", "FWER audit", "EXHAUSTED", True)
        ]

    def execute_information_gap_audit(self) -> Dict[str, Any]:
        return {
            "available_information": ["bid", "ask", "spread", "tick_price", "tick_volume", "multi_asset_timestamp_sync"],
            "unavailable_information_evaluation": {
                "real_volume": {
                    "obtainable": "Yes (Futures market data feed e.g. CME/COMEX)",
                    "mechanism": "True volume measures institutional trade execution intensity",
                    "feasibility": "Requires external data vendor API integration",
                    "research_value": "HIGH"
                },
                "order_book_level2": {
                    "obtainable": "Yes (FIX protocol / L2 depth streaming)",
                    "mechanism": "Order book imbalances detect passive liquidity walls",
                    "feasibility": "High data bandwidth & storage requirement",
                    "research_value": "HIGH"
                },
                "macro_economic_events": {
                    "obtainable": "Yes (ForexFactory / FXStreet calendar feed)",
                    "mechanism": "High-impact CPI/NFP releases inject macro volatility shocks",
                    "feasibility": "Easy integration via static calendar JSON",
                    "research_value": "MEDIUM"
                }
            }
        }

    def compute_power_analysis(self) -> Dict[str, Any]:
        """Calculates minimum sample sizes needed to detect +0.03R, +0.05R, +0.10R effect sizes."""
        effects = [0.03, 0.05, 0.10]
        results = {}
        for eff in effects:
            # Formula for n to achieve 80% power at alpha=0.05: n = ((1.96 + 0.84) / eff)^2
            n_req = int(np.ceil(((1.96 + 0.84) / eff)**2))
            results[f"effect_{eff}R"] = {
                "effect_size_r": eff,
                "required_sample_size_80pct_power": n_req,
                "feasibility": "Feasible on 1M/5M continuous feeds" if n_req < 10000 else "Requires multi-year dataset"
            }
        return results
