import pytest
from app.data.mt5_mock import MockMT5Adapter

def test_mt5_mock_connection(mock_mt5):
    assert mock_mt5.is_connected() is True
    mock_mt5.disconnect()
    assert mock_mt5.is_connected() is False

def test_mt5_mock_symbols(mock_mt5):
    symbols = mock_mt5.get_symbols()
    assert "XAUUSD" in symbols
    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols
    assert "NAS100" in symbols

def test_mt5_mock_symbol_info(mock_mt5):
    gold = mock_mt5.get_symbol_info("XAUUSD")
    assert gold is not None
    assert gold["digits"] == 2
    assert gold["point_size"] == 0.01

def test_mt5_mock_ticks(mock_mt5):
    ticks = mock_mt5.get_ticks("XAUUSD", count=10)
    assert len(ticks) == 10
    assert "bid" in ticks[0]
    assert "ask" in ticks[0]

def test_mt5_mock_candles(mock_mt5):
    candles = mock_mt5.get_historical_candles("XAUUSD", "M5", count=50)
    assert len(candles) == 50
    candle = candles[0]
    assert "open" in candle
    assert "high" in candle
    assert "low" in candle
    assert "close" in candle
    assert "volume" in candle
    assert candle["high"] >= candle["low"]

def test_mt5_mock_send_order(mock_mt5):
    order_req = {
        "symbol": "XAUUSD",
        "volume": 0.1,
        "price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0,
        "type": "BUY"
    }
    response = mock_mt5.send_order(order_req)
    assert response["retcode"] == 10009
    assert response["volume"] == 0.1
    assert "order" in response

def test_mt5_mock_account_info(mock_mt5):
    acc = mock_mt5.get_account_info()
    assert acc["balance"] == 10000.0
    assert acc["currency"] == "USD"
