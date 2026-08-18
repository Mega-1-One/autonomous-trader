import pytest
from app.context.timeframe_engine import Candle
from app.swing.swing_engine import SwingEngine
from app.scalper.instrument import InstrumentSpecification

def test_swing_engine_top_down_alignment():
    engine = SwingEngine()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    # Generate bullish 4h, 1h, 15m candles
    c4h = [Candle("XAUUSD", "4h", 2400.0, 2410.0, 2390.0, 2405.0 + i*0.5, 100, float(i*14400)) for i in range(15)]
    c1h = [Candle("XAUUSD", "1h", 2400.0, 2410.0, 2390.0, 2405.0 + i*0.5, 100, float(i*3600)) for i in range(15)]
    c15m = [Candle("XAUUSD", "15m", 2400.0, 2410.0, 2390.0, 2405.0 + i*0.5, 100, float(i*900)) for i in range(15)]

    res = engine.evaluate_swing_setup(c4h, c1h, c15m, spec, current_price=2412.0)
    assert res.approved is True
    assert res.direction == "BUY"
    assert res.take_profit > res.entry_price

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
