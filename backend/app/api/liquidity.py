from fastapi import APIRouter, Query, HTTPException, status
from app.services.market_data import MarketDataService
from app.strategy.structure import StructureEngine
from app.strategy.liquidity import LiquidityEngine

router = APIRouter(prefix="/api/liquidity", tags=["Liquidity"])
market_service = MarketDataService()

@router.get("/levels", status_code=status.HTTP_200_OK)
async def get_liquidity_levels(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    timeframe: str = Query("M5", description="Timeframe"),
    count: int = Query(300, ge=50, le=1000, description="Candle count"),
    tolerance_pips: float = Query(2.0, ge=0.1, le=10.0, description="Equal high/low tolerance in pips")
):
    """Returns all detected Buy-Side and Sell-Side liquidity pools."""
    candles = market_service.fetch_candles(symbol, timeframe, count)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candles found for {symbol} {timeframe}"
        )

    info = market_service.get_symbol_info(symbol) or {"point_size": 0.01}
    point_size = info.get("point_size", 0.01)

    struct_engine = StructureEngine(swing_lookback=3)
    swing_points = struct_engine.detect_swing_points(candles)

    liq_engine = LiquidityEngine(eqh_eql_tolerance_pips=tolerance_pips)
    levels = liq_engine.get_all_liquidity_levels(candles, swing_points, point_size)

    buyside = [l.to_dict() for l in levels if l.side == "BUYSIDE"]
    sellside = [l.to_dict() for l in levels if l.side == "SELLSIDE"]

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_levels": len(levels),
        "buyside_liquidity": buyside,
        "sellside_liquidity": sellside
    }
