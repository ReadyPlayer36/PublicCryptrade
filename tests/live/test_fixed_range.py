"""Live acceptance scenarios are represented with fake public responses in offline CI."""
from datetime import datetime, timezone
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
START = datetime.fromtimestamp(1767571200, tz=timezone.utc)
END = datetime.fromtimestamp(1767571500, tz=timezone.utc)

@pytest.mark.requirement("LIVE-01")
def test_btcusdt_5m_12_candles():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571800000}), FakeResponse(payload=[])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert len(rows) == 12
    assert len(http.calls) == 2

@pytest.mark.requirement("LIVE-02")
def test_immediate_rerun_zero_new_rows():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571800000}), FakeResponse(payload=[])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    first = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    second = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert first == second == []
    assert len(http.calls) == 4
