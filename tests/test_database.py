import pytest
from sqlalchemy import select
from app.models.domain import User, Symbol, SignalModel

@pytest.mark.asyncio
async def test_user_model_creation(db_session):
    user = User(
        username="trader1",
        email="trader1@example.com",
        hashed_password="secret_hashed_password"
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.username == "trader1"))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.email == "trader1@example.com"

@pytest.mark.asyncio
async def test_symbol_model_creation(db_session):
    sym = Symbol(
        canonical_name="XAUUSD",
        broker_name="XAUUSDm",
        digits=2,
        point_size=0.01,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100.0
    )
    db_session.add(sym)
    await db_session.commit()

    result = await db_session.execute(select(Symbol).where(Symbol.canonical_name == "XAUUSD"))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.broker_name == "XAUUSDm"

@pytest.mark.asyncio
async def test_signal_model_creation(db_session):
    sig = SignalModel(
        client_signal_id="SIG_0001",
        symbol="XAUUSD",
        direction="LONG",
        timeframe="M5",
        setup_type="BULLISH_SWEEP_FVG",
        entry_price=2400.0,
        stop_loss=2390.0,
        take_profit=2420.0,
        status="DETECTED",
        reasons={"htf_context": "BULLISH", "sweep": "PDL_SWEEP"}
    )
    db_session.add(sig)
    await db_session.commit()

    result = await db_session.execute(select(SignalModel).where(SignalModel.client_signal_id == "SIG_0001"))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.direction == "LONG"
    assert fetched.reasons["sweep"] == "PDL_SWEEP"
