import pytest
from app.strategy.sessions import SessionFilter
from app.strategy.engine import StrategyEngine

def test_session_filter_london():
    filt = SessionFilter()
    # 10:00 UTC is inside London (07:00-16:00)
    in_sess, name = filt.is_in_active_session("2026-08-17T10:00:00Z")
    assert in_sess is True
    assert "London" in name

def test_session_filter_outside():
    filt = SessionFilter()
    # 03:00 UTC is outside London and NY
    in_sess, name = filt.is_in_active_session("2026-08-17T03:00:00Z")
    assert in_sess is False

def generate_ict_long_setup_candles():
    """Generates synthetic candle sequence producing a Bullish ICT Sweep + FVG setup inside London session."""
    candles = []
    # 1. Previous Day Candles (2026-08-16) establishing PDL at 2395.0
    for h in range(24):
        candles.append({
            "timestamp": f"2026-08-16T{h:02d}:00:00Z",
            "open": 2400.0,
            "high": 2410.0,
            "low": 2395.0 if h == 12 else 2398.0, # PDL = 2395.0
            "close": 2402.0,
            "volume": 100
        })

    # 2. Current Day Candles (2026-08-17) before sweep
    for h in range(10):
        candles.append({
            "timestamp": f"2026-08-17T{h:02d}:00:00Z",
            "open": 2402.0,
            "high": 2408.0,
            "low": 2397.0,
            "close": 2400.0,
            "volume": 100
        })

    # 3. Sell-side sweep candle inside London session (10:15 UTC): sweeps below PDL (2395.0) down to 2388.0 and closes at 2398.0
    candles.append({
        "timestamp": "2026-08-17T10:15:00Z",
        "open": 2400.0,
        "high": 2402.0,
        "low": 2388.0,
        "close": 2398.0,
        "volume": 300
    })

    # 4. Big Bullish Impulse Candle (10:20 UTC) creating Bullish FVG (low 2406.0 > high 2402.0 of prev candle)
    candles.append({
        "timestamp": "2026-08-17T10:20:00Z",
        "open": 2398.0,
        "high": 2425.0,
        "low": 2406.0,
        "close": 2424.0,
        "volume": 800
    })

    # 5. Retrace / Confirmation Candle (10:25 UTC)
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
    assert signal.risk_reward >= 2.0
    assert signal.stop_loss < signal.entry_price < signal.take_profit

def test_strategy_engine_outside_session_rejection():
    engine = StrategyEngine()
    ltf_candles = generate_ict_long_setup_candles()
    # Change timestamps to 03:00 UTC (outside session)
    for c in ltf_candles:
        c["timestamp"] = c["timestamp"].replace("T10:", "T03:")

    signal = engine.evaluate_setup("XAUUSD", ltf_candles, ltf_candles, point_size=0.01)
    assert signal.status == "REJECTED"
    assert "Outside active trading session" in signal.reasons["rejection_reason"]

@pytest.mark.asyncio
async def test_api_evaluate_signals(async_client):
    res = await async_client.get("/api/strategy/signals?symbol=XAUUSD")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "signal" in data
    assert "status" in data["signal"]
    assert "reasons" in data["signal"]
