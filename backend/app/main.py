from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.structure import router as structure_router
from app.api.liquidity import router as liquidity_router
from app.api.setups import router as setups_router
from app.api.signals import router as signals_router
from app.api.risk import router as risk_router
from app.api.backtest import router as backtest_router
from app.api.execution import router as execution_router
from app.api.deps import init_app_state
from app.core.config import settings
from app.core.database import engine
from app.core.logging import logger
from app.models.base import Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Autonomous Trading Engine...")
    logger.info(f"Execution Mode: {settings.EXECUTION_MODE.value}")
    logger.info(f"Safety Live Trading Enabled: {settings.ENABLE_LIVE_TRADING}")

    # Initialize database tables for dev/testing
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Build the shared in-process engine set (ADR-2/B-01). MT5 adapter
    # connection previously attempted at health.py import time.
    init_app_state(app)

    yield

    logger.info("Shutting down Autonomous Trading Engine...")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Autonomous MT5 Quantitative Trading System",
    lifespan=lifespan
)

# CORS restricted to configured origins (C-06/P-05: no wildcard with credentials)
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(market_router)
app.include_router(structure_router)
app.include_router(liquidity_router)
app.include_router(setups_router)
app.include_router(signals_router)
app.include_router(risk_router)
app.include_router(backtest_router)
app.include_router(execution_router)









@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }
