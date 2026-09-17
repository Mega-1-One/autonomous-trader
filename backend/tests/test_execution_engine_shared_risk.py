"""B-01 tests: shared application state, DI wiring, and explicit RiskEngine injection.

- R-06: ExecutionEngine must reuse the injected RiskEngine, not build its own.
- (API emergency-stop propagation lives in test_emergency_stop_propagation.py.)
"""
import pytest

from app.api import deps
from app.execution.engine import ExecutionEngine
from app.risk.engine import RiskEngine


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
    assert "EMERGENCY STOP" in result["reason"].upper()
    app.state.risk_engine.reset_emergency_stop()
