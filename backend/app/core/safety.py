"""Destination-aware safety gate (ADR-3).

Enforces the execution-mode × destination truth table and consults the
cross-process emergency-stop sentinel (ADR-8) first.

Truth table (destination = where the order is actually sent):

| Execution mode | Destination = MOCK (paper sim / mock adapter) | Destination = REAL broker |
|---|---|---|
| BACKTEST | allowed | refused |
| PAPER    | allowed | refused |
| DEMO     | allowed | allowed only if account_trade_mode == 0 (demo account) |
| LIVE     | allowed | allowed only if both live flags set |
| any, with sentinel present | refused | refused |

Every order-sending path (ExecutionEngine and the six direct order-path files)
must call :func:`ensure_trading_allowed` before sending.
"""
from typing import Any, Optional

from app.core import stop_state
from app.core import config as _config
from app.core.config import ExecutionMode

DEST_MOCK = "MOCK"
DEST_REAL = "REAL"


class SafetyViolation(Exception):
    """Raised when an order send is not permitted by the mode × destination model."""


def ensure_trading_allowed(
    destination: str,
    *,
    account_trade_mode: Optional[int] = None,
) -> None:
    """Raises :class:`SafetyViolation` if sending to ``destination`` is not allowed."""
    # 1. Cross-process emergency-stop sentinel first (blocks everything).
    stop_reason = stop_state.is_active()
    if stop_reason is not None:
        raise SafetyViolation(
            f"EMERGENCY STOP ACTIVE ({stop_reason}). All new order submissions blocked."
        )

    if destination not in (DEST_MOCK, DEST_REAL):
        raise SafetyViolation(f"Unknown order destination: {destination!r}")

    mode = _config.settings.EXECUTION_MODE

    # Mock/paper execution is allowed in every mode.
    if destination == DEST_MOCK:
        return

    # REAL broker destination:
    if mode in (ExecutionMode.PAPER, ExecutionMode.BACKTEST):
        raise SafetyViolation(
            f"EXECUTION_MODE={mode.value} forbids real broker order submission. "
            "Use EXECUTION_MODE=DEMO (with a demo account) or LIVE with both "
            "live-trading flags for real sends."
        )

    if mode == ExecutionMode.DEMO:
        if account_trade_mode != 0:
            raise SafetyViolation(
                "EXECUTION_MODE=DEMO allows real sends only onto a demo account "
                "(account trade_mode == 0). "
                f"Got trade_mode={account_trade_mode!r}."
            )
        return

    if mode == ExecutionMode.LIVE:
        if not (_config.settings.ENABLE_LIVE_TRADING and _config.settings.LIVE_TRADING_CONFIRMATION):
            raise SafetyViolation(
                "EXECUTION_MODE=LIVE requires both ENABLE_LIVE_TRADING and "
                "LIVE_TRADING_CONFIRMATION to be true."
            )
        return


def destination_for_adapter(adapter: Any) -> str:
    """Derives the gate destination from the adapter type (ADR-3)."""
    from app.data.mt5_mock import MockMT5Adapter
    return DEST_MOCK if isinstance(adapter, MockMT5Adapter) else DEST_REAL


def account_trade_mode_from_adapter(adapter: Any) -> Optional[int]:
    """Reads trade_mode from an adapter's account info (dict or mt5 object)."""
    try:
        info = adapter.get_account_info()
    except Exception:
        return None
    if info is None:
        return None
    if isinstance(info, dict):
        return info.get("trade_mode")
    return getattr(info, "trade_mode", None)


def account_trade_mode_from_mt5() -> Optional[int]:
    """Reads trade_mode directly from the MT5 terminal (bot paths).

    Returns None when MetaTrader5 is unavailable or the terminal has no
    account info; the gate then fails safe (DEMO real sends are refused).
    """
    try:
        import MetaTrader5 as mt5
        acc = mt5.account_info()
    except Exception:
        return None
    if acc is None:
        return None
    return getattr(acc, "trade_mode", None)
