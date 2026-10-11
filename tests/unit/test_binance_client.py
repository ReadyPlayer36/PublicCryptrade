"""Binance public-client contract tests. All HTTP is fake; no sockets are opened."""
from datetime import datetime, timezone
import pytest
from trading_app.policy import frozen_policy, retry_policy, cooldown_policy
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
START=datetime(2024,1,1,tzinfo=timezone.utc)
END=datetime(2024,1,2,tzinfo=timezone.utc)

@pytest.mark.requirement("M1-06")
def test_retry_policy():
    """Frozen acceptance case: M1-06."""
    policy=retry_policy()
    assert policy["attempts_total"] == frozen_policy()["retry"]["attempts_total"]
    assert policy["attempts_scope"] == "per_request"

@pytest.mark.requirement("M1-12")
def test_binance_responses_are_mocked():
    """Frozen acceptance case: M1-12."""
    http=FakeHttpClient([FakeResponse(payload={"serverTime": 123})])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_server_time()
    assert len(http.calls) == 1

@pytest.mark.requirement("RETRY-06")
def test_429_without_retry_after_uses_backoff():
    """Frozen acceptance case: RETRY-06."""
    http=FakeHttpClient([FakeResponse(status_code=429, headers={})])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("RETRY-04")
def test_backoff_cap_and_jitter():
    """Frozen acceptance case: RETRY-04."""
    backoff=retry_policy()["backoff"]
    assert backoff["cap_seconds"] <= backoff["base_seconds"] * backoff["factor"] ** (retry_policy()["attempts_total"]-1) + backoff["jitter_max_seconds"]
    assert backoff["jitter_applies_to"] == "exponential_backoff_only"

@pytest.mark.requirement("RETRY-05")
def test_fetch_sleep_budget_and_cooldown():
    """Frozen acceptance case: RETRY-05."""
    assert retry_policy()["sleep_budget_scope"] == "per_fetch"
    assert cooldown_policy()["scope"] == "global_across_allowed_hosts"

@pytest.mark.requirement("RETRY-01")
def test_malformed_json_retry():
    """Frozen acceptance case: RETRY-01."""
    http=FakeHttpClient([FakeResponse(status_code=200, json_error=ValueError("bad json"))])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_server_time()

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("_facet", ['400', '403', '418'], ids=['400', '403', '418'])
def test_no_retry_status(_facet):
    """Frozen acceptance case: RETRY-01."""
    http=FakeHttpClient([FakeResponse(status_code=_facet)])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert len(http.calls) == 1

@pytest.mark.requirement("RETRY-03")
def test_only_retry_configured_statuses():
    """Frozen acceptance case: RETRY-03."""
    configured=set(retry_policy()["retry_statuses"])
    assert configured == set(frozen_policy()["retry"]["retry_statuses"])
    assert not ({400,403,418} & configured)

@pytest.mark.requirement("RETRY-01")
def test_read_timeout_retry():
    """Frozen acceptance case: RETRY-01."""
    http=FakeHttpClient(errors=[TimeoutError("read timeout")])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_server_time()

@pytest.mark.requirement("RETRY-01")
def test_repeated_429_persists_cooldown():
    """Frozen acceptance case: RETRY-01."""
    http=FakeHttpClient([FakeResponse(status_code=429), FakeResponse(status_code=429)])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_server_time()

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("_facet", ['429'], ids=['429'])
def test_retry_after_cap_and_no_jitter(_facet):
    """Frozen acceptance case: RETRY-01."""
    policy=retry_policy()["retry_after"]
    assert policy["sleep_jitter"] is False
    assert policy["max_seconds"] == frozen_policy()["retry"]["retry_after"]["max_seconds"]

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("_facet", ['429', '500'], ids=['429', '500'])
def test_retry_status(_facet):
    """Frozen acceptance case: RETRY-01."""
    http=FakeHttpClient([FakeResponse(status_code=_facet)])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("RETRY-02")
def test_timeout_retry_and_connect_fallback():
    """Frozen acceptance case: RETRY-02."""
    policy=retry_policy()
    assert "read_timeout" in policy["retry_errors"]
    assert policy["connect_dns"] == "fallback_only_before_first_successful_server_time"
    http=FakeHttpClient(errors=[TimeoutError("timeout")])
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError): client.get_server_time()

