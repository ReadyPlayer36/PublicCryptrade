"""Pagination contract test uses fake upstream pages only; no live requests are sent."""
from datetime import datetime, timezone
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient
from tests.fixtures.fakes import FakeHttpClient, FakeResponse

@pytest.mark.requirement("LIVE-03")
def test_1152_candles_two_pages():
    start = datetime.fromtimestamp(1767571200, timezone.utc)
    end = datetime.fromtimestamp((1767571200000 + 1152*300000)/1000, timezone.utc)
    page1 = []
    page2 = []
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1768000000000}), FakeResponse(payload=page1), FakeResponse(payload=page2)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=start, end=end)
    assert len(rows) == 1152
    assert len([1 for url, _ in http.calls if url.endswith("/api/v3/klines")]) == 2
