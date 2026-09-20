import pytest
import time
from app.backtest.tick_backtest import TickBacktestEngine
from app.backtest.tick_metrics import TickMetricsCalculator
from app.backtest.walk_forward import WalkForwardValidator, TickMonteCarloSimulator

def generate_sample_ticks(count: int = 500) -> list:
    ticks = []
    now = time.time()
    for i in range(count):
        t = now - (count - i) * 0.1
        base_price = 2400.0 + (i * 0.05) if (i // 50) % 2 == 0 else 2400.0 + (50 * 0.05) - ((i % 50) * 0.05)
        bid = round(base_price, 3)
        ask = round(base_price + 0.25, 3)
        ticks.append({"symbol": "XAUUSD", "bid": bid, "ask": ask, "last": bid, "timestamp": t})
    return ticks

def test_tick_backtest_engine_run():
    ticks = generate_sample_ticks(400)
    engine = TickBacktestEngine(latency_ms=50.0, base_slippage_pips=0.1, commission_per_lot=7.0)
    metrics = engine.run_backtest(ticks)

    assert isinstance(metrics.total_trades, int)
    assert isinstance(metrics.net_profit, float)
    assert isinstance(metrics.win_rate, float)
    assert "regime_breakdown" in metrics.to_dict()

def test_walk_forward_validator():
    ticks = generate_sample_ticks(400)
    engine = TickBacktestEngine()
    wf_validator = WalkForwardValidator(engine=engine)
    report = wf_validator.run_walk_forward(ticks)

    assert report.total_windows == 3
    assert hasattr(report.train_metrics, "total_trades")
    assert hasattr(report.out_of_sample_metrics, "total_trades")
    assert isinstance(report.passed, bool)

def test_monte_carlo_simulator():
    sim = TickMonteCarloSimulator()
    sample_trades = [
        {"realized_pnl": 15.0, "volume": 0.05},
        {"realized_pnl": -10.0, "volume": 0.05},
        {"realized_pnl": 20.0, "volume": 0.05},
        {"realized_pnl": -8.0, "volume": 0.05},
        {"realized_pnl": 25.0, "volume": 0.05},
    ]
    res = sim.run_monte_carlo(sample_trades, iterations=100)
    assert res["iterations"] == 100
    assert "median_net_profit" in res
    assert "probability_of_ruin_percent" in res

def test_tick_strategy_is_substitutable():
    """V1: a different tick strategy plugs the same harness without forking it."""
    from app.scalper.signal import ScalpSignal

    calls = []

    class _StubStrategy:
        def generate_signal(self, features, spec=None, point_size=0.001, digits=3):
            calls.append(features.symbol)
            return ScalpSignal(
                signal_id="SIG_STUB", timestamp=features.timestamp,
                symbol=features.symbol, direction="NONE", status="REJECTED",
                confidence_score=0.0, entry_reference=features.bid,
                stop_reference=features.bid, target_reference=features.bid,
                spread=features.spread_pips, momentum=0.0, velocity=0.0,
                volatility=0.0, reasons=["stub"], expiry_time=features.timestamp + 10.0,
            )

    ticks = generate_sample_ticks(400)
    engine = TickBacktestEngine(scalp_strategy=_StubStrategy())
    metrics = engine.run_backtest(ticks)
    assert len(calls) > 0  # harness consulted the substitute, not the default
    assert metrics.total_trades == 0
    assert isinstance(metrics.net_profit, float)


def test_lookahead_and_safety_locks():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
