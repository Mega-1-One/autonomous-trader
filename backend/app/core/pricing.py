"""Instrument pricing primitives (ADR-4).

Precedence rule (ADR-4):
    broker ``symbol_info`` overrides the static ``InstrumentSpecification``
    for point/tick/contract/volume fields; ``pip_size`` is canonical in the
    specification (gold 0.1, 5-digit FX 0.0001, JPY FX 0.01); a digits-derived
    fallback applies only when no specification exists for a symbol.

The mock adapter's digits=2 XAU spec describes the *mock environment* and is
not rewritten by this module; callers that hold broker symbol_info pass it via
the ``info`` parameter to override contract-size and point fields.
"""
from typing import Any, Dict, Optional

from app.scalper.instrument import InstrumentSpecification


def get_spec(symbol: str) -> Optional[InstrumentSpecification]:
    """Canonical static specification for a symbol (or None for unknown)."""
    return InstrumentSpecification.get_default_spec(symbol)


def pip_size(symbol: str, point_size: Optional[float] = None) -> float:
    """Canonical pip size for a symbol.

    Precedence: the static spec's pip_size is canonical (gold 0.1, 5-digit FX
    0.0001, JPY 0.01). Only when no spec exists does a digits-derived fallback
    (point_size * 10) apply.
    """
    spec = get_spec(symbol)
    if spec is not None and spec.pip_size > 0:
        return spec.pip_size
    if point_size and point_size > 0:
        return point_size * 10.0
    return 0.0001


def spread_in_pips(bid: float, ask: float, symbol: str = "",
                   digits: Optional[int] = None,
                   point_size: Optional[float] = None) -> float:
    """Spread in pips.

    If ``symbol`` resolves to a specification, the canonical ``pip_size`` is
    used (ADR-4). Otherwise the legacy digits-derived rules are kept so legacy
    callers without a symbol retain their exact prior behavior:
    digits==3 gold-style -> point*100; digits==5 FX-style -> point*10; other
    digits -> per-point.
    """
    if symbol:
        spec = get_spec(symbol)
        if spec is not None and spec.pip_size > 0:
            return round(abs(ask - bid) / spec.pip_size, 1)
    # Legacy digits-derived fallback (pre-B-02 behavior for symbol-less callers)
    raw_diff = abs(ask - bid)
    if digits == 3:
        return round(raw_diff / ((point_size or 0.001) * 100.0), 1)
    elif digits == 5:
        return round(raw_diff / ((point_size or 0.00001) * 10.0), 1)
    else:
        return round(raw_diff / (point_size or 0.01), 1)


def contract_size(symbol: str, symbol_info: Optional[Dict[str, Any]] = None) -> float:
    """Contract size with broker symbol_info precedence over the static spec."""
    info_cs = (symbol_info or {}).get("contract_size")
    if info_cs and info_cs > 0:
        return float(info_cs)
    spec = get_spec(symbol)
    if spec is not None:
        return spec.contract_size
    info_point = (symbol_info or {}).get("point_size")
    if info_point:
        # Digits/point-derived fallback for unknown symbols
        return 100.0 if info_point >= 0.01 else 100000.0
    return 100000.0


def pnl(price_diff: float, volume: float, symbol: str,
        symbol_info: Optional[Dict[str, Any]] = None) -> float:
    """Raw monetary PnL for a closed position.

    ``price_diff`` is (exit - entry) for LONG and (entry - exit) for SHORT.
    Contract size precedence: broker ``symbol_info`` > static spec.
    """
    return price_diff * contract_size(symbol, symbol_info) * volume


def pips_to_price(pips: float, symbol: str) -> float:
    """Convert a pip distance to a price distance using the canonical pip size."""
    return pips * pip_size(symbol)
