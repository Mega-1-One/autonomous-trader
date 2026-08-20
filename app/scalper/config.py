from dataclasses import dataclass

@dataclass
class SmallAccountDemoConfig:
    """Configurable profile for small-account scalping evaluation."""
    profile_name: str = "SMALL_ACCOUNT_DEMO"
    risk_per_trade_pct: float = 0.1          # Micro-scalp risk (0.1% per trade)
    maximum_daily_loss_pct: float = 0.0        # 0 = Disabled (unlimited continuous scalping)
    maximum_trades_per_day: int = 0            # 0 = Unlimited trades per day
    maximum_open_positions: int = 0            # 0 = Unlimited concurrent scalps
    maximum_spread_pips: float = 0.0           # 0 = Disabled
    minimum_rr: float = 0.0                    # 0 = Disabled (fast scalp profit taking)
    maximum_holding_seconds: int = 30          # Sub-minute scalping target
    cooldown_seconds: int = 0                  # Instant execution on setup
    maximum_consecutive_losses: int = 0        # 0 = Disabled (no artificial lockout)
