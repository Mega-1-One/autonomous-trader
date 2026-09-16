"""C-01 tests: spec-based PnL correctness, position price fix, FAILED->502."""
import pytest

from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine
from app.scalper.position_manager import ScalpPositionManager, ScalpPosition
from app.services.market_data import MarketDataService


def _engine():
    adapter = MockMT5Adapter()
    adapter.connect()
    return ExecutionEngine(adapter=adapter)


def _open_position(engine, symbol, entry, sl, tp, volume=0.1):
    res = engine.execute_signal({
        "client_signal_id": f"SIG_{symbol}_{entry}",
        "symbol": symbol, "direction": "LONG",
        "entry_price": entry, "stop_loss": sl, "take_profit": tp,
    })
    assert res["status"] == "EXECUTED", res
    return list(engine.positions.values())[-1]


def test_eurusd_floating_pnl_uses_forex_contract():
    # EURUSD diff 0.001 (10 pips) * contract 100000 * actual risk-sized volume
    engine = _engine()
    pos = _open_position(engine, "EURUSD", 1.08500, 1.08400, 1.09500, volume=0.1)
    updated = engine.update_positions({"EURUSD": 1.08600})
    assert updated[0]["floating_pnl"] == pytest.approx(0.001 * 100000.0 * pos.volume)


def test_xauusd_pnl_regression_unchanged():
    # XAUUSD diff 1.0 * contract 100 * actual volume (identical to old x100 math)
    engine = _engine()
    pos = _open_position(engine, "XAUUSD", 2400.0, 2390.0, 2420.0, volume=0.1)
    updated = engine.update_positions({"XAUUSD": 2401.0})
    assert updated[0]["floating_pnl"] == pytest.approx(1.0 * 100.0 * pos.volume)


def test_nas100_realized_pnl_contract_one():
    # Mock NAS100 spec contract is 20; broker info takes precedence.
    engine = _engine()
    pos = _open_position(engine, "NAS100", 19500.0, 19400.0, 19700.0, volume=0.1)
    engine._close_position(pos, 19510.0, "MANUAL_CLOSE")
    assert pos.realized_pnl == pytest.approx(10.0 * 20.0 * pos.volume)


def test_position_manager_forex_pnl():
    import time
    pm = ScalpPositionManager(max_holding_seconds=1000.0)
    now = time.time()
    pos = ScalpPosition(
        position_id="P1", symbol="EURUSD", direction="BUY", volume=0.1,
        entry_price=1.08500, current_price=1.08500,
        stop_loss=1.08400, take_profit=1.09500, entry_time=now, status="OPEN",
    )
    pm.add_position(pos)
    pm.update_and_check_exits(current_bid=1.08600, current_ask=1.08600, now=now + 1)
    assert pos.floating_pnl == pytest.approx(0.001 * 100000.0 * 0.1)


@pytest.mark.asyncio
async def test_broker_failed_maps_to_502(async_client):
    """A broker FAILED send surfaces as HTTP 502 (C-01 owns this; success shapes unchanged)."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.api import deps

    deps.init_app_state(app)

    class _FailingAdapter(MockMT5Adapter):
        def send_order(self, order_dict):
            return {"retcode": 10027, "comment": "Algo trading disabled"}

    failing = _FailingAdapter()
    failing.connect()

    from app.api.deps import get_execution_engine
    svc = deps.get_execution_engine.__wrapped__ if hasattr(deps.get_execution_engine, "__wrapped__") else None
    # Simpler: swap the shared engine's adapter (DI override-free, same-process)
    old_engine = app.state.execution_engine
    from app.execution.engine import ExecutionEngine as EE
    app.state.execution_engine = EE(adapter=failing, risk_engine=app.state.risk_engine)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/execution/orders", json={
                "client_signal_id": "SIG_FAIL_502",
                "symbol": "XAUUSD", "direction": "LONG",
                "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
            })
        assert res.status_code == 502
        assert "Algo trading disabled" in res.json()["detail"]
    finally:
        app.state.execution_engine = old_engine


@pytest.mark.asyncio
async def test_position_endpoint_uses_real_prices_for_eurusd(async_client):
    """Positions endpoint must not mark EURUSD at the hard-coded 2400.0 (N-06)."""
    from app.main import app
    from app.api import deps
    deps.init_app_state(app)

    res = await async_client.post("/api/execution/orders", json={
        "client_signal_id": "SIG_PRICE_001",
        "symbol": "EURUSD", "direction": "LONG",
        "entry_price": 1.08500, "stop_loss": 1.08400, "take_profit": 1.09500,
    })
    assert res.status_code == 200
    pos_id = res.json()["position"]["position_id"]

    res_pos = await async_client.get("/api/execution/positions")
    assert res_pos.status_code == 200
    data = res_pos.json()
    # The mock's sine-wave candle closes may TP/SL the position; it must be
    # present somewhere and marked at a real (non-constant) price either way.
    mine = [p for p in data["open_positions"] + data["closed_positions"]
            if p["position_id"] == pos_id]
    assert mine, "position missing from endpoint"
    assert mine[0]["current_price"] != 2400.0
    # Mock has no bid/ask on the spec -> falls back to a candle close
    assert abs(mine[0]["current_price"] - 1.0850) < 5.0


def test_get_latest_price_prefers_candle_close_over_constant():
    svc = MarketDataService()
    price = svc.get_latest_price("EURUSD")
    assert price is not None
    assert price != 2400.0
    assert abs(price - 1.0850) < 5.0  # mock candle close range
