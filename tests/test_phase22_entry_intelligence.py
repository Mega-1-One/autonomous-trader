import pytest
from app.context.timeframe_engine import TimeframeEngine, Candle
from app.context.bias_engine import BiasEngine, TopDownBiasResult
from app.context.price_location import PriceLocationEngine
from app.context.setup_classifier import SetupClassifier
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

def test_price_location_engine():
    loc_engine = PriceLocationEngine()
    candles = [Candle("XAUUSD", "15m", 2400.0, 2410.0, 2390.0, 2405.0, 100, float(i)) for i in range(20)]

    loc_premium = loc_engine.evaluate_location(candles, current_price=2408.0)
    assert loc_premium.location == "PREMIUM"

    loc_discount = loc_engine.evaluate_location(candles, current_price=2392.0)
    assert loc_discount.location == "DISCOUNT"

def test_setup_classifier():
    classifier = SetupClassifier()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    bias_res = TopDownBiasResult("STRONG_BULLISH", 1.0, {"4h": "BUY"}, ["Bullish"])

    loc_engine = PriceLocationEngine()
    candles = [Candle("XAUUSD", "15m", 2400.0, 2410.0, 2390.0, 2405.0, 100, float(i)) for i in range(20)]
    loc_res = loc_engine.evaluate_location(candles, current_price=2392.0)

    feats = ScalperFeatures(
        symbol="XAUUSD", timestamp=100.0, bid=2392.0, ask=2392.2, spread_pips=0.2,
        tick_velocity_5s=5.0, tick_velocity_10s=5.0, price_velocity=0.1, price_acceleration=0.01,
        momentum_5s=0.5, normalized_momentum=2.5, bullish_tick_ratio=0.60, bearish_tick_ratio=0.40,
        imbalance_edge=0.10, volatility_50t=0.2, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False
    )

    setup_res = classifier.classify_setup(bias_res, loc_res, feats, spec)
    assert setup_res.setup_type == "TREND_CONTINUATION"
    assert setup_res.direction == "BUY"
    assert setup_res.approved is True

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
