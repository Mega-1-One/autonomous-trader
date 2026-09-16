"""C-02 tests: backtest trades access, Monte Carlo over real trades, determinism."""
import json
import os

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import BacktestTradeRecord
from app.backtest.monte_carlo import MonteCarloSimulator

BASELINE_RUN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "baseline", "api_post_api_backtest_run.json"
)


def _mini_backtest(symbol="XAUUSD", point_size=0.01, entry=2400.0, sl=2399.0, tp=2401.0):
    """Engine with injected always-approve strategy/risk (deterministic trades)."""
    from app.risk.engine import RiskDecision

    class _FakeSignal:
        status = "APPROVED"
        direction = "LONG"
        entry_price = entry
        stop_loss = sl
        take_profit = tp
        def to_dict(self):
            return {"entry_price": entry, "stop_loss": sl, "take_profit": tp,
                    "direction": "LONG", "symbol": symbol}

    class _FakeStrategy:
        def evaluate_setup(self, *a, **k):
            return _FakeSignal()

    class _FakeRisk:
        def evaluate_trade_risk(self, *a, **k):
            return RiskDecision(True, None, 0.5, 10.0, 0.1, 2.0)

    engine = BacktestEngine(initial_balance=10000.0, slippage_pips=0.0, commission_per_lot=7.0)
    engine.strategy_engine = _FakeStrategy()
    engine.risk_engine = _FakeRisk()
    candles = [{"timestamp": f"t{i}", "open": entry, "high": entry, "low": entry,
                "close": entry, "tick_volume": 1, "volume": 1, "spread": 0}
               for i in range(30)]
    candles.append({"timestamp": "tX", "open": tp, "high": tp + 1.0, "low": entry,
                    "close": tp + 0.5, "tick_volume": 1, "volume": 1, "spread": 0})
    report = engine.run(symbol, candles, point_size=point_size)
    return engine, report


def test_last_trades_populated_without_changing_report_shape():
    engine, report = _mini_backtest()
    assert report.total_trades == 1
    # ADR-5b: trades accessible via last_trades; report carries no trade list
    assert len(engine.last_trades) == 1
    assert isinstance(engine.last_trades[0], BacktestTradeRecord)
    assert not hasattr(report, "trades")
    assert "trades" not in report.to_dict()


def test_trade_ids_deterministic():
    e1, _ = _mini_backtest()
    e2, _ = _mini_backtest()
    assert [t.trade_id for t in e1.last_trades] == [t.trade_id for t in e2.last_trades]
    assert e1.last_trades[0].trade_id == "BT_XAUUSD_25_LONG"


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


def test_walk_forward_monte_carlo_reproducible():
    from app.backtest.walk_forward import TickMonteCarloSimulator
    sim = TickMonteCarloSimulator()
    trades = [{"realized_pnl": 100.0}, {"realized_pnl": -50.0}, {"realized_pnl": 20.0}]
    r1 = sim.run_monte_carlo(trades, iterations=100)
    r2 = sim.run_monte_carlo(trades, iterations=100)
    assert r1 == r2


def test_walk_forward_monte_carlo_seed_parameter():
    from app.backtest.walk_forward import TickMonteCarloSimulator
    sim = TickMonteCarloSimulator()
    trades = [{"realized_pnl": float(v)} for v in
              (100, -50, 20, -30, 80, -10, 45, -60, 25, -15, 90, -40)]
    assert sim.run_monte_carlo(trades, iterations=500, seed=1) == \
        sim.run_monte_carlo(trades, iterations=500, seed=1)
    assert sim.run_monte_carlo(trades, iterations=500, seed=1) != \
        sim.run_monte_carlo(trades, iterations=500, seed=2)


@pytest.mark.asyncio
async def test_backtest_run_contract_preserved(async_client):
    """/api/backtest/run JSON keeps the baseline shape/keys (P-03 fix changes nothing here)."""
    res = await async_client.post("/api/backtest/run", json={
        "symbol": "XAUUSD", "timeframe": "M5", "candle_count": 200, "initial_balance": 10000,
    })
    assert res.status_code == 200
    data = res.json()
    with open(BASELINE_RUN_FILE, encoding="utf-8") as f:
        baseline = json.load(f)["result"]["json"]
    assert set(data.keys()) == set(baseline.keys())
    assert set(data["report"].keys()) == set(baseline["report"].keys())
    # Metric values are deterministic on mock data across runs (candle
    # timestamps are wall-clock; compare everything but timestamps).
    res2 = await async_client.post("/api/backtest/run", json={
        "symbol": "XAUUSD", "timeframe": "M5", "candle_count": 200, "initial_balance": 10000,
    })
    data2 = res2.json()
    assert data2["symbol"] == data["symbol"] == "XAUUSD"
    rep1 = {k: v for k, v in data["report"].items() if k != "equity_curve"}
    rep2 = {k: v for k, v in data2["report"].items() if k != "equity_curve"}
    assert rep1 == rep2
    eq1 = [(e["equity"], e["drawdown_percent"]) for e in data["report"]["equity_curve"]]
    eq2 = [(e["equity"], e["drawdown_percent"]) for e in data2["report"]["equity_curve"]]
    assert eq1 == eq2


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
