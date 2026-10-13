"""Public market-data download contracts with deterministic fake HTTP."""
from datetime import datetime, timezone
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
START = datetime.fromtimestamp(1767571200, timezone.utc)
END = datetime.fromtimestamp(1767571500, timezone.utc)

@pytest.mark.requirement("M1-05")
def test_kline_download():
    row = [1767571200000, "100.10", "101.00", "99.50", "100.50", "12.345", 1767571499999, "1240", 100, "0", "0", "0"]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000}), FakeResponse(payload=[row])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert rows == [row]
    assert len(http.calls) == 2

@pytest.mark.requirement("M1-05")
def test_kline_pagination():
    first = [[1767571200000, "100", "101", "99", "100", "1", 1767571499999, "100", 1, "0", "0", "0"]]
    second = [[1767571500000, "100", "101", "99", "100", "1", 1767571799999, "100", 1, "0", "0", "0"]]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571800000}), FakeResponse(payload=first), FakeResponse(payload=second)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=datetime.fromtimestamp(1767571800, timezone.utc))
    assert len(rows) == 2
    assert [r[0] for r in rows] == [1767571200000, 1767571500000]
    assert len(http.calls) == 3
