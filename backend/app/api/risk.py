from fastapi import APIRouter, Depends, status, Body
from pydantic import BaseModel
from typing import Optional

from app.api.deps import get_execution_engine, get_market_service, get_risk_engine, require_api_token
from app.execution.engine import ExecutionEngine
from app.risk.engine import RiskEngine
from app.services.market_data import MarketDataService

router = APIRouter(tags=["Risk & System Control"])

class RiskEvaluateRequest(BaseModel):
    symbol: str = "XAUUSD"
    entry_price: float
    stop_loss: float
    take_profit: float
    spread_pips: float = 1.0

@router.get("/api/risk/status", status_code=status.HTTP_200_OK)
async def get_risk_status(risk_engine: RiskEngine = Depends(get_risk_engine)):
    """Returns risk engine parameters, daily loss lock status, and emergency stop state."""
    return {
        "emergency_stop_active": risk_engine.emergency_stop_active,
        "daily_lock_active": risk_engine.daily_lock_active,
        "daily_lock_reason": risk_engine.daily_lock_reason,
        "today_trade_count": risk_engine.today_trade_count,
        "today_realized_pnl": risk_engine.today_realized_pnl,
        "risk_parameters": {
            "risk_per_trade_percent": risk_engine.risk_per_trade_percent,
            "maximum_daily_loss_percent": risk_engine.maximum_daily_loss_percent,
            "maximum_trades_per_day": risk_engine.maximum_trades_per_day,
            "maximum_open_positions": risk_engine.maximum_open_positions,
            "maximum_spread_pips": risk_engine.maximum_spread_pips,
            "minimum_rr": risk_engine.minimum_rr,
        }
    }

@router.post("/api/risk/evaluate", status_code=status.HTTP_200_OK)
async def evaluate_trade_risk_endpoint(
    req: RiskEvaluateRequest,
    risk_engine: RiskEngine = Depends(get_risk_engine),
    market_service: MarketDataService = Depends(get_market_service),
    execution_engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Evaluates risk and calculates lot size for a proposed trade."""
    info = market_service.get_symbol_info(req.symbol) or {
        "digits": 2, "point_size": 0.01, "tick_size": 0.01, "tick_value": 1.0,
        "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01
    }
    acc = market_service.adapter.get_account_info() or {"equity": 10000.0}

    signal_dict = {
        "entry_price": req.entry_price,
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit
    }

    # N2-M7: evaluate against the real open-position count so the
    # maximum-open-positions limit cannot be bypassed.
    open_count = len([p for p in execution_engine.positions.values() if p.status == "OPEN"])
    decision = risk_engine.evaluate_trade_risk(
        signal=signal_dict,
        account_info=acc,
        symbol_info=info,
        current_open_positions_count=open_count,
        current_spread_pips=req.spread_pips
    )

    return {
        "symbol": req.symbol,
        "decision": decision.to_dict()
    }

@router.post("/api/system/emergency-stop", status_code=status.HTTP_200_OK)
async def trigger_emergency_stop(
    reason: Optional[str] = Body(None, embed=True),
    risk_engine: RiskEngine = Depends(get_risk_engine),
    _: None = Depends(require_api_token),
):
    """Triggers global emergency stop, blocking all new trade entries immediately."""
    persisted = risk_engine.trigger_emergency_stop(reason or "User API emergency stop trigger")
    message = "Global emergency stop activated. All new entries are strictly prohibited."
    if not persisted:
        # L-2: cross-process propagation degraded; say so in the message
        # (no new response keys, so the contract is unchanged).
        message += " WARNING: cross-process sentinel was NOT persisted; other processes may keep trading."
    return {
        "status": "EMERGENCY_STOP_ACTIVATED",
        "emergency_stop_active": True,
        "message": message
    }

@router.post("/api/system/reset-emergency-stop", status_code=status.HTTP_200_OK)
async def reset_emergency_stop_endpoint(
    risk_engine: RiskEngine = Depends(get_risk_engine),
    _: None = Depends(require_api_token),
):
    """Resets global emergency stop."""
    persisted = risk_engine.reset_emergency_stop()
    message = "Global emergency stop reset successfully."
    if not persisted:
        message += " WARNING: cross-process sentinel was NOT removed; other processes may stay stopped."
    return {
        "status": "EMERGENCY_STOP_RESET",
        "emergency_stop_active": False,
        "message": message
    }
