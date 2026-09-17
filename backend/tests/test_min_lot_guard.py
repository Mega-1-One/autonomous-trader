"""D-05 tests: optional min-lot over-risk guard (default off)."""
from app.risk.engine import RiskEngine

GOLD_INFO = {
    "tick_size": 0.01, "tick_value": 1.0,
    "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01,
}


def test_default_disabled_preserves_clamp_up():
    """Default config (0 = disabled): tiny sizing still clamps up to min_volume."""
    engine = RiskEngine(config={"risk_per_trade_percent": 0.1})
    # equity 100, SL 10 away: monetary risk $0.10, risk/contract $1000 -> clamps to 0.01
    vol = engine.calculate_position_size(100.0, 2400.0, 2390.0, GOLD_INFO)
    assert vol == 0.01


def test_enabled_rejects_clamped_over_risk():
    """Enabled guard (multiple=2): clamped volume risking >2x per-trade risk -> 0."""
    engine = RiskEngine(config={
        "risk_per_trade_percent": 0.1,
        "reject_when_clamped_over_risk_multiple": 2,
    })
    vol = engine.calculate_position_size(100.0, 2400.0, 2390.0, GOLD_INFO)
    assert vol == 0.0


def test_enabled_allows_within_multiple():
    """Enabled guard passes when the clamped risk is within the multiple."""
    engine = RiskEngine(config={
        "risk_per_trade_percent": 0.1,
        "reject_when_clamped_over_risk_multiple": 200,
    })
    vol = engine.calculate_position_size(100.0, 2400.0, 2390.0, GOLD_INFO)
    assert vol == 0.01


def test_enabled_zero_volume_rejects_trade():
    engine = RiskEngine(config={
        "risk_per_trade_percent": 0.1,
        "reject_when_clamped_over_risk_multiple": 2,
    })
    decision = engine.evaluate_trade_risk(
        signal={"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0},
        account_info={"equity": 100.0},
        symbol_info=GOLD_INFO,
    )
    assert not decision.approved
