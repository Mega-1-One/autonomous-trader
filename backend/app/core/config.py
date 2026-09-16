import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Autonomous Trader"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "default-insecure-secret-key-change-in-prod"

    # Execution & Safety Flags
    EXECUTION_MODE: ExecutionMode = ExecutionMode.PAPER
    ENABLE_LIVE_TRADING: bool = False
    LIVE_TRADING_CONFIRMATION: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"

    # MT5 Credentials
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None
    MT5_PATH: Optional[str] = None

    # Config directory path
    CONFIG_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "config"

    # State directory for cross-process files (e.g. the emergency-stop sentinel).
    # Env vars: AUTOTRADER_STATE_DIR (preferred) or STATE_DIR
    STATE_DIR: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent / "state",
        validation_alias=AliasChoices("AUTOTRADER_STATE_DIR", "STATE_DIR"),
    )

    strategy_config: Dict[str, Any] = Field(default_factory=dict)
    risk_config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_safety_flags(self) -> "Settings":
        """Enforces critical safety principle: NEVER enable live trading automatically."""
        if self.EXECUTION_MODE == ExecutionMode.LIVE:
            if not (self.ENABLE_LIVE_TRADING and self.LIVE_TRADING_CONFIRMATION):
                raise ValueError(
                    "CRITICAL SAFETY VIOLATION: Execution mode LIVE requires both "
                    "ENABLE_LIVE_TRADING=true AND LIVE_TRADING_CONFIRMATION=true."
                )
        return self

    def load_yaml_configs(self) -> None:
        """Loads strategy.yaml and risk.yaml from config directory if present."""
        strategy_path = self.CONFIG_DIR / "strategy.yaml"
        risk_path = self.CONFIG_DIR / "risk.yaml"

        if strategy_path.exists():
            with open(strategy_path, "r", encoding="utf-8") as f:
                self.strategy_config = yaml.safe_load(f) or {}

        if risk_path.exists():
            with open(risk_path, "r", encoding="utf-8") as f:
                self.risk_config = yaml.safe_load(f) or {}

def get_settings() -> Settings:
    settings = Settings()
    settings.load_yaml_configs()
    return settings

settings = get_settings()
