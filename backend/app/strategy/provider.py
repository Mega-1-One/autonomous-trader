"""Strategy/platform decision contract (strategy-independence refactor, E1).

The platform depends on this contract — a plain validated dict — rather than
on any strategy implementation. Concrete strategies live behind
:class:`StrategyProvider`; this module itself imports nothing strategy-specific.

Contract (APPROVED decision):
  symbol, direction ∈ {"LONG", "SHORT"}, entry_price, stop_loss, take_profit,
  client_signal_id, status == "APPROVED",
  plus opaque strategy-owned extras (setup_type, confidence, reasons, ...).

REJECTED decisions carry status == "REJECTED" and a rejection_reason and never
reach risk approval. Direction/price rules apply to APPROVED decisions only.
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

APPROVED = "APPROVED"
REJECTED = "REJECTED"

LONG = "LONG"
SHORT = "SHORT"

DIRECTIONS = (LONG, SHORT)


class ContractViolation(ValueError):
    """A strategy output that does not satisfy the platform decision contract."""


def validate_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Validates a strategy output dict against the platform contract.

    Returns the dict unchanged when valid; raises ContractViolation otherwise.
    """
    if not isinstance(decision, dict):
        raise ContractViolation(f"decision must be a dict, got {type(decision).__name__}")
    status = decision.get("status")
    if status not in (APPROVED, REJECTED):
        raise ContractViolation(f"status must be APPROVED/REJECTED, got {status!r}")
    if status == REJECTED:
        reasons = decision.get("reasons") or {}
        if not isinstance(reasons, dict) or not reasons.get("rejection_reason"):
            raise ContractViolation("REJECTED decisions must carry reasons.rejection_reason")
        return decision
    direction = decision.get("direction")
    if direction not in DIRECTIONS:
        raise ContractViolation(f"APPROVED direction must be LONG/SHORT, got {direction!r}")
    for key in ("entry_price", "stop_loss", "take_profit"):
        value = decision.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ContractViolation(f"{key} must be a positive finite price, got {value!r}")
    entry, sl, tp = decision["entry_price"], decision["stop_loss"], decision["take_profit"]
    if direction == LONG and not (sl < entry < tp):
        raise ContractViolation(f"LONG requires stop < entry < take profit, got {sl}/{entry}/{tp}")
    if direction == SHORT and not (sl > entry > tp):
        raise ContractViolation(f"SHORT requires stop > entry > take profit, got {sl}/{entry}/{tp}")
    signal_id = decision.get("client_signal_id")
    if not isinstance(signal_id, str) or not signal_id:
        raise ContractViolation("client_signal_id must be a non-empty string")
    symbol = decision.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ContractViolation("symbol must be a non-empty string")
    return decision


@dataclass
class MarketInputs:
    """What the platform hands a strategy: candles per timeframe + point size.

    The strategy declares which timeframe keys it needs (today: "HTF"/"LTF");
    callers assemble them. Strategies must not fetch market data themselves.
    """
    symbol: str
    candles: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    point_size: float = 0.01


class StrategyProvider(ABC):
    """Minimal seam between platform and any strategy implementation."""

    #: registry name, e.g. "ict_scalp"
    name: str = "base"

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}

    def configure(self, config: Optional[Dict[str, Any]]) -> None:
        """Receives the strategy's OWN config section only (E4)."""
        self._config = dict(config or {})

    @abstractmethod
    def evaluate(self, inputs: MarketInputs) -> Dict[str, Any]:
        """Produces a raw decision dict (validated by the caller via validate_decision)."""

    def describe(
        self,
        *,
        symbol: str,
        candles: List[Dict[str, Any]],
        timeframe: str = "M5",
        point_size: float = 0.01,
        **options: Any,
    ) -> Optional[Dict[str, Any]]:
        """Optional human-readable market analysis for dashboards.

        Returns None when the strategy offers no analysis pages; routers turn
        that into a 404. Option keys are provider-defined (the ICT provider
        accepts swing_lookback/confirm_on_close/tolerance_pips).
        """
        return None


_PROVIDER_REGISTRY: Dict[str, Callable[[], StrategyProvider]] = {}


def register_provider(name: str, factory: Callable[[], StrategyProvider]) -> None:
    """Registers a provider factory under a config name."""
    _PROVIDER_REGISTRY[name] = factory


def registered_providers() -> List[str]:
    return sorted(_PROVIDER_REGISTRY)


def resolve_strategy_config(
    strategy_config: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Splits routing keys from the strategy's own config section (E4).

    Rule: if ``strategies.<name>`` exists it is used verbatim (isolated —
    future strategies never see ICT keys); otherwise the legacy ``ict_scalp``
    default receives the full top-level dict unchanged (zero behavior delta).
    Anything else is an error, not a silent fallback.
    """
    cfg = dict(strategy_config or {})
    key = name or cfg.get("name", "ict_scalp")
    sections = cfg.get("strategies")
    if isinstance(sections, dict) and isinstance(sections.get(key), dict):
        return key, sections[key]
    if key == "ict_scalp":
        return key, cfg
    raise ContractViolation(
        f"unknown strategy {key!r}; registered: {registered_providers()}"
    )


def create_provider(name: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> StrategyProvider:
    """Builds the configured provider (default: "ict_scalp")."""
    key = name or "ict_scalp"
    try:
        factory = _PROVIDER_REGISTRY[key]
    except KeyError:
        raise ContractViolation(
            f"unknown strategy {key!r}; registered: {registered_providers()}"
        ) from None
    provider = factory()
    provider.configure(config)
    return provider


def evaluate_strategy(
    provider: StrategyProvider,
    inputs: MarketInputs,
) -> Dict[str, Any]:
    """Runs a provider and enforces the decision contract on its output."""
    return validate_decision(provider.evaluate(inputs))
