from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.data.mt5_real import RealMT5Adapter
from app.data.mt5_mock import MockMT5Adapter

router = APIRouter(prefix="/api", tags=["Health"])

# Initialize MT5 adapter (tries Real MT5 terminal connection first; falls back to Mock if terminal not open)
real_mt5 = RealMT5Adapter()
if not real_mt5.connect():
    mt5_adapter = MockMT5Adapter()
    mt5_adapter.connect()
else:
    mt5_adapter = real_mt5

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db_session)):
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

    return {
        "status": "healthy" if db_status else "degraded",
        "app_name": settings.APP_NAME,
        "execution_mode": settings.EXECUTION_MODE.value,
        "enable_live_trading": settings.ENABLE_LIVE_TRADING,
        "live_trading_confirmation": settings.LIVE_TRADING_CONFIRMATION,
        "database_connected": db_status,
        "mt5_connected": mt5_connected,
        "mt5_adapter": adapter_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
