"""D-01 tests: optional production bearer-token gate (P-05/ADR-6)."""
import pytest

from app.core.config import settings


@pytest.fixture
def prod_token(monkeypatch):
    """Arms the token gate (production + token), restoring settings after."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "AUTOMATION_API_TOKEN", "test-token-123")
    yield
    # monkeypatch auto-restores


@pytest.fixture
def prod_no_token(monkeypatch):
    """Production WITHOUT a token configured: gate stays open (documented)."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "AUTOMATION_API_TOKEN", None)
    yield


@pytest.mark.asyncio
async def test_mutating_endpoints_open_in_dev(async_client):
    res = await async_client.get("/api/risk/status")
    assert res.status_code == 200
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "dev open"})
    assert res.status_code == 200
    res = await async_client.post("/api/system/reset-emergency-stop")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_token_enforced_when_prod_and_token_set(async_client, prod_token):
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "no header"})
    assert res.status_code == 401
    res = await async_client.post(
        "/api/system/emergency-stop",
        json={"reason": "wrong"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert res.status_code == 401
    res = await async_client.post(
        "/api/system/emergency-stop",
        json={"reason": "ok"},
        headers={"Authorization": "Bearer test-token-123"},
    )
    assert res.status_code == 200
    res = await async_client.post(
        "/api/system/reset-emergency-stop",
        headers={"Authorization": "Bearer test-token-123"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_orders_and_close_all_gated(async_client, prod_token):
    res = await async_client.post("/api/execution/orders", json={
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res.status_code == 401
    res = await async_client.post("/api/execution/close-all")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_read_endpoints_stay_open_under_token_gate(async_client, prod_token):
    res = await async_client.get("/api/risk/status")
    assert res.status_code == 200
    res = await async_client.get("/api/health")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_prod_without_token_stays_open(async_client, prod_no_token):
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "x"})
    assert res.status_code == 200
    res = await async_client.post("/api/system/reset-emergency-stop")
    assert res.status_code == 200
