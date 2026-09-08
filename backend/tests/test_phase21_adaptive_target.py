import pytest
from app.scalper.adaptive_exit_v2 import AdaptiveExitEngineV2, MinimumViableTargetEngine
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

def test_minimum_viable_target_engine():
    engine = MinimumViableTargetEngine()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    feats = ScalperFeatures(
        symbol="XAUUSD", timestamp=100.0, bid=2400.0, ask=2400.2, spread_pips=0.2,
        tick_velocity_5s=5.0, tick_velocity_10s=5.0, price_velocity=0.1, price_acceleration=0.01,
        momentum_5s=0.5, normalized_momentum=2.5, bullish_tick_ratio=0.60, bearish_tick_ratio=0.40,
        imbalance_edge=0.10, volatility_50t=0.2, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False
    )

    min_target = engine.calculate_minimum_target(feats, spec, total_cost_dollars=0.50, volume=0.05)
    assert min_target >= 3.0

def test_adaptive_exit_v2():
    exit_v2 = AdaptiveExitEngineV2()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    feats = ScalperFeatures(
        symbol="XAUUSD", timestamp=100.0, bid=2400.0, ask=2400.2, spread_pips=0.2,
        tick_velocity_5s=5.0, tick_velocity_10s=5.0, price_velocity=0.1, price_acceleration=0.01,
        momentum_5s=0.5, normalized_momentum=2.5, bullish_tick_ratio=0.60, bearish_tick_ratio=0.40,
        imbalance_edge=0.10, volatility_50t=0.2, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False
    )

    levels = exit_v2.calculate_exit_levels(feats, spec, direction="BUY", atr_multiple_target=2.0)
    assert levels.take_profit > levels.entry_price
    assert levels.stop_loss < levels.entry_price
    assert levels.cost_ratio_percent < 100.0

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
