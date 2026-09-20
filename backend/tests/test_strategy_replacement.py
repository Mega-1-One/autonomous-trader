"""E2 replacement simulation (§17): a behaviorally different test-double
strategy drives the API, the runner-equivalent call path, the candle
backtester, risk, and execution through the StrategyProvider seam — with no
ICT imports anywhere in this file.

The dummy lives only in this test module and is unregistered afterwards; it
is a replaceability demonstration, not a shipped strategy (§3).
"""
import pytest

from app.strategy.provider import (
    MarketInputs,
    StrategyProvider,
    create_provider,
    evaluate_strategy,
    register_provider,
)


class DummySmaProvider(StrategyProvider):
    """Test double: always LONG at last close, fixed 2-pip SL / 4-pip TP."""

    name = "dummy_sma"

    def evaluate(self, inputs):
        candles = inputs.candles.get("LTF", []) or inputs.candles.get("HTF", [])
        entry = float(candles[-1]["close"]) if candles else 100.0
        pip = 0.1 if "XAU" in inputs.symbol else 0.0001
        return {
            "client_signal_id": "SIG_DUMMY",
            "symbol": inputs.symbol,
            "direction": "LONG",
            "entry_price": entry,
            "stop_loss": round(entry - 2.0 * pip, 5),
            "take_profit": round(entry + 4.0 * pip, 5),
            "status": "APPROVED",
            "setup_type": "DUMMY_SMA",
            "confidence": 0.1,
            "reasons": {"note": "test double"},
            "timestamp": "t",
        }


@pytest.fixture
def dummy_provider():
    register_provider(DummySmaProvider.name, DummySmaProvider)
    try:
        yield create_provider("dummy_sma", {})
    finally:
        from app.strategy import provider as provider_module
        del provider_module._PROVIDER_REGISTRY[DummySmaProvider.name]


def test_dummy_drives_backtest(dummy_provider):
    """Candle backtester consumes a non-ICT strategy through the seam."""
    from app.backtest.engine import BacktestEngine
    from app.data.mt5_mock import MockMT5Adapter

    adapter = MockMT5Adapter()
    adapter.connect()
    candles = adapter.fetch_candles("XAUUSD", "M5", count=120)
    engine = BacktestEngine(initial_balance=10000.0)
    engine.strategy_engine = dummy_provider
    report = engine.run("XAUUSD", candles, point_size=0.01)
    assert report.total_trades >= 1
    assert all(t.symbol == "XAUUSD" for t in engine.last_trades)


def test_dummy_decision_flows_through_risk_and_execution(dummy_provider):
    """Same contract feeds the unchanged risk + execution stack."""
    from app.data.mt5_mock import MockMT5Adapter
    from app.execution.engine import ExecutionEngine
    from app.risk.engine import RiskEngine

    decision = evaluate_strategy(
        dummy_provider,
        MarketInputs(symbol="XAUUSD", candles={"LTF": [{"close": 2400.0}]}),
    )
    assert decision["setup_type"] == "DUMMY_SMA"
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter, risk_engine=RiskEngine())
    result = engine.execute_signal(dict(decision, client_signal_id="SIG_DUMMY_E2E"))
    assert result["status"] == "EXECUTED"
    assert result["position"]["symbol"] == "XAUUSD"


@pytest.mark.asyncio
async def test_dummy_drives_api_signals(async_client, dummy_provider):
    """The /signals router renders whatever the active provider returns."""
    from app.main import app
    from app.api import deps

    app.dependency_overrides[deps.get_strategy_engine] = lambda: dummy_provider
    try:
        res = await async_client.get("/api/strategy/signals?symbol=XAUUSD")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "XAUUSD"
        assert data["signal"]["setup_type"] == "DUMMY_SMA"
        assert data["signal"]["status"] == "APPROVED"
    finally:
        app.dependency_overrides.clear()


def test_ict_default_still_registered():
    """The production default behind the seam is unchanged."""
    provider = create_provider("ict_scalp", None)
    assert provider.name == "ict_scalp"
    assert "dummy_sma" not in provider.name
