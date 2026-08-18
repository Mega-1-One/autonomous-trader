from dataclasses import dataclass

@dataclass
class SmallAccountDemoConfig:
    """Configurable profile for small-account scalping evaluation."""
    profile_name: str = "SMALL_ACCOUNT_DEMO"
    risk_per_trade_pct: float = 0.25         # Conservative 0.25% risk per trade
    maximum_daily_loss_pct: float = 2.0        # Max 2% daily loss before lock
    maximum_trades_per_day: int = 50           # Scalping trade count limit
    maximum_open_positions: int = 1            # Single position at a time
    maximum_spread_pips: float = 3.0           # Max allowed spread
    minimum_rr: float = 1.5                    # Minimum Risk/Reward ratio
    maximum_holding_seconds: int = 30          # Sub-minute scalping target
    cooldown_seconds: int = 15                 # Minimum pause between trades
    maximum_consecutive_losses: int = 3        # Lock strategy after 3 consecutive losses
