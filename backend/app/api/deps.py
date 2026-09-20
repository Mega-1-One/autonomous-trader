"""Application state container accessors (ADR-2, B-01).

The state is built in ``main.py``'s lifespan (eagerly, in-process). These
small ``Depends`` accessors expose the shared engines/services to routers.
For test environments that do not run lifespan events (httpx ASGITransport),
the accessors lazily build and cache the same state on ``app.state`` so the
test suite keeps working without per-test wiring.
"""
import hmac
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import config as _config
from app.data.adapter_factory import build_adapter
from app.data.mt5_interface import AbstractMT5Adapter
from app.services.market_data import MarketDataService
from app.risk.engine import RiskEngine
from app.execution.engine import ExecutionEngine
from app.strategy import ict_adapter  # noqa: F401 (registers the ict_scalp provider)
from app.strategy.provider import StrategyProvider, create_provider, resolve_strategy_config

_bearer_scheme = HTTPBearer(auto_error=False)


def token_enforcement_active() -> bool:
    """Token gate is armed only in production WITH a token configured (D-01/ADR-6)."""
    return _config.settings.APP_ENV == "production" and bool(_config.settings.AUTOMATION_API_TOKEN)


async def require_api_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    """Bearer-token guard for mutating endpoints (D-01).

    Open by default (local dev). Enforced only when APP_ENV=production and
    AUTOMATION_API_TOKEN is set; the bundled dashboard sends the token via
    NEXT_PUBLIC_API_TOKEN (C-05). Production deployments without the token
    configured must front the API with a reverse proxy or accept the exposure
    in writing.
    """
    if not token_enforcement_active():
        return
    expected = _config.settings.AUTOMATION_API_TOKEN or ""
    provided = credentials.credentials if credentials else ""
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
        )


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
    # E2/E4: strategy behind the provider seam; each provider receives
    # only its own config section.
    provider_name, provider_config = resolve_strategy_config(_config.settings.strategy_config)
    app.state.strategy_engine = create_provider(provider_name, provider_config)


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


def get_strategy_engine(request: Request) -> StrategyProvider:
    return _ensure_state(request).strategy_engine
