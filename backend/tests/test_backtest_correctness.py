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

    class _FakeStrategy:
        """Test double implementing the StrategyProvider seam (dict in/out)."""

        def configure(self, config=None):
            pass

        def evaluate(self, inputs):
            return {"client_signal_id": "SIG_FAKE", "symbol": inputs.symbol,
                    "direction": "LONG", "entry_price": entry,
                    "stop_loss": sl, "take_profit": tp, "status": "APPROVED",
                    "setup_type": "FAKE", "confidence": 1.0,
                    "reasons": {}, "timestamp": "t"}

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


def test_fill_methodology_tp_no_slippage_sl_adverse():
    """N2-M2: TP fills exact, SL slips adversely, spread never alters fills."""
    engine, _ = _mini_backtest()
    assert len(engine.last_trades) == 1
    tp_trade = engine.last_trades[0]
    assert tp_trade.exit_reason == "TAKE_PROFIT"
    assert tp_trade.exit_price == 2401.0  # exact TP, zero slippage

    sl_engine = BacktestEngine(initial_balance=10000.0, slippage_pips=0.5, commission_per_lot=0.0)

    class _SLStrategy:
        def configure(self, config=None):
            pass

        def evaluate(self, inputs):
            return {"client_signal_id": "SIG_SL", "symbol": inputs.symbol,
                    "direction": "LONG", "entry_price": 2400.0,
                    "stop_loss": 2399.0, "take_profit": 2410.0,
                    "status": "APPROVED", "setup_type": "FAKE",
                    "confidence": 1.0, "reasons": {}, "timestamp": "t"}

    class _SLRisk:
        def evaluate_trade_risk(self, *a, **k):
            from app.risk.engine import RiskDecision
            return RiskDecision(True, None, 0.5, 10.0, 0.1, 2.0)

    sl_engine.strategy_engine = _SLStrategy()
    sl_engine.risk_engine = _SLRisk()
    candles = [{"timestamp": f"t{i}", "open": 2400.0, "high": 2400.0, "low": 2400.0,
                "close": 2400.0, "tick_volume": 1, "volume": 1, "spread": 0}
               for i in range(30)]
    candles.append({"timestamp": "tX", "open": 2399.0, "high": 2399.5, "low": 2398.0,
                    "close": 2398.5, "tick_volume": 1, "volume": 1, "spread": 0})
    sl_engine.run("XAUUSD", candles, point_size=0.01)
    assert len(sl_engine.last_trades) == 1
    sl_trade = sl_engine.last_trades[0]
    assert sl_trade.exit_reason == "STOP_LOSS"
    # Adverse slippage: 2399.0 - 0.5 * 0.01
    assert sl_trade.exit_price == pytest.approx(2398.995)


def test_spread_does_not_alter_fills():
    """N2-M2: spread_pips is risk-gating input only; fills are identical."""
    from app.backtest.engine import BacktestEngine as BE
    from app.risk.engine import RiskDecision

    _, r1 = _mini_backtest()
    assert r1.total_trades == 1
    # Re-run with a wide spread through a fresh engine with the same fakes.
    e2 = BE(initial_balance=10000.0, spread_pips=50.0, slippage_pips=0.0, commission_per_lot=7.0)

    class _FakeStrategy:
        def configure(self, config=None):
            pass

        def evaluate(self, inputs):
            return {"client_signal_id": "SIG_FAKE2", "symbol": inputs.symbol,
                    "direction": "LONG", "entry_price": 2400.0,
                    "stop_loss": 2399.0, "take_profit": 2401.0,
                    "status": "APPROVED", "setup_type": "FAKE",
                    "confidence": 1.0, "reasons": {}, "timestamp": "t"}

    class _FakeRisk:
        def evaluate_trade_risk(self, *a, **k):
            return RiskDecision(True, None, 0.5, 10.0, 0.1, 2.0)

    e2.strategy_engine = _FakeStrategy()
    e2.risk_engine = _FakeRisk()
    candles = [{"timestamp": f"t{i}", "open": 2400.0, "high": 2400.0, "low": 2400.0,
                "close": 2400.0, "tick_volume": 1, "volume": 1, "spread": 0}
               for i in range(30)]
    candles.append({"timestamp": "tX", "open": 2401.0, "high": 2402.0, "low": 2400.5,
                    "close": 2401.5, "tick_volume": 1, "volume": 1, "spread": 0})
    r2 = e2.run("XAUUSD", candles, point_size=0.01)
    assert r2.total_trades == r1.total_trades == 1
    assert r2.net_profit == r1.net_profit


def test_walk_forward_monte_carlo_reproducible():
    from app.backtest.walk_forward import TickMonteCarloSimulator
    sim = TickMonteCarloSimulator()
    trades = [{"realized_pnl": 100.0}, {"realized_pnl": -50.0}, {"realized_pnl": 20.0}]
    r1 = sim.run_monte_carlo(trades, iterations=100)
    r2 = sim.run_monte_carlo(trades, iterations=100)
    assert r1 == r2


def test_ruin_thresholds_are_named_and_distinct():
    """N2-M5: the two simulators define ruin differently, by name."""
    from app.backtest.monte_carlo import MONTE_CARLO_RUIN_THRESHOLD_PERCENT, MonteCarloSimulator
    from app.backtest.walk_forward import WALK_FORWARD_RUIN_THRESHOLD_PERCENT, TickMonteCarloSimulator
    assert MONTE_CARLO_RUIN_THRESHOLD_PERCENT == 50.0
    assert WALK_FORWARD_RUIN_THRESHOLD_PERCENT == 20.0
    assert MonteCarloSimulator().ruin_threshold_percent == 50.0
    import inspect
    sig = inspect.signature(TickMonteCarloSimulator.run_monte_carlo)
    assert sig.parameters["ruin_threshold_percent"].default == 20.0


def test_walk_forward_monte_carlo_seed_parameter():
    from app.backtest.walk_forward import TickMonteCarloSimulator
    sim = TickMonteCarloSimulator()
    trades = [{"realized_pnl": float(v)} for v in
              (100, -50, 20, -30, 80, -10, 45, -60, 25, -15, 90, -40)]
    assert sim.run_monte_carlo(trades, iterations=500, seed=1) == \
        sim.run_monte_carlo(trades, iterations=500, seed=1)
    assert sim.run_monte_carlo(trades, iterations=500, seed=1) != \
        sim.run_monte_carlo(trades, iterations=500, seed=2)
