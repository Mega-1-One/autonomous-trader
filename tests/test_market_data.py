import pytest
from app.services.market_data import MarketDataService
from app.data.mt5_mock import MockMT5Adapter

@pytest.fixture
def market_service():
    mock_adapter = MockMT5Adapter()
    mock_adapter.connect()
    return MarketDataService(adapter=mock_adapter)

def test_market_service_symbols(market_service):
    symbols = market_service.get_supported_symbols()
    assert "XAUUSD" in symbols
    assert "EURUSD" in symbols

def test_market_service_fetch_candles(market_service):
    candles = market_service.fetch_candles("XAUUSD", "M5", count=50)
    assert len(candles) == 50
    first = candles[0]
    assert "timestamp" in first
    assert "T" in first["timestamp"] # ISO format check

def test_market_service_missing_candles_detection(market_service):
    candles = market_service.fetch_candles("XAUUSD", "M5", count=20)
    # Artificially remove index 10 to create a gap
    gap_candles = candles[:10] + candles[12:]
    gaps = market_service.detect_missing_candles(gap_candles, "M5")
    assert len(gaps) >= 1
    assert gaps[0]["timeframe"] == "M5"

@pytest.mark.asyncio
async def test_api_get_symbols(async_client):
    res = await async_client.get("/api/market/symbols")
    assert res.status_code == 200
    data = res.json()
    assert "XAUUSD" in data["symbols"]
    assert "XAUUSD" in data["specifications"]

@pytest.mark.asyncio
async def test_api_get_candles(async_client):
    res = await async_client.get("/api/market/candles?symbol=XAUUSD&timeframe=M5&count=50")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert data["count"] == 50
    assert len(data["candles"]) == 50

@pytest.mark.asyncio
async def test_api_get_market_status(async_client):
    res = await async_client.get("/api/market/status")
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is True
    assert "XAUUSD" in data["freshness"]
