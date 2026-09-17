"""M-2 tests: CostFilter expected values per instrument (C-01 numeric contract).

The C-01 change (spec.contract_size instead of the x100 literal) is
behavior-changing for FX (~x1000) and indices (~x100). These tests lock the
intended corrected values for XAUUSD, EURUSD, and NAS100.
"""
import pytest

from app.intelligence.cost_analyzer import CostFilter
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification


def _features(spread_pips=0.2, price_velocity=0.0):
    return ScalperFeatures(
        symbol="X", timestamp=1.0, bid=1.0, ask=1.0, spread_pips=spread_pips,
        tick_velocity_5s=1.0, tick_velocity_10s=1.0, price_velocity=price_velocity,
        price_acceleration=0.0, momentum_5s=0.0, normalized_momentum=0.0,
        bullish_tick_ratio=0.5, bearish_tick_ratio=0.5, imbalance_edge=0.0,
        volatility_50t=0.1, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False,
    )


def test_cost_xauusd_expected_values():
    # contract 100, pip 0.1, vol 0.05: comm $0.35 -> 0.7 pips;
    # total 0.2 + 0.7 + 0.1 = 1.0 pips = $0.50; edge 4.5 pips = $2.25.
    f = CostFilter()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    res = f.evaluate_cost(_features(), spec, target_distance_pips=4.5, volume=0.05)
    assert res.total_transaction_cost_dollars == pytest.approx(0.50)
    assert res.expected_edge_dollars == pytest.approx(2.25)
    assert res.cost_to_target_ratio == pytest.approx(0.22)  # round(1.0/4.5, 2)
    assert res.passed is True


def test_cost_eurusd_expected_values():
    # contract 100000, pip 0.0001: $/pip/lot is still $10, so the corrected
    # FX numbers match gold here (old x100 math gave $0.005 instead of $0.50).
    f = CostFilter()
    spec = InstrumentSpecification.get_default_spec("EURUSD")
    res = f.evaluate_cost(_features(), spec, target_distance_pips=4.5, volume=0.05)
    assert res.total_transaction_cost_dollars == pytest.approx(0.50)
    assert res.expected_edge_dollars == pytest.approx(2.25)
    assert res.passed is True


def test_cost_nas100_expected_values():
    # contract 1, pip 1.0: comm $0.35 -> 7.0 pips; total 7.3 pips = $0.365;
    # edge 4.5 pips = $0.225; target < 1.5x cost -> rejected.
    f = CostFilter()
    spec = InstrumentSpecification.get_default_spec("NAS100")
    assert spec.contract_size == 1.0
    res = f.evaluate_cost(_features(), spec, target_distance_pips=4.5, volume=0.05)
    assert res.total_transaction_cost_dollars == pytest.approx(0.36)  # round(7.3*0.05, 2)
    assert res.expected_edge_dollars == pytest.approx(0.23)  # round(4.5*1*1*0.05, 2)
    assert res.passed is False


def test_cost_scales_with_volume():
    f = CostFilter()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    small = f.evaluate_cost(_features(), spec, volume=0.05)
    big = f.evaluate_cost(_features(), spec, volume=0.10)
    assert big.total_transaction_cost_dollars == pytest.approx(2 * small.total_transaction_cost_dollars)
