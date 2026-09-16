"""Application state container accessors (ADR-2, B-01).

The state is built in ``main.py``'s lifespan (eagerly, in-process). These
small ``Depends`` accessors expose the shared engines/services to routers.
For test environments that do not run lifespan events (httpx ASGITransport),
the accessors lazily build and cache the same state on ``app.state`` so the
test suite keeps working without per-test wiring.
"""
from typing import Any

from fastapi import Request

from app.data.mt5_interface import AbstractMT5Adapter
from app.data.mt5_real import RealMT5Adapter
from app.data.mt5_mock import MockMT5Adapter
from app.services.market_data import MarketDataService
from app.risk.engine import RiskEngine
from app.execution.engine import ExecutionEngine
from app.strategy.engine import StrategyEngine


def build_adapter() -> AbstractMT5Adapter:
    """Tries the real MT5 terminal first; falls back to the mock adapter."""
    real_mt5 = RealMT5Adapter()
    if real_mt5.connect():
        return real_mt5
    mock = MockMT5Adapter()
    mock.connect()
    return mock


def init_app_state(app: Any) -> None:
    """Builds the shared in-process engine set (the ONE instance per process)."""
    adapter = build_adapter()
    app.state.adapter = adapter
    app.state.market_service = MarketDataService(adapter=adapter)
    app.state.risk_engine = RiskEngine()
    # Explicit RiskEngine injection (review R-06): the execution engine must
    # reuse the shared instance, never build its own.
    app.state.execution_engine = ExecutionEngine(
        adapter=adapter, risk_engine=app.state.risk_engine
    )
    app.state.strategy_engine = StrategyEngine()


def _ensure_state(request: Request) -> Any:
    if not hasattr(request.app.state, "execution_engine"):
        init_app_state(request.app)
    return request.app.state


def get_adapter(request: Request) -> AbstractMT5Adapter:
    return _ensure_state(request).adapter


def get_market_service(request: Request) -> MarketDataService:
    return _ensure_state(request).market_service


def get_risk_engine(request: Request) -> RiskEngine:
    return _ensure_state(request).risk_engine


def get_execution_engine(request: Request) -> ExecutionEngine:
    return _ensure_state(request).execution_engine


def get_strategy_engine(request: Request) -> StrategyEngine:
    return _ensure_state(request).strategy_engine
