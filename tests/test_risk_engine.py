import pytest
from app.risk.engine import RiskEngine

def test_position_sizing_gold():
    engine = RiskEngine()
    gold_info = {
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01
    }

    # $10,000 equity @ 0.5% risk = $50 risk budget
    # Entry 2400.0, SL 2390.0 -> Risk distance = $10.00 (1000 ticks)
    # Risk per lot = 1000 ticks * $1.0 = $1,000 per lot
    # Calculated volume = $50 / $1000 = 0.05 lots
    vol = engine.calculate_position_size(10000.0, 2400.0, 2390.0, gold_info)
    assert vol == 0.05

def test_evaluate_trade_risk_approval():
    engine = RiskEngine()
    gold_info = {
        "tick_size": 0.01,
        "tick_value": 1.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01
    }
    acc = {"equity": 10000.0}
    signal = {"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0} # RR = 2.0

    decision = engine.evaluate_trade_risk(signal, acc, gold_info, current_open_positions_count=0, current_spread_pips=1.0)
    assert decision.approved is True
    assert decision.calculated_volume == 0.05
    assert decision.effective_rr == 2.0

def test_evaluate_trade_risk_max_positions_rejection():
    # When explicit max positions limit is set
    engine = RiskEngine(config={"maximum_open_positions": 1, "risk_per_trade_percent": 0.5})
    gold_info = {"tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}
    acc = {"equity": 10000.0}
    signal = {"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0}

    # Already 1 position open (max allowed is 1)
    decision = engine.evaluate_trade_risk(signal, acc, gold_info, current_open_positions_count=1)
    assert decision.approved is False
    assert "Maximum open positions limit" in decision.rejection_reason

def test_evaluate_trade_risk_spread_rejection():
    # When explicit max spread limit is set
    engine = RiskEngine(config={"maximum_spread_pips": 3.0, "risk_per_trade_percent": 0.5})
    gold_info = {"tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}
    acc = {"equity": 10000.0}
    signal = {"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0}

    # Spread is 5.0 pips (max allowed is 3.0 pips)
    decision = engine.evaluate_trade_risk(signal, acc, gold_info, current_spread_pips=5.0)
    assert decision.approved is False
    assert "spread" in decision.rejection_reason

def test_scalper_unlimited_trades_and_no_drawdown_lock():
    # Default Scalper Risk Engine has 0 limits (unlimited trades, no daily lock, no DD cap)
    engine = RiskEngine(config={
        "risk_per_trade_percent": 0.1,
        "maximum_daily_loss_percent": 0,
        "maximum_trades_per_day": 0,
        "maximum_open_positions": 0
    })
    gold_info = {"tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}
    acc = {"equity": 10000.0}
    signal = {"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0}

    # Simulate 50 trades already executed today and negative realized PnL (-$500)
    engine.today_trade_count = 50
    engine.today_realized_pnl = -500.0

    decision = engine.evaluate_trade_risk(signal, acc, gold_info, current_open_positions_count=5, current_spread_pips=2.0)
    assert decision.approved is True
    assert decision.calculated_volume == 0.01

def test_emergency_stop_blocking():
    engine = RiskEngine()
    gold_info = {"tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}
    acc = {"equity": 10000.0}
    signal = {"entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0}

    engine.trigger_emergency_stop("Test Stop")
    assert engine.emergency_stop_active is True

    decision = engine.evaluate_trade_risk(signal, acc, gold_info)
    assert decision.approved is False
    assert "Emergency Stop" in decision.rejection_reason

@pytest.mark.asyncio
async def test_api_risk_status(async_client):
    res = await async_client.get("/api/risk/status")
    assert res.status_code == 200
    data = res.json()
    assert "emergency_stop_active" in data
    assert "risk_parameters" in data

@pytest.mark.asyncio
async def test_api_emergency_stop_trigger(async_client):
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "Testing endpoint"})
    assert res.status_code == 200
    data = res.json()
    assert data["emergency_stop_active"] is True

    # Reset afterwards to avoid side-effects
    res_reset = await async_client.post("/api/system/reset-emergency-stop")
    assert res_reset.status_code == 200
    assert res_reset.json()["emergency_stop_active"] is False
