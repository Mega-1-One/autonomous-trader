from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service, get_strategy_engine
from app.services.market_data import MarketDataService
from app.strategy.provider import StrategyProvider

router = APIRouter(prefix="/api/strategy", tags=["Strategy Patterns"])

@router.get("/patterns", status_code=status.HTTP_200_OK)
async def get_strategy_patterns(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    timeframe: str = Query("M5", description="Timeframe"),
    count: int = Query(200, ge=30, le=1000, description="Candle count"),
    market_service: MarketDataService = Depends(get_market_service),
    strategy: StrategyProvider = Depends(get_strategy_engine),
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

    described = strategy.describe(
        symbol=symbol, candles=candles, timeframe=timeframe,
        point_size=point_size,
    )
    if described is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active strategy provides no market analysis for {symbol}"
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "trend": described["trend"],
        "displacements": described["displacements"],
        "fair_value_gaps": described["fair_value_gaps"],
        "liquidity_sweeps": described["liquidity_sweeps"],
        "order_blocks": described["order_blocks"]
    }
