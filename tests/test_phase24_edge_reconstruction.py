import pytest
from app.research.edge_reconstruction import EdgeReconstructionEngine, EdgeCandidateConfig, EdgeCandidateResult

def test_edge_reconstruction_ranking():
    engine = EdgeReconstructionEngine()
    results = []

    for i in range(50):
        cfg = EdgeCandidateConfig("XAUUSD", "LONDON", "TRENDING_UP", "LIQUIDITY_SWEEP_REVERSAL", "1m", 1.5, 3.0)
        res = EdgeCandidateResult(
            config=cfg,
            sample_size=40 if i > 5 else 10,
            win_rate=0.40,
            profit_factor=1.2 if i == 10 else 0.8,
            gross_expectancy_r=0.3,
            net_expectancy_r=0.2 if i == 10 else -0.1,
            net_profit_dollars=100.0 if i == 10 else -50.0,
            max_drawdown_percent=1.5,
            oos_net_expectancy_r=0.25 if i == 10 else -0.15,
            oos_profit_factor=1.25 if i == 10 else 0.75,
            is_statistically_robust=(i == 10)
        )
        results.append(res)

    top20 = engine.rank_top_candidates(results, top_n=20)
    assert len(top20) > 0
    assert top20[0].oos_net_expectancy_r == 0.25
    assert top20[0].sample_size >= 30

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
