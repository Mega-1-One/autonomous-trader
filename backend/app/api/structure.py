from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service, get_strategy_engine
from app.services.market_data import MarketDataService
from app.strategy.provider import StrategyProvider

router = APIRouter(prefix="/api/structure", tags=["Market Structure"])

@router.get("/analyze", status_code=status.HTTP_200_OK)
async def analyze_structure(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    timeframe: str = Query("M5", description="Timeframe"),
    count: int = Query(200, ge=20, le=1000, description="Candle count"),
    swing_lookback: int = Query(3, ge=1, le=20, description="Swing lookback window"),
    market_service: MarketDataService = Depends(get_market_service),
    strategy: StrategyProvider = Depends(get_strategy_engine),
):
    """Performs deterministic market structure analysis returning trend, swing points, BOS, and MSS."""
    candles = market_service.fetch_candles(symbol, timeframe, count)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candles retrieved for {symbol} {timeframe}"
        )

    described = strategy.describe(
        symbol=symbol, candles=candles, timeframe=timeframe,
        swing_lookback=swing_lookback, confirm_on_close=True,
    )
    if described is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active strategy provides no market analysis for {symbol}"
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "swing_lookback": swing_lookback,
        "analysis": described["analysis"]
    }
