import pytest
from app.strategy.liquidity import LiquidityEngine, LiquidityType, LiquiditySide
from app.strategy.structure import SwingPoint

def create_multi_day_candles():
    """Generates synthetic candles spanning 2 calendar days."""
    candles = []
    # Day 1: 2026-08-15
    for h in range(24):
        candles.append({
            "timestamp": f"2026-08-15T{h:02d}:00:00Z",
            "open": 2400.0,
            "high": 2450.0 if h == 10 else 2410.0,
            "low": 2380.0 if h == 15 else 2395.0,
            "close": 2405.0,
            "volume": 100
        })
    # Day 2: 2026-08-16
    for h in range(24):
        candles.append({
            "timestamp": f"2026-08-16T{h:02d}:00:00Z",
            "open": 2405.0,
            "high": 2460.0 if h == 12 else 2420.0,
            "low": 2390.0 if h == 18 else 2400.0,
            "close": 2415.0,
            "volume": 100
        })
    return candles

def test_detect_pdh_pdl():
    engine = LiquidityEngine()
    candles = create_multi_day_candles()
    levels = engine.detect_pdh_pdl(candles)

    assert len(levels) == 2
    pdh = next(l for l in levels if l.level_type == LiquidityType.PDH.value)
    pdl = next(l for l in levels if l.level_type == LiquidityType.PDL.value)

    # Previous day is 2026-08-15
    assert pdh.price == 2450.0
    assert pdl.price == 2380.0
    assert pdh.side == LiquiditySide.BUYSIDE.value
    assert pdl.side == LiquiditySide.SELLSIDE.value

def test_detect_equal_highs():
    engine = LiquidityEngine(eqh_eql_tolerance_pips=2.0)
    swing_points = [
        SwingPoint(index=10, timestamp="2026-08-15T10:00:00Z", point_type="HIGH", price=2450.00),
        SwingPoint(index=25, timestamp="2026-08-15T15:00:00Z", point_type="LOW", price=2400.00),
        SwingPoint(index=40, timestamp="2026-08-15T20:00:00Z", point_type="HIGH", price=2450.01), # EQH within 0.01 (1 pip)
    ]

    levels = engine.detect_equal_highs_lows(swing_points, point_size=0.01)
    eqh = [l for l in levels if l.level_type == LiquidityType.EQH.value]
    assert len(eqh) == 1
    assert eqh[0].price == 2450.01

def test_session_highs_lows():
    engine = LiquidityEngine()
    candles = create_multi_day_candles()
    levels = engine.detect_session_highs_lows(candles)

    assert len(levels) >= 2
    types = [l.level_type for l in levels]
    assert LiquidityType.SESSION_HIGH.value in types
    assert LiquidityType.SESSION_LOW.value in types

@pytest.mark.asyncio
async def test_api_get_liquidity_levels(async_client):
    res = await async_client.get("/api/liquidity/levels?symbol=XAUUSD&timeframe=M5&count=300")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "buyside_liquidity" in data
    assert "sellside_liquidity" in data
