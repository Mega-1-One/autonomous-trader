"""D-02: Monte Carlo responsiveness + determinism (P-03/C-02)."""
import pytest

from app.backtest.metrics import BacktestTradeRecord
from app.backtest.monte_carlo import MonteCarloSimulator
from tests.test_backtest_correctness import _mini_backtest


def test_monte_carlo_over_real_trades_is_nonzero_and_deterministic():
    engine, _ = _mini_backtest()
    sim = MonteCarloSimulator(iterations=50)
    r1 = sim.run_simulation(10000.0, engine.last_trades).to_dict()
    r2 = sim.run_simulation(10000.0, engine.last_trades).to_dict()
    assert r1 == r2  # seeded (default_rng 42) -> reproducible
    assert r1["median_net_profit"] != 0.0


def test_monte_carlo_responds_to_trade_content():
    win = [BacktestTradeRecord("W", "X", "LONG", 1, 2, 0, 3, 0.5, 100.0, 2.0, "a", "b", "TAKE_PROFIT")]
    loss = [BacktestTradeRecord("L", "X", "LONG", 1, 0, 0, 3, 0.5, -5000.0, -1.0, "a", "b", "STOP_LOSS")]
    sim = MonteCarloSimulator(iterations=50)
    r_win = sim.run_simulation(10000.0, win).to_dict()
    r_loss = sim.run_simulation(10000.0, loss).to_dict()
    assert r_win["median_net_profit"] > 0
    assert r_loss["probability_of_ruin_percent"] > r_win["probability_of_ruin_percent"]


@pytest.mark.asyncio
async def test_monte_carlo_endpoint_uses_real_trades(async_client):
    """Endpoint passes engine.last_trades (P-03): shape preserved, still 200 OK."""
    res = await async_client.post("/api/backtest/monte-carlo", json={
        "symbol": "XAUUSD", "timeframe": "M5", "candle_count": 200, "initial_balance": 10000,
    })
    assert res.status_code == 200
    data = res.json()
    assert "simulation" in data
    sim = data["simulation"]
    assert set(sim.keys()) == {
        "iterations", "initial_balance", "probability_of_ruin_percent",
        "median_net_profit", "p95_net_profit", "p5_net_profit",
        "median_max_drawdown_percent", "p95_max_drawdown_percent",
        "expected_losing_streak", "drawdown_distribution",
    }
