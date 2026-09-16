from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.api.deps import get_market_service, get_execution_engine, require_api_token
from app.execution.engine import ExecutionEngine
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api/execution", tags=["Execution & Position Management"])

class OrderSubmitRequest(BaseModel):
    client_signal_id: Optional[str] = None
    symbol: str = "XAUUSD"
    direction: str = "LONG"
    entry_price: float
    stop_loss: float
    take_profit: float
    spread_pips: float = 1.0

@router.get("/positions", status_code=status.HTTP_200_OK)
async def get_positions(
    market_service: MarketDataService = Depends(get_market_service),
    execution_engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Returns active and historical simulated positions with real-time floating P&L and metrics."""
    # Update active positions with live prices (no hard-coded fallback, P-17/C-01)
    symbols = market_service.get_supported_symbols()
    current_prices = {}
    for s in symbols:
        price = market_service.get_latest_price(s)
        if price is not None:
            current_prices[s] = price

    updated = execution_engine.update_positions(current_prices)
    all_positions = [p.to_dict() for p in execution_engine.positions.values()]

    return {
        "total_positions": len(all_positions),
        "open_positions": [p for p in all_positions if p["status"] == "OPEN"],
        "closed_positions": [p for p in all_positions if p["status"] == "CLOSED"]
    }

@router.post("/orders", status_code=status.HTTP_200_OK)
async def submit_order(
    req: OrderSubmitRequest,
    execution_engine: ExecutionEngine = Depends(get_execution_engine),
    _: None = Depends(require_api_token),
):
    """Submits order to execution engine with idempotency & safety checks."""
    result = execution_engine.execute_signal(req.model_dump(), current_spread_pips=req.spread_pips)
    if result["status"] == "FAILED":
        # Broker rejected/failed the send: surface as a bad-gateway failure
        # path (C-01 owns this change exclusively; success shapes unchanged).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("reason", "Broker order send failed"),
        )
    if result["status"] == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["reason"]
        )
    return result

@router.post("/positions/{position_id}/close", status_code=status.HTTP_200_OK)
async def close_position(
    position_id: str,
    execution_engine: ExecutionEngine = Depends(get_execution_engine),
    _: None = Depends(require_api_token),
):
    """Manually closes an individual open position."""
    pos = execution_engine.positions.get(position_id)
    if not pos or pos.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Open position {position_id} not found"
        )

    execution_engine._close_position(pos, pos.current_price, "MANUAL_CLOSE")
    return {"status": "CLOSED", "position": pos.to_dict()}

@router.post("/close-all", status_code=status.HTTP_200_OK)
async def close_all_positions(
    reason: Optional[str] = Body(None, embed=True),
    execution_engine: ExecutionEngine = Depends(get_execution_engine),
    _: None = Depends(require_api_token),
):
    """Emergency closes all active positions immediately."""
    closed = execution_engine.close_all_positions(reason or "EMERGENCY_CLOSE_ALL")
    return {
        "status": "ALL_POSITIONS_CLOSED",
        "closed_count": len(closed),
        "positions": closed
    }
