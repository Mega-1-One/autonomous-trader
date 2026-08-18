import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings, ExecutionMode
from app.core.logging import logger
from app.scalper.signal import ScalpSignal
from app.scalper.position_manager import ScalpPosition, ScalpPositionManager
from app.scalper.cooldown import CooldownManager

class ScalpPaperExecutionEngine:
    """High-speed Paper Execution Router capturing signal-to-order latency and simulated fills."""

    def __init__(self, position_manager: Optional[ScalpPositionManager] = None):
        if position_manager is None:
            position_manager = ScalpPositionManager(max_holding_seconds=30.0)
        self.position_manager = position_manager
        self.cooldown_manager = CooldownManager(cooldown_seconds=15, max_consecutive_losses=3)

    def execute_scalp_opportunity(
        self,
        signal: ScalpSignal,
        opportunity_score: float,
        calculated_volume: float = 0.05,
        slippage_pips: float = 0.1
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        now = time.time()

        # 1. Cooldown & Lockout Check
        if self.cooldown_manager.locked:
            return {"status": "REJECTED", "reason": self.cooldown_manager.lock_reason}

        if self.cooldown_manager.is_in_cooldown(now):
            return {"status": "REJECTED", "reason": "Trade cooldown active"}

        # 2. Check Open Position Limit
        open_positions = [p for p in self.position_manager.positions.values() if p.status == "OPEN"]
        if len(open_positions) >= 1:
            return {"status": "REJECTED", "reason": "Max open position limit (1) reached"}

        # 3. Simulate Fill & Latency Measurement
        fill_price = signal.entry_reference
        if signal.direction == "BUY":
            fill_price += (slippage_pips * 0.01)
        elif signal.direction == "SELL":
            fill_price -= (slippage_pips * 0.01)

        pos_id = f"SCALP_{uuid.uuid4().hex[:8].upper()}"
        pos = ScalpPosition(
            position_id=pos_id,
            symbol=signal.symbol,
            direction=signal.direction,
            volume=calculated_volume,
            entry_price=round(fill_price, 3),
            current_price=round(fill_price, 3),
            stop_loss=signal.stop_reference,
            take_profit=signal.target_reference,
            entry_time=now,
            status="OPEN"
        )
        self.position_manager.add_position(pos)

        total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 3)

        audit_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "PAPER_POSITION_OPENED",
            "symbol": signal.symbol,
            "direction": signal.direction,
            "opportunity_score": opportunity_score,
            "requested_price": signal.entry_reference,
            "fill_price": pos.entry_price,
            "volume": calculated_volume,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "signal_id": signal.signal_id,
            "position_id": pos_id,
            "latency_ms": total_latency_ms
        }
        logger.info(f"[PAPER_EXECUTION] {audit_log}")

        return {
            "status": "EXECUTED",
            "mode": "PAPER",
            "position": pos.to_dict(),
            "latency_ms": total_latency_ms,
            "audit": audit_log
        }
