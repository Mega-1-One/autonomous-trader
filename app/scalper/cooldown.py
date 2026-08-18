import time

class CooldownManager:
    """Manages trade cooldowns, consecutive loss counters, and strategy lockouts."""

    def __init__(self, cooldown_seconds: int = 15, max_consecutive_losses: int = 3):
        self.cooldown_seconds = cooldown_seconds
        self.max_consecutive_losses = max_consecutive_losses
        self.last_trade_time: float = 0.0
        self.consecutive_losses: int = 0
        self.locked: bool = False
        self.lock_reason: str = ""

    def is_in_cooldown(self, now: float) -> bool:
        return (now - self.last_trade_time) < self.cooldown_seconds

    def record_trade_result(self, realized_pnl: float, now: float) -> None:
        self.last_trade_time = now
        if realized_pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.locked = True
                self.lock_reason = f"Locked out after {self.consecutive_losses} consecutive losses"
        else:
            self.consecutive_losses = 0

    def reset_lockout(self) -> None:
        self.locked = False
        self.consecutive_losses = 0
        self.lock_reason = ""

