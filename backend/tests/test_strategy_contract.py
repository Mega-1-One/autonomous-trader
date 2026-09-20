"""E1: StrategyDecision contract tests (strategy/platform boundary)."""
import math

import pytest

from app.strategy.provider import (
    APPROVED,
    REJECTED,
    ContractViolation,
    MarketInputs,
    StrategyProvider,
    create_provider,
    evaluate_strategy,
    registered_providers,
    register_provider,
    validate_decision,
)


def _approved(**overrides):
    base = {
        "client_signal_id": "SIG_1",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2399.7,
        "take_profit": 2400.5,
        "status": APPROVED,
        "setup_type": "ANYTHING",
        "confidence": 0.5,
        "reasons": {},
    }
    base.update(overrides)
    return base


def test_valid_long_and_short_pass_through_unchanged():
    d = _approved()
    assert validate_decision(d) is d
    short = _approved(direction="SHORT", entry_price=2400.0,
                      stop_loss=2400.3, take_profit=2399.5)
    assert validate_decision(short) is short


def test_opaque_extras_preserved():
    d = _approved(setup_type="SOME_FUTURE_SETUP", confidence=0.99,
                  reasons={"nested": {"arbitrary": [1, 2]}})
    assert validate_decision(d)["setup_type"] == "SOME_FUTURE_SETUP"


def test_non_dict_rejected():
    with pytest.raises(ContractViolation):
        validate_decision(["not", "a", "dict"])


def test_bad_status_rejected():
    with pytest.raises(ContractViolation):
        validate_decision(_approved(status="MAYBE"))


@pytest.mark.parametrize("direction", ["BUY", "SELL", "NEUTRAL", "NONE", "FLAT", "long", "", None])
def test_approved_bad_direction_rejected(direction):
    with pytest.raises(ContractViolation):
        validate_decision(_approved(direction=direction))


@pytest.mark.parametrize("key,value", [
    ("entry_price", 0.0), ("entry_price", -1.0),
    ("stop_loss", 0.0), ("take_profit", -5.0),
    ("entry_price", math.nan), ("stop_loss", math.inf),
    ("take_profit", "2400.5"), ("entry_price", None),
])
def test_approved_bad_prices_rejected(key, value):
    with pytest.raises(ContractViolation):
        validate_decision(_approved(**{key: value}))


def test_approved_missided_stops_rejected():
    with pytest.raises(ContractViolation):  # LONG with stop above entry
        validate_decision(_approved(stop_loss=2400.5))
    with pytest.raises(ContractViolation):  # LONG with tp below entry
        validate_decision(_approved(take_profit=2399.5))
    with pytest.raises(ContractViolation):  # SHORT with stop below entry
        validate_decision(_approved(direction="SHORT", entry_price=2400.0,
                                    stop_loss=2399.5, take_profit=2400.5))


def test_missing_identity_rejected():
    with pytest.raises(ContractViolation):
        validate_decision(_approved(client_signal_id=""))
    with pytest.raises(ContractViolation):
        validate_decision(_approved(symbol=""))


def test_rejected_requires_reason():
    ok = {"status": REJECTED, "reasons": {"rejection_reason": "no setup"},
          "symbol": "XAUUSD", "direction": "NEUTRAL"}
    assert validate_decision(ok) is ok
    with pytest.raises(ContractViolation):
        validate_decision({"status": REJECTED, "reasons": {}})
    with pytest.raises(ContractViolation):
        validate_decision({"status": REJECTED})


def test_unknown_provider_name_rejected():
    with pytest.raises(ContractViolation):
        create_provider("no_such_strategy")


def test_evaluate_enforces_contract_on_provider_output():
    class _BadProvider(StrategyProvider):
        name = "bad"

        def evaluate(self, inputs):
            return {"status": APPROVED, "direction": "YOLO"}

    register_provider("bad", _BadProvider)
    try:
        assert "bad" in registered_providers()
        with pytest.raises(ContractViolation):
            evaluate_strategy(_BadProvider(), MarketInputs(symbol="XAUUSD"))
    finally:
        from app.strategy import provider as provider_module
        del provider_module._PROVIDER_REGISTRY["bad"]


def test_market_inputs_defaults():
    mi = MarketInputs(symbol="EURUSD")
    assert mi.candles == {}
    assert mi.point_size == 0.01
