from dataclasses import dataclass, asdict
from typing import List, Dict, Any

@dataclass
class EdgeCandidateConfig:
    instrument: str
    session: str
    regime: str
    setup: str
    entry_timing: str
    sl_atr: float
    tp_atr: float

@dataclass
class EdgeCandidateResult:
    config: EdgeCandidateConfig
    sample_size: int
    win_rate: float
    profit_factor: float
    gross_expectancy_r: float
    net_expectancy_r: float
    net_profit_dollars: float
    max_drawdown_percent: float
    oos_net_expectancy_r: float
    oos_profit_factor: float
    is_statistically_robust: bool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["config"] = asdict(self.config)
        return d

class EdgeReconstructionEngine:
    """Evaluates full combinatorial matrix: Instrument x Session x Regime x Setup x Entry Timing x SL/TP Matrix."""

    SESSIONS = ["ASIA", "LONDON", "NEW_YORK", "OVERLAP"]
    REGIMES = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "BREAKOUT", "VOLATILITY_EXPANSION"]
    SETUPS = [
        "LIQUIDITY_SWEEP_REVERSAL", "LIQUIDITY_SWEEP_CONTINUATION",
        "TREND_CONTINUATION", "BOS_CONTINUATION", "CHOCH_REVERSAL"
    ]
    TIMINGS = ["Immediate", "5s", "10s", "15s", "30s", "1m"]
    SL_TP_PAIRS = [(0.75, 1.0), (1.0, 1.5), (1.0, 2.0), (1.5, 2.0), (1.5, 3.0), (2.0, 3.0), (2.0, 4.0)]

    def rank_top_candidates(self, results: List[EdgeCandidateResult], top_n: int = 20) -> List[EdgeCandidateResult]:
        valid_results = [r for r in results if r.sample_size >= 30]
        sorted_results = sorted(valid_results, key=lambda x: (x.oos_net_expectancy_r, x.oos_profit_factor), reverse=True)
        return sorted_results[:top_n]
