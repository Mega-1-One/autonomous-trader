from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

@dataclass
class DynamicSymbolSpecification:
    symbol: str
    canonical_name: str
    digits: int
    point_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    spread_pips: float
    trade_mode: str = "FULL_ACCESS"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class OrderRequest:
    client_order_id: str
    symbol: str
    order_type: OrderType
    volume: float
    requested_price: float
    stop_loss: float
    take_profit: float
    magic_number: int = 888888
    comment: str = "AutonomousExecution"
    slippage_points: int = 10

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["order_type"] = self.order_type.value
        return d

@dataclass
class OrderResult:
    client_order_id: str
    status: OrderStatus
    broker_ticket: Optional[int]
    fill_price: float
    fill_volume: float
    slippage_cost: float
    commission_cost: float
    spread_cost: float
    latency_ms: float
    rejection_reason: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

@dataclass
class AccountState:
    login: int
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    leverage: int
    is_live: bool = False
    connected: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
