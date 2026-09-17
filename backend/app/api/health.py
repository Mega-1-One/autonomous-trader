from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_adapter
from app.core import config as _config
from app.core.database import get_db_session
from app.data.mt5_interface import AbstractMT5Adapter
from app.data.mt5_mock import MockMT5Adapter

router = APIRouter(prefix="/api", tags=["Health"])

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    mt5_adapter: AbstractMT5Adapter = Depends(get_adapter),
):
    """Health check endpoint evaluating system status, DB connection, and MT5 connection status."""
    db_status = False
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_status = True
    except Exception:
        db_status = False

    mt5_connected = mt5_adapter.is_connected()
    adapter_name = mt5_adapter.__class__.__name__
    settings = _config.settings
    # NEW-01/NEW-05: make a simulated real-money mode operator-visible.
    # `mt5_connected` reports the *active* adapter (a connected mock in
    # PAPER/BACKTEST); `simulated_execution` is True only when a DEMO/LIVE
    # mode runs on the mock adapter, i.e. fills would be simulated.
    simulated_execution = (
        isinstance(mt5_adapter, MockMT5Adapter)
        and settings.EXECUTION_MODE.value in ("DEMO", "LIVE")
    )

    return {
        "status": "healthy" if db_status else "degraded",
        "app_name": settings.APP_NAME,
        "execution_mode": settings.EXECUTION_MODE.value,
        "enable_live_trading": settings.ENABLE_LIVE_TRADING,
        "live_trading_confirmation": settings.LIVE_TRADING_CONFIRMATION,
        "database_connected": db_status,
        "mt5_connected": mt5_connected,
        "mt5_adapter": adapter_name,
        "simulated_execution": simulated_execution,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
