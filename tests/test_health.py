import pytest

@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "Autonomous Trader"
    assert data["execution_mode"] == "PAPER"
    assert data["enable_live_trading"] is False
    assert data["database_connected"] is True
    assert data["mt5_connected"] is True

@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Autonomous Trader"
    assert data["health"] == "/api/health"
