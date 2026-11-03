"""Server time must come from Binance only; failure aborts instead of using the local clock."""
import pytest
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient

LOCAL_CLOCK_MS = 999_999_999_999_999


@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    http = FakeHttpClient([FakeResponse(status_code=503) for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http,
                                     sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: LOCAL_CLOCK_MS)
    with pytest.raises(BinanceClientError, match="503|request"):
        client.get_server_time()
    assert len(http.calls) == 4


@pytest.mark.requirement("FINAL-01")
def test_server_time_is_the_exchange_value_not_the_local_clock():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, now_ms=lambda: LOCAL_CLOCK_MS)
    assert client.get_server_time() == 1767571500000
