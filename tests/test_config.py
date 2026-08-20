import pytest
from pydantic import ValidationError
from app.core.config import Settings, ExecutionMode

def test_default_config_safety_mode():
    settings = Settings()
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_live_trading_safety_gate_rejection():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            EXECUTION_MODE=ExecutionMode.LIVE,
            ENABLE_LIVE_TRADING=False,
            LIVE_TRADING_CONFIRMATION=False
        )
    assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)

def test_live_trading_partial_confirmation_rejection():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            EXECUTION_MODE=ExecutionMode.LIVE,
            ENABLE_LIVE_TRADING=True,
            LIVE_TRADING_CONFIRMATION=False
        )
    assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)

def test_live_trading_explicit_approval_success():
    settings = Settings(
        EXECUTION_MODE=ExecutionMode.LIVE,
        ENABLE_LIVE_TRADING=True,
        LIVE_TRADING_CONFIRMATION=True
    )
    assert settings.EXECUTION_MODE == ExecutionMode.LIVE
    assert settings.ENABLE_LIVE_TRADING is True
    assert settings.LIVE_TRADING_CONFIRMATION is True

def test_load_yaml_configs():
    settings = Settings()
    settings.load_yaml_configs()
    assert "market_structure" in settings.strategy_config
    assert "risk_rules" in settings.risk_config
    assert settings.strategy_config["market_structure"]["swing_lookback"] == 3
    assert settings.risk_config["risk_rules"]["risk_per_trade_percent"] in [0.1, 0.5]
