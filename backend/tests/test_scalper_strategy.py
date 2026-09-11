import pytest
import time
from app.scalper.tick_engine import TickBuffer, TickData
from app.scalper.features import FeatureEngine
from app.scalper.strategy import ScalpStrategyEngine

def test_feature_engine_extraction():
    buffer = TickBuffer(max_size=100)
    now = time.time()

    # Fill buffer with 20 bullish ticks
    for i in range(20):
        t = now - (20 - i) * 0.2
        p = 2400.0 + (i * 0.1)
        buffer.add_tick(TickData("XAUUSD", p, p + 0.02, p, 0.2, t))

    engine = FeatureEngine()
    feats = engine.extract_features(buffer, point_size=0.001, digits=3)

    assert feats is not None
    assert feats.symbol == "XAUUSD"
    assert feats.tick_velocity_5s > 0.0
    assert feats.momentum_5s > 0.0
    assert feats.bullish_tick_ratio > 0.5

def test_scalp_strategy_buy_signal():
    buffer = TickBuffer(max_size=100)
    now = time.time()

    for i in range(30):
        t = now - (30 - i) * 0.1
        p = 2400.0 + (i * 0.1)
        buffer.add_tick(TickData("XAUUSD", p, p + 0.02, p, 0.2, t))

    feats_engine = FeatureEngine()
    feats = feats_engine.extract_features(buffer, point_size=0.001, digits=3)

    strategy = ScalpStrategyEngine(max_allowed_spread=1.0, min_tick_velocity=1.0, min_imbalance_edge=0.5)
    sig = strategy.generate_signal(feats, point_size=0.001, digits=3)

    assert sig.status == "APPROVED"
    assert sig.direction == "BUY"
    assert sig.confidence_score > 0.5
    assert "bullish_tick_imbalance" in sig.reasons
    assert sig.signal_id.startswith("SIG_")

def test_scalp_strategy_spread_rejection():
    buffer = TickBuffer(max_size=100)
    now = time.time()

    # Ticks with wide spread (5.0 pips)
    for i in range(30):
        t = now - (30 - i) * 0.1
        p = 2400.0 + (i * 0.1)
        buffer.add_tick(TickData("XAUUSD", p, p + 0.5, p, 5.0, t))

    feats_engine = FeatureEngine()
    feats = feats_engine.extract_features(buffer, point_size=0.001, digits=3)

    strategy = ScalpStrategyEngine(max_allowed_spread=2.0)
    sig = strategy.generate_signal(feats, point_size=0.001, digits=3)

    assert sig.status == "REJECTED"
    assert any("Spread too high" in r for r in sig.reasons)
