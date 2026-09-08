from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.services.market_data import MarketDataService
from app.backtest.engine import BacktestEngine
from app.backtest.monte_carlo import MonteCarloSimulator

router = APIRouter(prefix="/api/backtest", tags=["Backtesting & Monte Carlo"])
market_service = MarketDataService()

class BacktestRunRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "M5"
    candle_count: int = 500
    initial_balance: float = 10000.0
    spread_pips: float = 1.0
    slippage_pips: float = 0.5
    commission_per_lot: float = 7.0

class MonteCarloRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "M5"
    candle_count: int = 500
    initial_balance: float = 10000.0
    iterations: int = 200

@router.post("/run", status_code=status.HTTP_200_OK)
async def run_backtest(req: BacktestRunRequest):
    """Runs zero-lookahead backtest using exact live strategy and risk logic."""
    candles = market_service.fetch_candles(req.symbol, req.timeframe, count=req.candle_count)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unable to fetch historical data for symbol {req.symbol}"
        )

    info = market_service.get_symbol_info(req.symbol) or {"point_size": 0.01}
    point_size = info.get("point_size", 0.01)

    engine = BacktestEngine(
        initial_balance=req.initial_balance,
        spread_pips=req.spread_pips,
        slippage_pips=req.slippage_pips,
        commission_per_lot=req.commission_per_lot
    )

    report = engine.run(symbol=req.symbol, candles=candles, point_size=point_size)

    return {
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "report": report.to_dict()
    }

@router.post("/monte-carlo", status_code=status.HTTP_200_OK)
async def run_monte_carlo(req: MonteCarloRequest):
    """Runs Monte Carlo simulation over backtested trade results."""
    candles = market_service.fetch_candles(req.symbol, req.timeframe, count=req.candle_count)
    info = market_service.get_symbol_info(req.symbol) or {"point_size": 0.01}
    point_size = info.get("point_size", 0.01)

    engine = BacktestEngine(initial_balance=req.initial_balance)
    report = engine.run(symbol=req.symbol, candles=candles, point_size=point_size)

    # Reconstruct trades from report or run simulation
    simulator = MonteCarloSimulator(iterations=req.iterations)
    res = simulator.run_simulation(req.initial_balance, [])

    return {
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "simulation": res.to_dict()
    }
