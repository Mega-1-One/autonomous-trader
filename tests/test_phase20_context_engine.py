import pytest
from app.context.timeframe_engine import TimeframeEngine
from app.context.bias_engine import BiasEngine
from app.context.setup_engine import SetupEngine
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

def test_timeframe_engine_candle_aggregation():
    tf_engine = TimeframeEngine()
    for i in range(100):
        tf_engine.process_tick("XAUUSD", 2400.0 + i * 0.1, 100.0 + i * 2)

    c1m = tf_engine.get_candles("1m")
    c5m = tf_engine.get_candles("5m")
    assert len(c1m) > 0
    assert len(c5m) > 0

def test_bias_and_setup_engine():
    tf_engine = TimeframeEngine()
    # Generate bullish candles for all timeframes
    for i in range(300):
        tf_engine.process_tick("XAUUSD", 2400.0 + i * 0.5, 100.0 + i * 10)

    tf_candles = {tf: tf_engine.get_candles(tf) for tf in ["4h", "1h", "15m", "5m"]}
    bias_engine = BiasEngine()
    bias_res = bias_engine.evaluate_bias(tf_candles)

    assert "BULLISH" in bias_res.bias

    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    feats = ScalperFeatures(
        symbol="XAUUSD", timestamp=4000.0, bid=2550.0, ask=2550.2, spread_pips=0.2,
        tick_velocity_5s=5.0, tick_velocity_10s=5.0, price_velocity=0.1, price_acceleration=0.01,
        momentum_5s=0.5, normalized_momentum=2.5, bullish_tick_ratio=0.60, bearish_tick_ratio=0.40,
        imbalance_edge=0.10, volatility_50t=0.2, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False
    )


    setup_engine = SetupEngine()
    setup_res = setup_engine.evaluate_setup(bias_res, feats, spec)

    assert setup_res.direction == "BUY"
    assert setup_res.tick_timing_confirmed is True

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
