import pytest
import time
from app.research.dataset import SignalResearchObservation
from app.research.labeler import OutcomeLabeler
from app.research.calibration import ProbabilityCalibrator
from app.research.walk_forward_split import WalkForwardCalibrator
from app.scalper.instrument import InstrumentSpecification

def test_outcome_labeler_zero_leakage():
    obs = SignalResearchObservation(
        signal_id="SIG_TEST_1", timestamp=100.0, symbol="XAUUSD", direction="BUY",
        signal_type="QUALIFIED", regime="TRENDING_UP", strategy="TrendContinuation",
        opportunity_score=0.75, bullish_evidence=0.6, bearish_evidence=0.0, conflict_score=0.0,
        technical_score=0.7, structure_score=0.8, liquidity_score=0.6, momentum_score=0.7,
        volatility_score=0.5, session_score=0.5, spread_pips=0.2, estimated_slippage_pips=0.1,
        estimated_commission_dollars=0.35, estimated_total_cost_dollars=0.50,
        entry_reference=2400.0, stop_reference=2397.0, target_reference=2404.5,
        ev_estimate_raw=1.5
    )

    future_ticks = [
        {"bid": 2401.0, "ask": 2401.02, "timestamp": 100.1},
        {"bid": 2402.5, "ask": 2402.52, "timestamp": 101.0},
        {"bid": 2405.0, "ask": 2405.02, "timestamp": 105.0},
    ]
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    labeler = OutcomeLabeler()
    labeled = labeler.label_observation(obs, future_ticks, spec)

    assert labeled.outcomes_by_horizon is not None
    assert "100ms" in labeled.outcomes_by_horizon
    assert "5s" in labeled.outcomes_by_horizon
    assert labeled.tp_hit_before_sl is True
    assert labeled.net_realized_r > 0

def test_calibration_insufficient_data_gating():
    calibrator = ProbabilityCalibrator()
    res = calibrator.fit_and_evaluate([])

    assert res.calibration_status == "INSUFFICIENT_DATA"
    assert res.brier_score == 1.0

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
