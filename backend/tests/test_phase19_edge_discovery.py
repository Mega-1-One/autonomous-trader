import pytest
from app.research.dataset import SignalResearchObservation
from app.research.edge_discovery import EdgeDiscoveryEngine

def test_baseline_comparison_and_decile_analysis():
    obs_list = []
    for i in range(100):
        score = 0.50 + (i * 0.004)
        r_val = 1.5 if i > 50 else -1.0
        obs = SignalResearchObservation(
            signal_id=f"SIG_DEC_{i}", timestamp=100.0 + i, symbol="XAUUSD", direction="BUY",
            signal_type="QUALIFIED", regime="TRENDING_UP", strategy="TrendContinuation",
            opportunity_score=score, bullish_evidence=0.6, bearish_evidence=0.0, conflict_score=0.0,
            technical_score=0.7, structure_score=0.8, liquidity_score=0.6, momentum_score=0.7,
            volatility_score=0.5, session_score=0.5, spread_pips=0.2, estimated_slippage_pips=0.1,
            estimated_commission_dollars=0.35, estimated_total_cost_dollars=0.50,
            entry_reference=2400.0, stop_reference=2397.0, target_reference=2404.5,
            ev_estimate_raw=1.5,
            outcomes_by_horizon={"30s": {"mfe_pips": 5.0, "mae_pips": 2.0, "net_pips": 3.0}},
            tp_hit_before_sl=(r_val > 0), sl_hit_before_tp=(r_val < 0), net_realized_r=r_val
        )
        obs_list.append(obs)

    engine = EdgeDiscoveryEngine()
    deciles = engine.analyze_opportunity_deciles(obs_list)

    assert len(deciles) == 10
    assert deciles[0].sample_count == 10
    assert deciles[-1].raw_positive_rate > deciles[0].raw_positive_rate

    # Baseline comparison check
    def mock_model(s): return 0.5 + (s * 0.1)
    train_obs = obs_list[:60]
    val_obs = obs_list[60:80]
    oos_obs = obs_list[80:]

    base_res = engine.evaluate_baseline_comparison(train_obs, val_obs, oos_obs, mock_model)
    assert base_res.oos_baseline_brier > 0
    assert base_res.oos_model_brier > 0

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
