"""B-02 Step 1 — characterization tests locking CURRENT numeric outputs.

These tests define the before-state of instrument/pip math. They are locked
BEFORE any reconciliation edit. Where B-02 deliberately changes behavior
(mock-gold spread display), the specific test is updated in the same commit as
the change, with the documented reason (see ADR-4 / plan §2.6 #6).
"""
import pytest

from app.runner import calculate_spread_in_pips
from app.strategy.engine import StrategyEngine
from app.data.mt5_mock import MockMT5Adapter, DEFAULT_SYMBOL_SPECS
from app.backtest.engine import BacktestEngine
from app.strategy.engine import TradeSignal


# ---------------------------------------------------------------------------
# runner.calculate_spread_in_pips — current digits-based rules
# ---------------------------------------------------------------------------

def test_spread_gold_digits3_rule():
    # digits=3 gold: raw diff 0.260 / (point 0.001 * 100) = 2.6 pips
    assert calculate_spread_in_pips(2400.000, 2400.260, digits=3, point_size=0.001) == 2.6

def test_spread_forex_digits5_rule():
    # digits=5 FX: raw diff 0.00010 / (point 0.00001 * 10) = 1.0 pip
    assert calculate_spread_in_pips(1.08500, 1.08510, digits=5, point_size=0.00001) == 1.0

def test_spread_other_digits_falls_back_to_point():
    # Legacy symbol-less callers keep the exact prior digits rule
    # (digits=2: raw diff 0.05 / point 0.01 = 5.0, point-based).
    assert calculate_spread_in_pips(2400.00, 2400.05, digits=2, point_size=0.01) == 5.0


# ---------------------------------------------------------------------------
# B-02 Step 2 — canonical pip-size semantics (intended change, ADR-4 / §2.6 #6)
#
# Documented deliberate change: symbol-resolved spread now divides by the
# canonical pip_size instead of the digits rule. For real 3-digit gold and
# 5-digit FX quotes the numbers are identical (spec pip == legacy rule); for
# the mock's digits=2 gold environment the displayed spread changes scale
# (0.05 diff: was 5.0 point-based, now 0.5 pip-based). The spread risk gate is
# disabled by default, so there is no trading-behavior change.
# ---------------------------------------------------------------------------

def test_spread_symbol_resolved_gold_canonical_pip():
    from app.runner import calculate_spread_in_pips as _f  # migrated symbol-aware wrapper
    # digits=3 real gold quote: identical to legacy rule (0.260 / 0.1 = 2.6)
    assert _f(2400.000, 2400.260, digits=3, point_size=0.001, symbol="XAUUSD") == 2.6
    # digits=2 mock gold quote: now canonical 0.1-pip scale (was point-based 5.0)
    assert _f(2400.00, 2400.05, digits=2, point_size=0.01, symbol="XAUUSD") == 0.5

def test_spread_symbol_resolved_forex_canonical_pip():
    from app.runner import calculate_spread_in_pips as _f
    assert _f(1.08500, 1.08510, digits=5, point_size=0.00001, symbol="EURUSD") == 1.0

def test_tick_engine_spread_uses_canonical_pip_size():
    from app.scalper.tick_engine import TickEngine
    import time as _time
    engine = TickEngine(max_stale_seconds=5.0)
    now = _time.time()
    tick = engine.process_tick("XAUUSD", bid=2400.00, ask=2400.05,
                               timestamp=now, point_size=0.01, digits=2)
    # mock digits=2 gold quote: canonical 0.1-pip scale -> 0.5 pips (was 5.0)
    assert tick.spread_pips == 0.5
    tick_fx = engine.process_tick("EURUSD", bid=1.08500, ask=1.08510,
                                  timestamp=now, point_size=0.00001, digits=5)
    assert tick_fx.spread_pips == 1.0


# ---------------------------------------------------------------------------
# core/pricing.py primitives (new, ADR-4)
# ---------------------------------------------------------------------------

def test_pricing_pip_size_precedence():
    from app.core.pricing import pip_size
    assert pip_size("XAUUSD") == 0.1
    assert pip_size("XAUUSDm") == 0.1          # trailing-suffix normalization
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01
    assert pip_size("NAS100") == 1.0
    # unknown symbol -> digits-derived fallback from point_size
    assert pip_size("ZZZUSD", point_size=0.00001) == 0.0001

def test_pricing_pnl_contract_precedence():
    from app.core.pricing import pnl
    # Spec contract (EURUSD 100000): 0.001 diff = 10 pips * $10/pip/lot * 0.5 lot
    assert pnl(0.001, 0.5, "EURUSD") == pytest.approx(50.0)
    # Broker symbol_info overrides the static spec
    assert pnl(1.0, 1.0, "XAUUSD", {"contract_size": 200.0}) == 200.0
    # Spec contract for gold
    assert pnl(1.0, 1.0, "XAUUSD") == 100.0

def test_pricing_pips_to_price():
    from app.core.pricing import pips_to_price
    assert pips_to_price(3.0, "XAUUSD") == pytest.approx(0.3)
    assert pips_to_price(5.0, "EURUSD") == pytest.approx(0.0005)

def test_get_default_spec_trailing_m_only():
    from app.scalper.instrument import InstrumentSpecification
    # trailing m suffix stripped
    assert InstrumentSpecification.get_default_spec("XAUUSDm").symbol == "XAUUSDm"
    gold = InstrumentSpecification.get_default_spec("XAUUSDm")
    assert gold.pip_size == 0.1
    # interior M preserved: M100 resolves by NAS branch ("M100".upper() -> "M100" keeps M)
    spec = InstrumentSpecification.get_default_spec("M100")
    assert spec.symbol == "M100"
    # digits-2 mock environment untouched
    from app.data.mt5_mock import DEFAULT_SYMBOL_SPECS
    assert DEFAULT_SYMBOL_SPECS["XAUUSD"]["digits"] == 2


# ---------------------------------------------------------------------------
# strategy/engine._scalp_levels — spec-driven pip math (trading level)
# ---------------------------------------------------------------------------

@pytest.fixture
def strategy_engine():
    return StrategyEngine(config={
        "entry": {"minimum_rr": 1.5, "take_profit_pips": 5.0, "stop_loss_pips": 3.0},
        "timeframes": {"ltf": "M1"},
        "sessions": {},
        "market_structure": {},
    })

def test_scalp_levels_xauusd(strategy_engine):
    # gold spec: pip_size 0.1, digits rule: point 0.001 < 0.01 -> digits 5
    sl, tp, rr = strategy_engine._scalp_levels("XAUUSD", "LONG", 2400.0, point_size=0.001)
    assert sl == 2399.7   # 3 pips * 0.1
    assert tp == 2400.5   # 5 pips * 0.1
    assert rr == 1.67

def test_scalp_levels_eurusd(strategy_engine):
    # FX spec: pip_size 0.0001, digits 5
    sl, tp, rr = strategy_engine._scalp_levels("EURUSD", "LONG", 1.08500, point_size=0.00001)
    assert sl == 1.0847
    assert tp == 1.0855
    assert rr == 1.67

def test_scalp_levels_short(strategy_engine):
    sl, tp, rr = strategy_engine._scalp_levels("XAUUSD", "SHORT", 2400.0, point_size=0.001)
    assert sl == 2400.3
    assert tp == 2399.5


# ---------------------------------------------------------------------------
# Mock adapter environment (spec values unchanged by B-02)
# ---------------------------------------------------------------------------

def test_mock_gold_spec_is_digits2_point01():
    spec = DEFAULT_SYMBOL_SPECS["XAUUSD"]
    assert spec["digits"] == 2
    assert spec["point_size"] == 0.01
    assert spec["contract_size"] == 100.0

def test_mock_adapter_tick_spread_path():
    adapter = MockMT5Adapter()
    adapter.connect()
    tick = adapter.get_ticks("XAUUSD", count=1)[0]
    # mock tick: ask = bid + point*10 = bid + 0.1
    assert tick["ask"] - tick["bid"] == pytest.approx(0.1, abs=1e-9)

def test_mock_get_symbol_info_has_no_bid_key():
    adapter = MockMT5Adapter()
    adapter.connect()
    info = adapter.get_symbol_info("XAUUSD")
    assert "bid" not in info  # N-06 precondition: 2400.0 fallback path


# ---------------------------------------------------------------------------
# backtest/engine contract heuristic (current point-size guess)
# ---------------------------------------------------------------------------

class _FakeStrategy:
    """Test double implementing the StrategyProvider seam (dict in/out)."""

    def __init__(self, entry, sl, tp, direction="LONG"):
        self.entry, self.sl, self.tp, self.direction = entry, sl, tp, direction

    def configure(self, config=None):
        pass

    def evaluate(self, inputs):
        return {"client_signal_id": "SIG_CHAR", "symbol": inputs.symbol,
                "direction": self.direction, "entry_price": self.entry,
                "stop_loss": self.sl, "take_profit": self.tp,
                "status": "APPROVED", "setup_type": "FAKE",
                "confidence": 1.0, "reasons": {}, "timestamp": "t"}


class _FakeRisk:
    def evaluate_trade_risk(self, *args, **kwargs):
        from app.risk.engine import RiskDecision
        return RiskDecision(approved=True, rejection_reason=None,
                            calculated_volume=0.5, monetary_risk=10.0,
                            risk_percent=0.1, effective_rr=2.0)


def _run_mini_backtest(point_size, entry, sl, tp, exit_candles, symbol="XAUUSD"):
    """Backtest with injected strategy/risk so the contract heuristic is exercised deterministically."""
    engine = BacktestEngine(initial_balance=10000.0, slippage_pips=0.0, commission_per_lot=7.0)
    engine.strategy_engine = _FakeStrategy(entry, sl, tp)
    engine.risk_engine = _FakeRisk()
    candles = [{"timestamp": f"t{i}", "open": entry, "high": entry, "low": entry, "close": entry,
                "tick_volume": 1, "volume": 1, "spread": 0} for i in range(30)]
    candles += exit_candles
    return engine.run(symbol, candles, point_size=point_size)


def test_backtest_contract_heuristic_xau_shaped_point():
    # point_size 0.01 -> contract 100.0 (current heuristic). LONG TP hit.
    report = _run_mini_backtest(
        point_size=0.01, entry=2400.0, sl=2399.0, tp=2401.0,
        exit_candles=[{"timestamp": "tX", "open": 2401.0, "high": 2402.0, "low": 2400.5,
                       "close": 2401.5, "tick_volume": 1, "volume": 1, "spread": 0}],
    )
    assert report.total_trades == 1
    # pnl = diff 1.0 * contract 100 * vol 0.5 - commission 3.5
    # (report has no trades list pre-C-02 — locked via net_profit)
    assert report.net_profit == 46.5

def test_backtest_contract_heuristic_fx_shaped_point():
    # C-01 intended change (register #5): the old heuristic was symbol-blind and
    # guessed contract 100000 purely from point_size; the spec-based rule
    # resolves via the symbol. For a real FX symbol (EURUSD) the corrected
    # contract is still 100000, so the locked value holds.
    report = _run_mini_backtest(
        point_size=0.00001, entry=1.08500, sl=1.08400, tp=1.08700,
        exit_candles=[{"timestamp": "tX", "open": 1.08700, "high": 1.08750, "low": 1.08520,
                       "close": 1.08720, "tick_volume": 1, "volume": 1, "spread": 0}],
        symbol="EURUSD",
    )
    assert report.total_trades == 1
    # pnl = diff 0.002 * contract 100000 * vol 0.5 - commission 3.5
    assert report.net_profit == 96.5


def test_backtest_contract_now_resolved_by_symbol_not_point_size():
    # Same FX-shaped point size, but a gold symbol: the old heuristic used
    # contract 100000 (net 96.5); the corrected spec rule uses 100
    # (diff 0.002 * 100 * 0.5 - 3.5 = -3.4). Intended correction (register #5).
    report = _run_mini_backtest(
        point_size=0.00001, entry=1.08500, sl=1.08400, tp=1.08700,
        exit_candles=[{"timestamp": "tX", "open": 1.08700, "high": 1.08750, "low": 1.08520,
                       "close": 1.08720, "tick_volume": 1, "volume": 1, "spread": 0}],
        symbol="XAUUSD",
    )
    assert report.total_trades == 1
    assert report.net_profit == -3.4
