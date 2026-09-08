import pytest
from app.strategy.displacement import DisplacementEngine
from app.strategy.fvg import FVGEngine, FVGType, MitigationStatus
from app.strategy.sweeps import SweepEngine
from app.strategy.order_block import OrderBlockEngine
from app.strategy.liquidity import LiquidityLevel, LiquiditySide
from app.strategy.structure import StructureEvent

def generate_fvg_candles():
    """Generates synthetic 3-candle sequence creating a Bullish FVG."""
    return [
        {"timestamp": "2026-08-17T10:00:00Z", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 100},
        {"timestamp": "2026-08-17T10:05:00Z", "open": 101.0, "high": 110.0, "low": 101.0, "close": 109.0, "volume": 500}, # Big bullish impulse
        {"timestamp": "2026-08-17T10:10:00Z", "open": 109.0, "high": 115.0, "low": 105.0, "close": 114.0, "volume": 200}, # Low is 105.0 > High 102.0 (c1)
    ]

def test_displacement_engine():
    engine = DisplacementEngine(atr_period=2, atr_multiplier=1.0, min_body_percentage=50.0)
    candles = generate_fvg_candles()
    displacements = engine.detect_displacement(candles)

    assert len(displacements) >= 1
    assert displacements[0].direction == "BULLISH"

def test_fvg_engine():
    engine = FVGEngine(min_gap_size_pips=0.1)
    candles = generate_fvg_candles()
    fvgs = engine.detect_fvgs(candles, timeframe="M5", point_size=0.01)

    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.fvg_type == FVGType.BULLISH.value
    assert fvg.lower_boundary == 102.0
    assert fvg.upper_boundary == 105.0
    assert fvg.gap_size == 3.0
    assert fvg.mitigation_status == MitigationStatus.UNMITIGATED.value

def test_fvg_mitigation_update():
    engine = FVGEngine(min_gap_size_pips=0.1)
    candles = generate_fvg_candles()
    # Add a 4th candle pulling back into gap
    candles.append({"timestamp": "2026-08-17T10:15:00Z", "open": 114.0, "high": 114.0, "low": 103.5, "close": 106.0, "volume": 150})
    fvgs = engine.detect_fvgs(candles, timeframe="M5", point_size=0.01)

    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.mitigation_status == MitigationStatus.PARTIALLY_MITIGATED.value
    assert fvg.fill_percentage > 0.0

def test_sweep_engine():
    engine = SweepEngine(sweep_threshold_pips=0.5)
    candles = [
        {"timestamp": "2026-08-17T10:00:00Z", "open": 100.0, "high": 102.0, "low": 94.0, "close": 97.0}, # Sweeps low 95.0, closes 97.0
    ]
    levels = [
        LiquidityLevel(level_type="PDL", side=LiquiditySide.SELLSIDE.value, price=95.0, timestamp="2026-08-16T00:00:00Z", strength=2.0, source="PDL")
    ]
    sweeps = engine.detect_sweeps(candles, levels, point_size=0.01)

    assert len(sweeps) == 1
    assert sweeps[0].sweep_type == "BULLISH_SWEEP"
    assert sweeps[0].sweep_extreme_price == 94.0

def test_order_block_engine():
    engine = OrderBlockEngine()
    candles = [
        {"timestamp": "2026-08-17T09:55:00Z", "open": 102.0, "high": 102.5, "low": 99.5, "close": 100.0}, # Bearish candle before displacement
        {"timestamp": "2026-08-17T10:00:00Z", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
        {"timestamp": "2026-08-17T10:05:00Z", "open": 101.0, "high": 110.0, "low": 101.0, "close": 109.0}, # Disp idx 2
    ]
    disp_engine = DisplacementEngine(atr_period=2, atr_multiplier=1.0)
    displacements = disp_engine.detect_displacement(candles)
    events = [StructureEvent(event_type="BOS", direction="BULLISH", broken_level=105.0, broken_point_index=0, trigger_candle_index=2, timestamp="2026-08-17T10:05:00Z", description="")]

    obs = engine.detect_order_blocks(candles, displacements, events)
    assert len(obs) == 1
    assert obs[0].ob_type == "BULLISH"
    assert obs[0].candle_index == 0

@pytest.mark.asyncio
async def test_api_get_strategy_patterns(async_client):
    res = await async_client.get("/api/strategy/patterns?symbol=XAUUSD&timeframe=M5&count=200")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "fair_value_gaps" in data
    assert "liquidity_sweeps" in data
    assert "order_blocks" in data
    assert "displacements" in data
