"""H-2/M-6 tests: mode-aware adapter selection, host-independent PAPER flow.

build_adapter() must return the mock adapter in PAPER/BACKTEST even when a
real MT5 terminal is present, so POST /api/execution/orders works on any
host. DEMO/LIVE keep real-first with mock fallback.
"""
import pytest

import app.core.config as config_module
from app.core.config import ExecutionMode, Settings
from app.data.mt5_mock import MockMT5Adapter
from app.data.mt5_real import RealMT5Adapter


@pytest.fixture
def mode_env():
    original = config_module.settings

    def _set(mode, live=False, confirm=False):
        s = Settings()
        object.__setattr__(s, "EXECUTION_MODE", mode)
        object.__setattr__(s, "ENABLE_LIVE_TRADING", live)
        object.__setattr__(s, "LIVE_TRADING_CONFIRMATION", confirm)
        config_module.settings = s
        return s

    yield _set
    config_module.settings = original


class _ConnectingReal(RealMT5Adapter):
    """Simulates an MT5-present host without the terminal."""
    connected_attempts = 0

    def connect(self):
        type(self).connected_attempts += 1
        self._connected = True
        return True


def test_paper_ignores_real_terminal(mode_env, monkeypatch):
    """PAPER never instantiates the real adapter, even if MT5 is present."""
    import app.api.deps as deps
    mode_env(ExecutionMode.PAPER)
    created = []

    class _SpyReal(_ConnectingReal):
        def __init__(self):
            created.append(True)
            super().__init__()

    monkeypatch.setattr(deps, "RealMT5Adapter", _SpyReal)
    adapter = deps.build_adapter()
    assert isinstance(adapter, MockMT5Adapter)
    assert created == []
    assert adapter.is_connected()


def test_backtest_ignores_real_terminal(mode_env, monkeypatch):
    import app.api.deps as deps
    mode_env(ExecutionMode.BACKTEST)
    monkeypatch.setattr(deps, "RealMT5Adapter", _ConnectingReal)
    assert isinstance(deps.build_adapter(), MockMT5Adapter)


def test_demo_prefers_real_when_available(mode_env, monkeypatch):
    import app.api.deps as deps
    mode_env(ExecutionMode.DEMO)
    monkeypatch.setattr(deps, "RealMT5Adapter", _ConnectingReal)
    assert isinstance(deps.build_adapter(), _ConnectingReal)


def test_demo_falls_back_to_mock_without_terminal(mode_env):
    import app.api.deps as deps
    mode_env(ExecutionMode.DEMO)
    # MetaTrader5 is not installed here, so RealMT5Adapter.connect() fails.
    assert isinstance(deps.build_adapter(), MockMT5Adapter)


@pytest.mark.asyncio
async def test_live_without_terminal_refuses_orders_not_simulates(async_client, mode_env):
    """NEW-01: LIVE + dead terminal must refuse, never simulate EXECUTED."""
    from app.main import app
    mode_env(ExecutionMode.LIVE, live=True, confirm=True)
    saved = dict(app.state.__dict__)
    for attr in ("adapter", "market_service", "risk_engine",
                 "execution_engine", "strategy_engine"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    try:
        # No terminal here -> lazy state rebuild falls back to mock, and the
        # gate must refuse the simulated fill instead of EXECUTED.
        res = await async_client.post("/api/execution/orders", json={
            "client_signal_id": "SIG_LIVE_NOSIM",
            "symbol": "XAUUSD", "direction": "LONG",
            "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        })
        assert res.status_code == 400, res.text
        assert "simulated" in res.json()["detail"].lower()
    finally:
        for attr in ("adapter", "market_service", "risk_engine",
                     "execution_engine", "strategy_engine"):
            if hasattr(app.state, attr):
                delattr(app.state, attr)
        for attr, value in saved.items():
            setattr(app.state, attr, value)


@pytest.mark.asyncio
async def test_health_reports_simulated_execution(async_client, mode_env):
    """NEW-01/NEW-05: degraded real-money mode is operator-visible in health."""
    mode_env(ExecutionMode.LIVE, live=True, confirm=True)
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["execution_mode"] == "LIVE"
    assert data["mt5_adapter"] == "MockMT5Adapter"
    assert data["simulated_execution"] is True


@pytest.mark.asyncio
async def test_api_paper_order_host_independent(async_client, mode_env, monkeypatch):
    """POST /api/execution/orders succeeds in PAPER with an MT5-present host."""
    import app.api.deps as deps
    from app.main import app
    mode_env(ExecutionMode.PAPER)
    monkeypatch.setattr(deps, "RealMT5Adapter", _ConnectingReal)
    # Force state rebuild through the mode-aware path.
    saved = dict(app.state.__dict__)
    for attr in ("adapter", "market_service", "risk_engine",
                 "execution_engine", "strategy_engine"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    try:
        res = await async_client.post("/api/execution/orders", json={
            "client_signal_id": "SIG_HOST_INDEP",
            "symbol": "XAUUSD", "direction": "LONG",
            "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        })
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "EXECUTED"
        assert isinstance(app.state.adapter, MockMT5Adapter)
    finally:
        for attr in ("adapter", "market_service", "risk_engine",
                     "execution_engine", "strategy_engine"):
            if hasattr(app.state, attr):
                delattr(app.state, attr)
        for attr, value in saved.items():
            setattr(app.state, attr, value)
