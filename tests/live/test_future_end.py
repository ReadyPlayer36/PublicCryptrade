"""Future end acceptance scenario uses only fake HTTP responses offline."""
from datetime import datetime, timezone
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient
from tests.fixtures.fakes import FakeHttpClient, FakeResponse

@pytest.mark.requirement("LIVE-04")
def test_future_end_clamp_and_strict_end():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767574201234}), FakeResponse(payload=[])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    result = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=datetime.fromtimestamp(1767571200, timezone.utc), end=datetime.fromtimestamp(1767601200, timezone.utc))
    assert result == []
    assert http.calls[1][1]["endTime"] == 1767574200000 - 1
