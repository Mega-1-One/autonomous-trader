from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service
from app.services.market_data import MarketDataService
from app.strategy.structure import StructureEngine
from app.strategy.liquidity import LiquidityEngine
from app.strategy.displacement import DisplacementEngine
from app.strategy.fvg import FVGEngine
from app.strategy.sweeps import SweepEngine
from app.strategy.order_block import OrderBlockEngine

router = APIRouter(prefix="/api/strategy", tags=["Strategy Patterns"])

@router.get("/patterns", status_code=status.HTTP_200_OK)
async def get_strategy_patterns(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    timeframe: str = Query("M5", description="Timeframe"),
    count: int = Query(200, ge=30, le=1000, description="Candle count"),
    market_service: MarketDataService = Depends(get_market_service),
):
    """Returns detected FVGs, Order Blocks, Liquidity Sweeps, and Displacement candles."""
    candles = market_service.fetch_candles(symbol, timeframe, count)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candles found for {symbol} {timeframe}"
        )

    info = market_service.get_symbol_info(symbol) or {"point_size": 0.01}
    point_size = info.get("point_size", 0.01)

    # 1. Structure
    struct_engine = StructureEngine(swing_lookback=3)
    struct_res = struct_engine.analyze_structure(candles)

    # 2. Liquidity
    liq_engine = LiquidityEngine()
    liq_levels = liq_engine.get_all_liquidity_levels(candles, struct_res.swing_points, point_size)

    # 3. Displacement
    disp_engine = DisplacementEngine()
    displacements = disp_engine.detect_displacement(candles)

    # 4. FVG
    fvg_engine = FVGEngine()
    fvgs = fvg_engine.detect_fvgs(candles, timeframe=timeframe, point_size=point_size)

    # 5. Sweeps
    sweep_engine = SweepEngine()
    sweeps = sweep_engine.detect_sweeps(candles, liq_levels, point_size=point_size)

    # 6. Order Blocks
    ob_engine = OrderBlockEngine()
    order_blocks = ob_engine.detect_order_blocks(candles, displacements, struct_res.events)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trend": struct_res.trend,
        "displacements": [d.to_dict() for d in displacements],
        "fair_value_gaps": [f.to_dict() for f in fvgs],
        "liquidity_sweeps": [s.to_dict() for s in sweeps],
        "order_blocks": [ob.to_dict() for ob in order_blocks]
    }
