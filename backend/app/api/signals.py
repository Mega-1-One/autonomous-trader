from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service, get_strategy_engine
from app.services.market_data import MarketDataService
from app.strategy.engine import StrategyEngine

router = APIRouter(prefix="/api/strategy", tags=["Strategy Engine"])

@router.get("/signals", status_code=status.HTTP_200_OK)
async def evaluate_signals(
    symbol: str = Query("XAUUSD", description="Symbol name"),
    market_service: MarketDataService = Depends(get_market_service),
    strategy_engine: StrategyEngine = Depends(get_strategy_engine),
):
    """Evaluates live market state against the ICT/SMC strategy engine."""
    htf_candles = market_service.fetch_candles(symbol, "H1", count=100)
    ltf_candles = market_service.fetch_candles(symbol, "M5", count=200)

    if not ltf_candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unable to fetch market data for symbol {symbol}"
        )

    info = market_service.get_symbol_info(symbol) or {"point_size": 0.01}
    point_size = info.get("point_size", 0.01)

    signal = strategy_engine.evaluate_setup(
        symbol=symbol,
        htf_candles=htf_candles,
        ltf_candles=ltf_candles,
        point_size=point_size
    )

    return {
        "symbol": symbol,
        "signal": signal.to_dict()
    }
