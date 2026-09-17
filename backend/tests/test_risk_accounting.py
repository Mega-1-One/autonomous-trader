"""N2-H1/N2-M7 tests: daily risk accounting actually works.

- Executed fills increment today_trade_count; closes accumulate realized PnL.
- maximum_trades_per_day and the daily-loss lock fire once counters move.
- Counters roll over on calendar-day change (locks clear).
- /api/risk/evaluate counts real open positions (no max-open bypass).
"""
import pytest

from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine
from app.risk.engine import RiskEngine


def _engine(risk_config=None):
    adapter = MockMT5Adapter()
    adapter.connect()
    risk = RiskEngine(config=risk_config) if risk_config is not None else RiskEngine()
    return ExecutionEngine(adapter=adapter, risk_engine=risk)


def _signal(order_id, entry=2400.0, sl=2390.0, tp=2420.0):
    return {
        "client_signal_id": order_id,
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": entry, "stop_loss": sl, "take_profit": tp,
    }


def test_trade_count_increments_and_max_trades_fires():
    engine = _engine({"risk_per_trade_percent": 0.1, "maximum_trades_per_day": 1})
    first = engine.execute_signal(_signal("SIG_H1_A"))
    assert first["status"] == "EXECUTED"
    assert engine.risk_engine.today_trade_count == 1
    second = engine.execute_signal(_signal("SIG_H1_B"))
    assert second["status"] == "REJECTED"
    assert "Maximum trades per day" in second["reason"]


def test_realized_pnl_accumulates_and_daily_lock_fires():
    engine = _engine({"risk_per_trade_percent": 0.1, "maximum_daily_loss_percent": 0.05})
    res = engine.execute_signal(_signal("SIG_H1_C"))
    assert res["status"] == "EXECUTED"
    pos_id = res["position"]["position_id"]
    # Force an SL close: SL 2390 hit -> realized (2390-2400)*100*0.01 = -10.
    engine.update_positions({"XAUUSD": 2380.0})
    assert engine.positions[pos_id].status == "CLOSED"
    assert engine.risk_engine.today_realized_pnl == pytest.approx(-10.0)
    # 0.05% of 10000 = $5 limit; -10 <= -5 -> locked on next evaluation.
    nxt = engine.execute_signal(_signal("SIG_H1_D"))
    assert nxt["status"] == "REJECTED"
    assert "Daily loss limit" in nxt["reason"]
    assert engine.risk_engine.daily_lock_active is True


def test_rollover_resets_counters_and_locks():
    engine = _engine({"risk_per_trade_percent": 0.1, "maximum_trades_per_day": 1})
    engine.risk_engine.today_date = "2000-01-01"
    engine.risk_engine.today_trade_count = 5
    engine.risk_engine.daily_lock_active = True
    engine.risk_engine.daily_lock_reason = "stale lock"
    res = engine.execute_signal(_signal("SIG_H1_E"))
    assert res["status"] == "EXECUTED"
    assert engine.risk_engine.today_trade_count == 1
    assert engine.risk_engine.daily_lock_active is False
    assert engine.risk_engine.daily_lock_reason is None


def test_record_methods_rollover():
    risk = RiskEngine(config={"risk_per_trade_percent": 0.1})
    risk.today_date = "2000-01-01"
    risk.today_trade_count = 9
    risk.record_executed_trade()
    assert risk.today_trade_count == 1
    risk.record_closed_trade(-25.0)
    assert risk.today_realized_pnl == pytest.approx(-25.0)


@pytest.mark.asyncio
async def test_risk_evaluate_uses_real_open_count(async_client):
    """N2-M7: /api/risk/evaluate must not bypass maximum-open-positions."""
    from app.main import app
    from app.api import deps
    deps.init_app_state(app)
    risk_engine = app.state.execution_engine.risk_engine
    old_max_open = risk_engine.maximum_open_positions
    risk_engine.maximum_open_positions = 1
    try:
        res = await async_client.post("/api/execution/orders", json={
            "client_signal_id": "SIG_H1_OPEN",
            "symbol": "XAUUSD", "direction": "LONG",
            "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        })
        assert res.status_code == 200
        pos_id = res.json()["position"]["position_id"]
        try:
            ev = await async_client.post("/api/risk/evaluate", json={
                "symbol": "XAUUSD", "entry_price": 2400.0,
                "stop_loss": 2390.0, "take_profit": 2420.0,
            })
            assert ev.status_code == 200
            decision = ev.json()["decision"]
            assert decision["approved"] is False
            assert "Maximum open positions" in decision["rejection_reason"]
        finally:
            await async_client.post(f"/api/execution/positions/{pos_id}/close")
    finally:
        risk_engine.maximum_open_positions = old_max_open
