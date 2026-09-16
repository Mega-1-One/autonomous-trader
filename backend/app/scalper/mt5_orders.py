"""Shared MT5 order/close request builders (C-03).

All five scalper bots plus scripts/run_demo_trader.py build broker request
payloads here so per-bot plumbing (deviation, filling, magic/comment
passthrough) cannot drift. Strategy logic, magic numbers, defaults, and
output formats are unchanged in the callers; only payload construction is
shared. ``magic``/``comment`` are delegated through so the adapter path
(C-07) can honor per-strategy attribution.
"""
from typing import Any, Dict, Optional


def pip_scale_for(symbol: str) -> float:
    """Pip scale used by the scalper bots (legacy convention, preserved exactly).

    0.10 for XAU/GOLD/USTEC symbols, 0.0001 otherwise. This mirrors the bots'
    existing inline convention (it is not the canonical ADR-4 pip_size, which
    treats indices as 1.0); bot SL/TP distances are unchanged.
    """
    upper = (symbol or "").upper()
    if "XAU" in upper or "GOLD" in upper or "USTEC" in upper:
        return 0.10
    return 0.0001


def build_market_order(
    mt5: Any,
    *,
    symbol: str,
    order_type: Any,
    volume: float,
    price: float,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    deviation: int = 10,
    magic: int = 100001,
    comment: str = "",
    filling: Any = None,
) -> Dict[str, Any]:
    """Builds a TRADE_ACTION_DEAL open-order request (sl/tp omitted when None)."""
    request: Dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
    }
    if sl is not None:
        request["sl"] = sl
    if tp is not None:
        request["tp"] = tp
    request.update({
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling if filling is not None else mt5.ORDER_FILLING_IOC,
    })
    return request


def build_close_request(
    mt5: Any,
    *,
    symbol: str,
    volume: float,
    close_type: Any,
    position_ticket: int,
    price: float,
    deviation: int = 10,
    magic: int = 100001,
    comment: str = "",
) -> Dict[str, Any]:
    """Builds a TRADE_ACTION_DEAL position-close request."""
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "position": position_ticket,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }


_RETCODE_HINTS = {
    10009: "TRADE_RETCODE_DONE (Order executed cleanly)",
    10013: "TRADE_RETCODE_INVALID (Invalid order parameters)",
    10014: "TRADE_RETCODE_INVALID_VOLUME (Invalid lot size)",
    10015: "TRADE_RETCODE_INVALID_PRICE (Invalid entry price)",
    10016: "TRADE_RETCODE_INVALID_STOPS (Invalid SL or TP distance)",
    10019: "TRADE_RETCODE_NO_MONEY (Insufficient margin on MT5 account)",
    10027: "TRADE_RETCODE_AUTOTRADER_DISABLED (Algo Trading disabled in MT5 toolbar)",
}


def broker_reject_hint(retcode: Optional[int]) -> str:
    """Human-readable hint for a broker order retcode (shared wording)."""
    if retcode in _RETCODE_HINTS:
        return _RETCODE_HINTS[retcode]
    return f"Retcode {retcode if retcode is not None else 'None'}"
