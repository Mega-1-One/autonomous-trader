"""C-02 tests: backtest trades access (last_trades) and determinism.

(/run contract, Monte Carlo responsiveness, and MC endpoint shape live in
test_backtest_contract.py and test_monte_carlo_responsiveness.py.)
"""
import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.metrics import BacktestTradeRecord


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
