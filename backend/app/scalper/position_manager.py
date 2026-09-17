from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
import time

from app.core.logging import logger
from app.core.pricing import pnl as spec_pnl

@dataclass
class ScalpPosition:
    position_id: str
    symbol: str
    direction: str            # "BUY" or "SELL"
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    entry_time: float         # Unix timestamp
    status: str               # "OPEN" or "CLOSED"
    floating_pnl: float = 0.0
    realized_pnl: float = 0.0
    holding_time_seconds: float = 0.0
    exit_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ScalpPositionManager:
    """Monitors live scalping positions, micro SL/TP hits, momentum reversals, and maximum holding times."""

    def __init__(self, max_holding_seconds: float = 30.0):
        self.max_holding_seconds = max_holding_seconds
        self.positions: Dict[str, ScalpPosition] = {}

    def add_position(self, pos: ScalpPosition) -> None:
        self.positions[pos.position_id] = pos

    def update_and_check_exits(
        self,
        current_bid: float,
        current_ask: float,
        momentum_reversal: bool = False,
        now: Optional[float] = None,
        symbol_info: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[ScalpPosition]:
        """Updates positions and checks exits.

        ``symbol_info`` optionally maps symbol -> broker symbol-info dict so
        PnL uses broker contract precedence (ADR-4); without it the static
        spec applies (N2-M4).
        """
        if now is None:
            now = time.time()
        broker_info = symbol_info or {}

        closed_positions = []

        for pos in list(self.positions.values()):
            if pos.status != "OPEN":
                continue

            curr_price = current_bid if pos.direction == "BUY" else current_ask
            pos.current_price = curr_price
            pos.holding_time_seconds = round(now - pos.entry_time, 2)

            price_diff = (curr_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - curr_price)
            pos.floating_pnl = round(
                spec_pnl(price_diff, pos.volume, pos.symbol,
                         symbol_info=broker_info.get(pos.symbol)), 2)

            # 1. Take Profit Hit
            if (pos.direction == "BUY" and curr_price >= pos.take_profit) or \
               (pos.direction == "SELL" and curr_price <= pos.take_profit):
                self._close_pos(pos, pos.take_profit, "TAKE_PROFIT", now, broker_info)
                closed_positions.append(pos)
                continue

            # 2. Stop Loss Hit
            if (pos.direction == "BUY" and curr_price <= pos.stop_loss) or \
               (pos.direction == "SELL" and curr_price >= pos.stop_loss):
                self._close_pos(pos, pos.stop_loss, "STOP_LOSS", now, broker_info)
                closed_positions.append(pos)
                continue

            # 3. Time Exit
            if pos.holding_time_seconds >= self.max_holding_seconds:
                self._close_pos(pos, curr_price, "TIME_EXIT", now, broker_info)
                closed_positions.append(pos)
                continue

            # 4. Momentum Reversal Exit
            if momentum_reversal:
                self._close_pos(pos, curr_price, "MOMENTUM_REVERSAL", now, broker_info)
                closed_positions.append(pos)
                continue

        return closed_positions

    def _close_pos(self, pos: ScalpPosition, exit_price: float, reason: str, now: float,
                   broker_info: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        pos.status = "CLOSED"
        pos.exit_reason = reason
        pos.holding_time_seconds = round(now - pos.entry_time, 2)
        price_diff = (exit_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - exit_price)
        info = (broker_info or {}).get(pos.symbol)
        pos.realized_pnl = round(spec_pnl(price_diff, pos.volume, pos.symbol, symbol_info=info), 2)
        pos.floating_pnl = 0.0
        logger.info(f"[SCALP_POSITION_CLOSED] {pos.position_id} exited @ {exit_price} ({reason}). Realized PnL: ${pos.realized_pnl} (Held: {pos.holding_time_seconds}s)")
