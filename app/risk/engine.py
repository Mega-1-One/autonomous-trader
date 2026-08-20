import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.logging import logger

@dataclass
class RiskDecision:
    approved: bool
    rejection_reason: Optional[str]
    calculated_volume: float
    monetary_risk: float
    risk_percent: float
    effective_rr: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class RiskEngine:
    """Quantitative Risk Engine enforcing strict position sizing, risk thresholds, and broker safety checks."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = settings.risk_config.get("risk_rules", {})

        # 0 disables a limit so scalps can fire whenever a setup appears.
        self.risk_per_trade_percent = config.get("risk_per_trade_percent", 0.1)
        self.maximum_daily_loss_percent = config.get("maximum_daily_loss_percent", 0)
        self.maximum_trades_per_day = config.get("maximum_trades_per_day", 0)
        self.maximum_open_positions = config.get("maximum_open_positions", 0)
        self.maximum_spread_pips = config.get("maximum_spread_pips", 0)
        self.minimum_rr = config.get("minimum_rr", 0)
        self.maximum_position_size_lots = config.get("maximum_position_size_lots", 10.0)
        self.minimum_position_size_lots = config.get("minimum_position_size_lots", 0.01)

        self.emergency_stop_active = False
        self.daily_lock_active = False
        self.daily_lock_reason: Optional[str] = None
        self.today_trade_count = 0
        self.today_realized_pnl = 0.0

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        symbol_info: Dict[str, Any]
    ) -> float:
        """Calculates precise position volume based on contract specifications and risk percentage."""
        if equity <= 0 or entry_price <= 0 or stop_loss <= 0:
            return 0.0

        price_risk = abs(entry_price - stop_loss)
        if price_risk <= 0:
            return 0.0

        tick_size = symbol_info.get("tick_size", 0.01)
        tick_value = symbol_info.get("tick_value", 1.0)
        min_vol = symbol_info.get("min_volume", self.minimum_position_size_lots)
        max_vol = symbol_info.get("max_volume", self.maximum_position_size_lots)
        vol_step = symbol_info.get("volume_step", 0.01)

        monetary_risk = equity * (self.risk_per_trade_percent / 100.0)
        ticks_at_risk = price_risk / tick_size
        risk_per_contract = ticks_at_risk * tick_value

        if risk_per_contract <= 0:
            return 0.0

        raw_volume = monetary_risk / risk_per_contract

        # Snap volume to broker volume step
        steps = math.floor(raw_volume / vol_step)
        snapped_volume = round(steps * vol_step, 4)

        # Clamp volume to broker min/max boundaries
        clamped_volume = max(min_vol, min(max_vol, snapped_volume))
        return float(clamped_volume)

    def evaluate_trade_risk(
        self,
        signal: Dict[str, Any],
        account_info: Dict[str, Any],
        symbol_info: Dict[str, Any],
        current_open_positions_count: int = 0,
        current_spread_pips: float = 1.0
    ) -> RiskDecision:
        """Evaluates trade setup against all active risk limits."""
        # 1. Global Emergency Stop Check
        if self.emergency_stop_active:
            return RiskDecision(
                approved=False,
                rejection_reason="Emergency Stop is currently ACTIVE. All new entries blocked.",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        # 2. Daily Risk Lock Check
        if self.daily_lock_active:
            return RiskDecision(
                approved=False,
                rejection_reason=f"Daily Risk Lock ACTIVE ({self.daily_lock_reason}).",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        equity = account_info.get("equity", 10000.0)
        entry_price = signal.get("entry_price", 0.0)
        stop_loss = signal.get("stop_loss", 0.0)
        take_profit = signal.get("take_profit", 0.0)

        # 3. Daily Loss Check (disabled when maximum_daily_loss_percent is 0)
        if self.maximum_daily_loss_percent > 0:
            max_daily_loss_amount = equity * (self.maximum_daily_loss_percent / 100.0)
            if self.today_realized_pnl <= -max_daily_loss_amount:
                self.daily_lock_active = True
                self.daily_lock_reason = f"Daily loss limit ({self.maximum_daily_loss_percent}%) reached"
                return RiskDecision(
                    approved=False,
                    rejection_reason=self.daily_lock_reason,
                    calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
                )

        # 4. Max Trades Per Day Check (disabled when maximum_trades_per_day is 0)
        if self.maximum_trades_per_day > 0 and self.today_trade_count >= self.maximum_trades_per_day:
            return RiskDecision(
                approved=False,
                rejection_reason=f"Maximum trades per day ({self.maximum_trades_per_day}) reached.",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        # 5. Max Open Positions Check (disabled when maximum_open_positions is 0)
        if self.maximum_open_positions > 0 and current_open_positions_count >= self.maximum_open_positions:
            return RiskDecision(
                approved=False,
                rejection_reason=f"Maximum open positions limit ({self.maximum_open_positions}) reached.",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        # 6. Spread Check (disabled when maximum_spread_pips is 0)
        if self.maximum_spread_pips > 0 and current_spread_pips > self.maximum_spread_pips:
            return RiskDecision(
                approved=False,
                rejection_reason=f"Current spread ({current_spread_pips} pips) exceeds max allowed ({self.maximum_spread_pips} pips).",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        # 7. Risk/Reward Check
        risk_dist = abs(entry_price - stop_loss)
        reward_dist = abs(take_profit - entry_price)
        if risk_dist <= 0:
            return RiskDecision(
                approved=False,
                rejection_reason="Invalid stop loss price (zero distance to entry).",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=0.0
            )

        effective_rr = round(reward_dist / risk_dist, 2)
        if self.minimum_rr > 0 and effective_rr < self.minimum_rr:
            return RiskDecision(
                approved=False,
                rejection_reason=f"Risk/Reward ratio ({effective_rr}) below configured minimum ({self.minimum_rr}).",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=effective_rr
            )

        # 8. Position Sizing Calculation
        volume = self.calculate_position_size(equity, entry_price, stop_loss, symbol_info)
        monetary_risk = equity * (self.risk_per_trade_percent / 100.0)

        if volume <= 0:
            return RiskDecision(
                approved=False,
                rejection_reason="Calculated position volume is zero or below minimum broker constraint.",
                calculated_volume=0.0, monetary_risk=0.0, risk_percent=0.0, effective_rr=effective_rr
            )

        return RiskDecision(
            approved=True,
            rejection_reason=None,
            calculated_volume=volume,
            monetary_risk=round(monetary_risk, 2),
            risk_percent=self.risk_per_trade_percent,
            effective_rr=effective_rr
        )

    def trigger_emergency_stop(self, reason: str = "User Initiated Emergency Stop") -> None:
        """Triggers global emergency stop blocking all future entries."""
        self.emergency_stop_active = True
        logger.critical(f"GLOBAL EMERGENCY STOP ACTIVATED: {reason}")

    def reset_emergency_stop(self) -> None:
        """Resets global emergency stop."""
        self.emergency_stop_active = False
        logger.info("Global Emergency Stop has been reset.")
