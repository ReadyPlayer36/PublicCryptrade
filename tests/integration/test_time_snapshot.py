"""Exactly one successful server-time request per fetch (hermetic; no network)."""
from datetime import datetime, timezone
import pytest
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from trading_app.data.binance_client import BinanceMarketDataClient

START = datetime.fromtimestamp(1767571200, tz=timezone.utc)
END = datetime.fromtimestamp(1767571500, tz=timezone.utc)


@pytest.mark.requirement("TIME-01")
def test_exactly_one_successful_server_time_per_fetch():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000}), FakeResponse(payload=[])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=0)
    client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert [u for u, _ in http.calls if u.endswith("/api/v3/time")] == ["https://data-api.binance.vision/api/v3/time"]
