"""Finality integration contracts with fake public HTTP responses only."""
from datetime import datetime, timezone
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
START=datetime(2024,1,1,tzinfo=timezone.utc)
END=datetime(2024,1,2,tzinfo=timezone.utc)
FUTURE=datetime(2030,1,1,tzinfo=timezone.utc)

@pytest.mark.requirement("FINAL-01")
@pytest.mark.parametrize("_facet", ['lag-0ms'], ids=['lag-0ms'])
def test_boundary_rule(_facet):
    """Frozen acceptance case: FINAL-01."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-03")
def test_future_end_reports_requested_and_effective_ranges():
    """Frozen acceptance case: FINAL-03."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient([FakeResponse(payload={"serverTime": 1704067200000})]))
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=FUTURE)

@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    """Frozen acceptance case: FINAL-01."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient(errors=[TimeoutError("server time down")]))
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-02")
def test_nonfinal_candle_during_pagination_aborts():
    """Frozen acceptance case: FINAL-02."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-06")
def test_returned_nonfinal_candle_aborts_fetch():
    """Frozen acceptance case: FINAL-06."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-01")
@pytest.mark.parametrize("_facet", ['invalid-timestamp', 'malformed-time', 'server-time-failure'], ids=['invalid-timestamp', 'malformed-time', 'server-time-failure'])
def test_server_time_failure_aborts(_facet):
    """Frozen acceptance case: FINAL-01."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient(errors=[TimeoutError("server time down")]))
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

