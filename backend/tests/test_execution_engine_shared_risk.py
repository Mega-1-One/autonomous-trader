"""B-01 tests: shared application state, DI wiring, and explicit RiskEngine injection.

- P-01 in-process: POST /api/system/emergency-stop must block POST /api/execution/orders.
- R-06: ExecutionEngine must reuse the injected RiskEngine, not build its own.
"""
import pytest

from app.api import deps
from app.execution.engine import ExecutionEngine
from app.risk.engine import RiskEngine


@pytest.mark.asyncio
async def test_api_emergency_stop_blocks_order_submission(async_client):
    """API emergency stop must block the API order path (same shared engine)."""
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "DI test"})
    assert res.status_code == 200
    assert res.json()["emergency_stop_active"] is True

    res_order = await async_client.post("/api/execution/orders", json={
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res_order.status_code == 400
    assert "Emergency Stop" in res_order.json()["detail"]

    # Reset to restore clean state for other tests
    res_reset = await async_client.post("/api/system/reset-emergency-stop")
    assert res_reset.status_code == 200


@pytest.mark.asyncio
async def test_single_risk_engine_instance_per_process(async_client):
    """The risk router and the execution engine share ONE RiskEngine instance."""
    transport = async_client._transport
    app = transport.app
    deps.init_app_state(app)
    assert app.state.execution_engine.risk_engine is app.state.risk_engine


def test_execution_engine_injects_shared_risk_engine():
    adapter = None
    engine = ExecutionEngine(adapter=adapter, risk_engine=None)
    # No injection -> default built (standalone use allowed)
    assert engine.risk_engine is not None

    shared = RiskEngine()
    engine2 = ExecutionEngine(risk_engine=shared)
    assert engine2.risk_engine is shared


def test_risk_engine_not_constructed_inside_execution_engine():
    """Grep-equivalent assertion: ExecutionEngine source must not construct RiskEngine()."""
    import inspect
    from app.execution import engine as engine_module
    src = inspect.getsource(engine_module)
    assert "self.risk_engine = RiskEngine()" not in src
    assert "risk_engine if risk_engine is not None else RiskEngine()" in src


@pytest.mark.asyncio
async def test_injected_risk_engine_is_consulted(async_client):
    """Triggering stop on the shared engine (via API) rejects the engine path directly."""
    transport = async_client._transport
    app = transport.app
    deps.init_app_state(app)
    app.state.risk_engine.trigger_emergency_stop("wiring test")
    result = app.state.execution_engine.execute_signal({
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        "client_signal_id": "SIG_WIRING_TEST",
    })
    assert result["status"] == "REJECTED"
    assert "Emergency Stop" in result["reason"]
    app.state.risk_engine.reset_emergency_stop()
