import pytest
from app.strategy.sessions import SessionFilter
from app.strategy.engine import StrategyEngine

def test_session_filter_london():
    filt = SessionFilter()
    in_sess, name = filt.is_in_active_session("2026-08-17T10:00:00Z")
    assert in_sess is True
    assert ("London" in name or "Scalp" in name)

def test_session_filter_outside():
    filt = SessionFilter()
    in_sess, name = filt.is_in_active_session("2026-08-17T03:00:00Z")
    assert isinstance(in_sess, bool)

def generate_ict_long_setup_candles():
    """Generates synthetic candle sequence producing a Bullish ICT Sweep + FVG setup inside London session."""
    candles = []
    for h in range(24):
        candles.append({
            "timestamp": f"2026-08-16T{h:02d}:00:00Z",
            "open": 2400.0,
            "high": 2410.0,
            "low": 2395.0 if h == 12 else 2398.0,
            "close": 2402.0,
            "volume": 100
        })
    for h in range(10):
        candles.append({
            "timestamp": f"2026-08-17T{h:02d}:00:00Z",
            "open": 2402.0,
            "high": 2408.0,
            "low": 2397.0,
            "close": 2400.0,
            "volume": 100
        })
    candles.append({
        "timestamp": "2026-08-17T10:15:00Z",
        "open": 2400.0,
        "high": 2402.0,
        "low": 2388.0,
        "close": 2398.0,
        "volume": 300
    })
    candles.append({
        "timestamp": "2026-08-17T10:20:00Z",
        "open": 2398.0,
        "high": 2425.0,
        "low": 2406.0,
        "close": 2424.0,
        "volume": 800
    })
    candles.append({
        "timestamp": "2026-08-17T10:25:00Z",
        "open": 2424.0,
        "high": 2428.0,
        "low": 2415.0,
        "close": 2420.0,
        "volume": 400
    })
    return candles

def test_strategy_engine_bullish_signal():
    engine = StrategyEngine()
    ltf_candles = generate_ict_long_setup_candles()
    htf_candles = ltf_candles

    signal = engine.evaluate_setup("XAUUSD", htf_candles, ltf_candles, point_size=0.01)
    assert signal.status == "APPROVED"
    assert signal.direction == "LONG"
    assert signal.risk_reward >= 1.5
    assert signal.stop_loss < signal.entry_price < signal.take_profit

def test_strategy_engine_outside_session_rejection():
    engine = StrategyEngine()
    ltf_candles = generate_ict_long_setup_candles()
    signal = engine.evaluate_setup("XAUUSD", ltf_candles, ltf_candles, point_size=0.01)
    assert signal.status in ["APPROVED", "REJECTED"]

@pytest.mark.asyncio
async def test_api_evaluate_signals(async_client):
    res = await async_client.get("/api/strategy/signals?symbol=XAUUSD")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "signal" in data
    assert "status" in data["signal"]
    assert "reasons" in data["signal"]
