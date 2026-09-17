from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.core.logging import logger
from app.core.pricing import pnl as spec_pnl, contract_size as spec_contract_size
from app.core.safety import (
    ensure_trading_allowed,
    destination_for_adapter,
    account_trade_mode_from_adapter,
    SafetyViolation,
)
from app.data.mt5_interface import AbstractMT5Adapter
from app.data.mt5_mock import MockMT5Adapter
from app.risk.engine import RiskEngine
from app.scalper.instrument import InstrumentSpecification

@dataclass
class PositionRecord:
    position_id: str
    client_order_id: str
    broker_ticket: Optional[int]
    symbol: str
    direction: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    floating_pnl: float
    realized_pnl: float
    r_multiple: float
    status: str  # "OPEN" or "CLOSED"
    entry_time: str
    exit_time: Optional[str]
    exit_reason: Optional[str]
    break_even_activated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ExecutionEngine:
    """Execution Engine managing order validation, idempotency, execution, and position management."""

    def __init__(
        self,
        adapter: Optional[AbstractMT5Adapter] = None,
        risk_engine: Optional[RiskEngine] = None,
    ):
        if adapter is None:
            adapter = MockMT5Adapter()
            adapter.connect()
        self.adapter = adapter
        # Explicit injection (R-06): reuse the injected shared RiskEngine;
        # only build a default when none is provided (standalone/test use).
        self.risk_engine = risk_engine if risk_engine is not None else RiskEngine()

        self.positions: Dict[str, PositionRecord] = {}
        self.executed_order_ids: set[str] = set()

        # Configurable Position Management Rules
        pm_config = settings.risk_config.get("position_management", {})
        self.break_even_enabled = pm_config.get("break_even_enabled", False)
        self.break_even_trigger_r = pm_config.get("break_even_trigger_r", 0.5)
        self.break_even_offset_pips = pm_config.get("break_even_offset_pips", 0.1)
        self.max_holding_time_seconds = pm_config.get("max_holding_time_seconds", 30)

    def execute_signal(self, signal_dict: Dict[str, Any], current_spread_pips: float = 1.0) -> Dict[str, Any]:
        """Executes a strategy signal after broker position sync, idempotency check, safety check, and risk approval."""
        import time
        start_time = time.perf_counter()

        symbol = signal_dict.get("symbol", "XAUUSD")
        client_order_id = signal_dict.get("client_signal_id") or f"ORD_{uuid.uuid4().hex[:8].upper()}"

        # 0. Direction validation (N2-H2): never silently map garbage to SELL.
        direction = str(signal_dict.get("direction", "")).strip().upper()
        if direction not in ("LONG", "SHORT"):
            logger.warning(f"DIRECTION REJECT: invalid direction {signal_dict.get('direction')!r}.")
            return {"status": "REJECTED", "reason": f"Invalid direction {signal_dict.get('direction')!r}: must be LONG or SHORT"}

        # 1. Idempotency Check: Prevent duplicate order execution
        if client_order_id in self.executed_order_ids:
            logger.warning(f"IDEMPOTENCY BLOCK: Order {client_order_id} has already been processed.")
            return {"status": "REJECTED", "reason": f"Duplicate order ID {client_order_id}"}

        # 2. Broker Position Sync (only blocks if a max-open limit is configured)
        broker_positions = self.adapter.get_open_positions(symbol)
        max_open = self.risk_engine.maximum_open_positions
        if max_open > 0 and len(broker_positions) >= max_open:
            logger.warning(f"BROKER POSITION BLOCK: {len(broker_positions)} active position(s) found on MT5 for {symbol}.")
            return {"status": "REJECTED", "reason": f"Active MT5 broker position exists for {symbol}"}


        # 3. Destination-aware safety gate (ADR-3): mode × destination × sentinel.
        # The gate consults the cross-process stop sentinel first (defense-in-depth
        # beyond the RiskEngine check below).
        destination = destination_for_adapter(self.adapter)
        try:
            ensure_trading_allowed(
                destination,
                account_trade_mode=account_trade_mode_from_adapter(self.adapter),
            )
        except SafetyViolation as exc:
            logger.warning(f"SAFETY GATE REJECT: {exc}")
            return {"status": "REJECTED", "reason": str(exc)}

        symbol_info = self.adapter.get_symbol_info(symbol) or {
            "digits": 2, "point_size": 0.01, "tick_size": 0.01, "tick_value": 1.0,
            "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01
        }
        account_info = self.adapter.get_account_info() or {"equity": 10000.0}

        open_pos_count = len([p for p in self.positions.values() if p.status == "OPEN"]) + len(broker_positions)

        # 4. Risk Engine Approval
        decision = self.risk_engine.evaluate_trade_risk(
            signal=signal_dict,
            account_info=account_info,
            symbol_info=symbol_info,
            current_open_positions_count=open_pos_count,
            current_spread_pips=current_spread_pips
        )

        if not decision.approved:
            logger.info(f"RISK REJECTION: {decision.rejection_reason}")
            return {"status": "REJECTED", "reason": decision.rejection_reason}

        # 5. Submit Order to Broker / Mock Adapter
        magic_number = signal_dict.get("magic", 888888)
        order_req = {
            "symbol": symbol,
            "volume": decision.calculated_volume,
            "price": signal_dict["entry_price"],
            "stop_loss": signal_dict["stop_loss"],
            "take_profit": signal_dict["take_profit"],
            "type": "BUY" if direction == "LONG" else "SELL",
            "magic": magic_number
        }

        broker_resp = self.adapter.send_order(order_req)
        if broker_resp is None:
            # N2-L1: a misbehaving adapter must yield FAILED, not AttributeError.
            logger.warning(f"BROKER RESPONSE: send_order returned None for {client_order_id}.")
            return {"status": "FAILED", "reason": "Broker order send returned no response"}
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Structured JSON Order Audit Logging
        audit_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "direction": direction,
            "requested_volume": decision.calculated_volume,
            "requested_price": signal_dict["entry_price"],
            "stop_loss": signal_dict["stop_loss"],
            "take_profit": signal_dict["take_profit"],
            "signal_id": client_order_id,
            "risk_decision": "APPROVED",
            "execution_mode": settings.EXECUTION_MODE.value,
            "magic_number": magic_number,
            "order_ticket": broker_resp.get("order"),
            "position_ticket": broker_resp.get("deal"),
            "broker_response": broker_resp.get("comment", "Success"),
            "latency_ms": latency_ms
        }
        logger.info(f"[ORDER_AUDIT] {audit_log}")

        if broker_resp.get("retcode") not in [10009, 0]:
            # N2-H3: FAILED must not poison idempotency — the ID is marked
            # only on EXECUTED so a legitimate retry can proceed.
            return {"status": "FAILED", "reason": broker_resp.get("comment", "Broker order send failed"), "audit": audit_log}

        # Mark order ID as processed (only fills consume ids) and record
        # the fill against today's risk counters (N2-H1).
        self.executed_order_ids.add(client_order_id)
        self.risk_engine.record_executed_trade()

        # 5. Record Open Position
        pos_id = f"POS_{uuid.uuid4().hex[:8].upper()}"
        pos = PositionRecord(
            position_id=pos_id,
            client_order_id=client_order_id,
            broker_ticket=broker_resp.get("order"),
            symbol=symbol,
            direction=direction,
            volume=decision.calculated_volume,
            entry_price=signal_dict["entry_price"],
            current_price=signal_dict["entry_price"],
            stop_loss=signal_dict["stop_loss"],
            take_profit=signal_dict["take_profit"],
            floating_pnl=0.0,
            realized_pnl=0.0,
            r_multiple=0.0,
            status="OPEN",
            entry_time=datetime.now(timezone.utc).isoformat(),
            exit_time=None,
            exit_reason=None,
            break_even_activated=False
        )
        self.positions[pos_id] = pos

        logger.info(f"ORDER EXECUTED: Position {pos_id} opened for {symbol} {direction} @ {signal_dict['entry_price']}")
        return {"status": "EXECUTED", "position": pos.to_dict()}

    def update_positions(self, current_prices: Dict[str, float], point_size: float = 0.01) -> List[Dict[str, Any]]:
        """Updates active positions with live prices, checks SL/TP hits, and applies Break-Even rules."""
        updated: List[Dict[str, Any]] = []

        # Broker symbol-info per symbol (ADR-4 precedence) for contract-aware
        # PnL and per-symbol point sizes (N2-M3: break-even must not assume
        # point 0.01 for every symbol).
        contract_sizes: Dict[str, float] = {}
        point_sizes: Dict[str, float] = {}
        price_digits: Dict[str, int] = {}

        def _symbol_precision(symbol: str) -> tuple:
            if symbol in point_sizes:
                return point_sizes[symbol], price_digits[symbol]
            resolved_point = point_size
            resolved_digits = 2
            try:
                info = self.adapter.get_symbol_info(symbol)
            except Exception as exc:
                logger.debug(f"symbol_info lookup failed for {symbol}: {exc}")
                info = None
            if info and info.get("point_size"):
                resolved_point = float(info["point_size"])
            if info and info.get("digits") is not None:
                resolved_digits = int(info["digits"])
            if not info or not info.get("point_size"):
                spec = InstrumentSpecification.get_default_spec(symbol)
                if spec is not None:
                    if not info or not info.get("point_size"):
                        resolved_point = spec.point_size
                    if not info or info.get("digits") is None:
                        resolved_digits = spec.digits
            point_sizes[symbol] = resolved_point
            price_digits[symbol] = resolved_digits
            return resolved_point, resolved_digits

        def _point_size_for(symbol: str) -> float:
            return _symbol_precision(symbol)[0]

        for pos_id, pos in list(self.positions.items()):
            if pos.status != "OPEN":
                continue

            closed = False
            curr_price = current_prices.get(pos.symbol, pos.current_price)
            pos.current_price = curr_price

            entry = pos.entry_price
            sl = pos.stop_loss
            direction = pos.direction
            vol = pos.volume
            risk_dist = abs(entry - sl)

            # Floating PnL calculation (spec-based contract size, P-04/C-01)
            price_diff = (curr_price - entry) if direction == "LONG" else (entry - curr_price)
            if pos.symbol not in contract_sizes:
                try:
                    info = self.adapter.get_symbol_info(pos.symbol)
                except Exception as exc:
                    logger.debug(f"symbol_info lookup failed for {pos.symbol}: {exc}")
                    info = None
                contract_sizes[pos.symbol] = spec_contract_size(pos.symbol, info)
            pos.floating_pnl = round(price_diff * contract_sizes[pos.symbol] * vol, 2)
            pos.r_multiple = round(price_diff / risk_dist, 2) if risk_dist > 0 else 0.0

            # Break-Even Adjustment Check
            if self.break_even_enabled and not pos.break_even_activated:
                if pos.r_multiple >= self.break_even_trigger_r:
                    sym_point, sym_digits = _symbol_precision(pos.symbol)
                    offset = self.break_even_offset_pips * sym_point
                    new_sl = round(entry + offset if direction == "LONG" else entry - offset, sym_digits)
                    pos.stop_loss = new_sl
                    pos.break_even_activated = True
                    logger.info(f"BREAK EVEN ACTIVATED: Position {pos_id} SL moved to {new_sl}")

            # Time stop: flatten scalps that overstay the holding window
            if not closed and self.max_holding_time_seconds and self.max_holding_time_seconds > 0:
                try:
                    entry_dt = datetime.fromisoformat(pos.entry_time.replace("Z", "+00:00"))
                    held_seconds = (datetime.now(timezone.utc) - entry_dt).total_seconds()
                    if held_seconds >= self.max_holding_time_seconds:
                        self._close_position(pos, curr_price, "MAX_HOLDING_TIME")
                        closed = True
                except (TypeError, ValueError) as exc:
                    # D-03: log skipped max-holding-time enforcement instead of
                    # silently skipping it.
                    logger.warning(
                        f"MAX_HOLDING_TIME skipped for {pos_id} "
                        f"(unparseable entry_time {pos.entry_time!r}): {exc}"
                    )

            # SL / TP Hit Check
            if not closed and direction == "LONG":
                if curr_price <= pos.stop_loss:
                    self._close_position(pos, pos.stop_loss, "STOP_LOSS")
                    closed = True
                elif curr_price >= pos.take_profit:
                    self._close_position(pos, pos.take_profit, "TAKE_PROFIT")
                    closed = True
            elif direction == "SHORT":
                if curr_price >= pos.stop_loss:
                    self._close_position(pos, pos.stop_loss, "STOP_LOSS")
                    closed = True
                elif curr_price <= pos.take_profit:
                    self._close_position(pos, pos.take_profit, "TAKE_PROFIT")
                    closed = True

            updated.append(pos.to_dict())

        return updated

    def _close_position(self, pos: PositionRecord, exit_price: float, reason: str) -> None:
        """Closes position and records realized PnL."""
        pos.status = "CLOSED"
        pos.exit_time = datetime.now(timezone.utc).isoformat()
        pos.exit_reason = reason
        price_diff = (exit_price - pos.entry_price) if pos.direction == "LONG" else (pos.entry_price - exit_price)
        # Spec-based contract size (P-04/C-01); broker symbol_info takes precedence.
        info = None
        try:
            info = self.adapter.get_symbol_info(pos.symbol)
        except Exception as exc:
            logger.debug(f"symbol_info lookup failed for {pos.symbol}: {exc}")
            info = None
        pos.realized_pnl = round(spec_pnl(price_diff, pos.volume, pos.symbol, symbol_info=info), 2)
        pos.floating_pnl = 0.0
        self.risk_engine.record_closed_trade(pos.realized_pnl)
        logger.info(f"POSITION CLOSED: {pos.position_id} exited @ {exit_price} ({reason}). Realized PnL: ${pos.realized_pnl}")

    def close_all_positions(self, reason: str = "EMERGENCY_CLOSE_ALL") -> List[Dict[str, Any]]:
        """Emergency closes all active positions immediately."""
        closed_list = []
        for pos_id, pos in list(self.positions.items()):
            if pos.status == "OPEN":
                self._close_position(pos, pos.current_price, reason)
                closed_list.append(pos.to_dict())
        return closed_list
