import pytest
from app.strategy.structure import StructureEngine, TrendRegime, PointType, StructureEventType

def generate_synthetic_uptrend_candles():
    """Generates synthetic candles forming an uptrend with clear swing highs and swing lows."""
    prices = [
        # Initial base
        100, 101, 102, 105, 104, 103, 101, 100, 99, 100, 101, # Swing Low at 99 (idx 8)
        # Rally to Swing High
        102, 105, 108, 112, 115, 114, 112, 110, 108, # Swing High at 115 (idx 16)
        # Pullback to Higher Low
        107, 105, 106, 107, # Higher Low at 105 (idx 20)
        # Rally breaking Swing High -> BOS -> Higher High
        110, 114, 118, 122, 125, 124, 122, 120, # Swing High at 125 (idx 27)
    ]
    candles = []
    for i, p in enumerate(prices):
        candles.append({
            "timestamp": f"2026-08-17T{i:02d}:00:00Z",
            "open": p - 0.5,
            "high": p + 1.0,
            "low": p - 1.0,
            "close": p,
            "volume": 100
        })
    return candles

def test_detect_swing_points():
    engine = StructureEngine(swing_lookback=2)
    candles = generate_synthetic_uptrend_candles()
    pts = engine.detect_swing_points(candles)

    assert len(pts) > 0
    highs = [p for p in pts if p.point_type == PointType.SWING_HIGH.value]
    lows = [p for p in pts if p.point_type == PointType.SWING_LOW.value]
    assert len(highs) >= 2
    assert len(lows) >= 2

def test_label_swing_points():
    engine = StructureEngine(swing_lookback=2)
    candles = generate_synthetic_uptrend_candles()
    pts = engine.detect_swing_points(candles)
    engine.label_swing_points(pts)

    labels = [p.label for p in pts if p.label is not None]
    assert "HIGH" in labels or "HH" in labels
    assert "LOW" in labels or "HL" in labels

def test_bos_and_trend_analysis():
    engine = StructureEngine(swing_lookback=2, confirm_on_close=True)
    candles = generate_synthetic_uptrend_candles()
    res = engine.analyze_structure(candles)

    assert res.trend in [TrendRegime.BULLISH.value, TrendRegime.RANGING.value]
    assert len(res.events) > 0
    # Check that at least one event is a Bullish break
    bullish_events = [e for e in res.events if e.direction == "BULLISH"]
    assert len(bullish_events) > 0

def test_mss_reversal():
    engine = StructureEngine(swing_lookback=2, confirm_on_close=True)
    candles = generate_synthetic_uptrend_candles()
    
    # Append sharp reversal crashing below Higher Low (105)
    crash_prices = [115, 110, 104, 98, 95, 96, 97]
    start_len = len(candles)
    for i, p in enumerate(crash_prices):
        candles.append({
            "timestamp": f"2026-08-17T{start_len+i:02d}:00:00Z",
            "open": p + 0.5,
            "high": p + 1.0,
            "low": p - 1.0,
            "close": p,
            "volume": 200
        })

    res = engine.analyze_structure(candles)
    assert res.trend == TrendRegime.BEARISH.value
    mss_events = [e for e in res.events if e.event_type == StructureEventType.MSS.value]
    assert len(mss_events) > 0

@pytest.mark.asyncio
async def test_api_structure_analyze(async_client):
    res = await async_client.get("/api/structure/analyze?symbol=XAUUSD&timeframe=M5&count=100&swing_lookback=3")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "analysis" in data
    assert "trend" in data["analysis"]
    assert "swing_points" in data["analysis"]
