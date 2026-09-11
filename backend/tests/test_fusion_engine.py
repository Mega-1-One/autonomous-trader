import pytest
import time

from app.scalper.tick_engine import TickBuffer, TickData
from app.scalper.features import FeatureEngine
from app.scalper.strategy import ScalpStrategyEngine
from app.regime.engine import MarketRegimeEngine, MarketRegime
from app.scalper.selector import StrategySelector
from app.fusion.engine import SignalFusionEngine

def test_regime_engine_classification():
    buffer = TickBuffer(max_size=100)
    now = time.time()

    for i in range(20):
        p = 2400.0 + (i * 0.1)
        buffer.add_tick(TickData("XAUUSD", p, p + 0.02, p, 0.2, now - (20 - i) * 0.1))

    feats_engine = FeatureEngine()
    feats = feats_engine.extract_features(buffer)

    regime_engine = MarketRegimeEngine()
    state = regime_engine.evaluate_regime(feats)

    assert state.allow_trading is True
    assert state.regime in [MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT]

def test_regime_event_lockout():
    buffer = TickBuffer(max_size=100)
    now = time.time()
    for i in range(20):
        buffer.add_tick(TickData("XAUUSD", 2400.0, 2400.5, 2400.0, 0.5, now - (20 - i) * 0.1))

    feats_engine = FeatureEngine()
    feats = feats_engine.extract_features(buffer)

    regime_engine = MarketRegimeEngine()
    state = regime_engine.evaluate_regime(feats, event_lockout=True)

    assert state.allow_trading is False
    assert state.regime == MarketRegime.HIGH_RISK_EVENT

def test_signal_fusion_conflict_detection():
    buffer = TickBuffer(max_size=100)
    now = time.time()

    for i in range(20):
        p = 2400.0 + (i * 0.1)
        buffer.add_tick(TickData("XAUUSD", p, p + 0.02, p, 0.2, now - (20 - i) * 0.1))

    feats_engine = FeatureEngine()
    feats = feats_engine.extract_features(buffer)

    strategy_engine = ScalpStrategyEngine(max_allowed_spread=1.0)
    signal = strategy_engine.generate_signal(feats)

    fusion_engine = SignalFusionEngine()
    # Force a conflicting regime state (TRENDING_DOWN) for a BUY signal
    from app.regime.engine import RegimeState
    conflict_state = RegimeState(regime=MarketRegime.TRENDING_DOWN, confidence=0.9, allow_trading=True, reasons=[])

    fused = fusion_engine.evaluate_opportunity(signal, conflict_state)
    assert fused.approved is False
    assert fused.opportunity_score == 0.0
    assert "SIGNAL CONFLICT" in fused.reasons[0]
