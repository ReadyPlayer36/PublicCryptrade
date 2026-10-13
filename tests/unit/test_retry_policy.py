"""Retry behavior checks use fake responses and assert observable side effects."""
import pytest
from tests.fixtures.policy import retry_policy
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError

@pytest.mark.requirement("M1-06")
@pytest.mark.requirement("RETRY-01")
def test_403_and_418_are_not_retried():
    for status in (403, 418):
        http = FakeHttpClient([FakeResponse(status_code=status)])
        client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
        with pytest.raises(BinanceClientError, match=str(status)):
            client.get_server_time()
        assert len(http.calls) == 1

@pytest.mark.requirement("RETRY-01")
def test_429_does_not_fallback():
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": "45"})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.5)
    with pytest.raises(BinanceClientError, match="429|budget|cooldown|retry"):
        client.get_server_time()
    assert len(http.calls) == 1
    assert all("api.binance.com" not in url for url, _ in http.calls)

@pytest.mark.requirement("RETRY-02")
@pytest.mark.requirement("RETRY-01")
def test_retry_after_is_not_jittered_or_reduced():
    policy = retry_policy()["retry_after"]
    assert policy["sleep_jitter"] is False
    assert policy["max_seconds"] == 60
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": "10"}) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.9)
    with pytest.raises(BinanceClientError, match="429|rate|retry"):
        client.get_server_time()
    assert sleeps == [10, 10, 10]
    assert len(http.calls) == 4
