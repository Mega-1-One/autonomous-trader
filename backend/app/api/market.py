from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.api.deps import get_market_service
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api/market", tags=["Market Data"])

@router.get("/symbols", status_code=status.HTTP_200_OK)
async def get_symbols(market_service: MarketDataService = Depends(get_market_service)):
    """Returns list of supported instruments and their specifications."""
    symbols = market_service.get_supported_symbols()
    specs = {}
    for s in symbols:
        specs[s] = market_service.get_symbol_info(s)
    return {"symbols": symbols, "specifications": specs}

@router.get("/candles", status_code=status.HTTP_200_OK)
async def get_candles(
    symbol: str = Query("XAUUSD", description="Canonical symbol name"),
    timeframe: str = Query("M5", description="Timeframe (M1, M5, M15, M30, H1, H4)"),
    count: int = Query(100, ge=1, le=1000, description="Number of candles"),
    market_service: MarketDataService = Depends(get_market_service),
):
    """Fetches historical candles with normalized UTC timestamps."""
    candles = market_service.fetch_candles(symbol, timeframe, count)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unable to retrieve candles for symbol {symbol} timeframe {timeframe}"
        )
    
    stale = market_service.is_data_stale(symbol, timeframe)
    gaps = market_service.detect_missing_candles(candles, timeframe)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "is_stale": stale,
        "missing_gaps": gaps,
        "candles": candles
    }

@router.get("/status", status_code=status.HTTP_200_OK)
async def get_market_status(market_service: MarketDataService = Depends(get_market_service)):
    """Returns connection state and data freshness for core instruments."""
    connected = market_service.ensure_connected()
    freshness = {}
    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "NAS100"]:
        stale = market_service.is_data_stale(sym, "M5")
        freshness[sym] = {"is_stale": stale, "status": "STALE" if stale else "FRESH"}

    return {
        "connected": connected,
        "freshness": freshness
    }
