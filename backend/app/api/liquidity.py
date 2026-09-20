from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service, get_strategy_engine
from app.services.market_data import MarketDataService
from app.strategy.provider import StrategyProvider

router = APIRouter(prefix="/api/liquidity", tags=["Liquidity"])

@router.get("/levels", status_code=status.HTTP_200_OK)
async def get_liquidity_levels(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    timeframe: str = Query("M5", description="Timeframe"),
    count: int = Query(300, ge=50, le=1000, description="Candle count"),
    tolerance_pips: float = Query(2.0, ge=0.1, le=10.0, description="Equal high/low tolerance in pips"),
    market_service: MarketDataService = Depends(get_market_service),
    strategy: StrategyProvider = Depends(get_strategy_engine),
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

    described = strategy.describe(
        symbol=symbol, candles=candles, timeframe=timeframe,
        point_size=point_size, tolerance_pips=tolerance_pips,
    )
    if described is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active strategy provides no market analysis for {symbol}"
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_levels": described["total_levels"],
        "buyside_liquidity": described["buyside_liquidity"],
        "sellside_liquidity": described["sellside_liquidity"]
    }
