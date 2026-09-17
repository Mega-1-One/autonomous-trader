from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

class Account(Base):
    __tablename__ = "accounts"

    login: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    broker: Mapped[str] = mapped_column(String(100), nullable=False)
    server: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    leverage: Mapped[int] = mapped_column(Integer, default=100)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)

class Symbol(Base):
    __tablename__ = "symbols"

    canonical_name: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False) # e.g. XAUUSD
    broker_name: Mapped[str] = mapped_column(String(20), nullable=False) # e.g. XAUUSDm
    digits: Mapped[int] = mapped_column(Integer, default=2)
    point_size: Mapped[float] = mapped_column(Float, default=0.01)
    tick_size: Mapped[float] = mapped_column(Float, default=0.01)
    tick_value: Mapped[float] = mapped_column(Float, default=1.0)
    contract_size: Mapped[float] = mapped_column(Float, default=100.0)
    min_volume: Mapped[float] = mapped_column(Float, default=0.01)
    max_volume: Mapped[float] = mapped_column(Float, default=100.0)
    volume_step: Mapped[float] = mapped_column(Float, default=0.01)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class StrategyConfigModel(Base):
    __tablename__ = "strategy_configs"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)

class RiskConfigModel(Base):
    __tablename__ = "risk_configs"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)

class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=0.0)

class SignalModel(Base):
    __tablename__ = "signals"

    client_signal_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False) # LONG / SHORT
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    setup_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="DETECTED") # DETECTED, APPROVED, REJECTED, EXECUTED, EXPIRED
    reasons: Mapped[dict] = mapped_column(JSON, nullable=False)

class OrderModel(Base):
    __tablename__ = "orders"

    client_order_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    broker_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False) # BUY, SELL, BUY_LIMIT, etc.
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    execution_mode: Mapped[str] = mapped_column(String(10), default="PAPER")

class PositionModel(Base):
    __tablename__ = "positions"

    position_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    broker_ticket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    floating_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="OPEN") # OPEN, CLOSED

class TradeModel(Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    r_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(50), nullable=False) # SL, TP, TRAILING_STOP, BE, MANUAL, EMERGENCY

class SystemEvent(Base):
    __tablename__ = "system_events"

    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="INFO") # INFO, WARNING, ERROR, CRITICAL
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

class RiskEvent(Base):
    __tablename__ = "risk_events"

    rule_violated: Mapped[str] = mapped_column(String(100), nullable=False)
    action_taken: Mapped[str] = mapped_column(String(100), nullable=False) # REJECT_ORDER, LOCK_TRADING, EMERGENCY_CLOSE
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
