"""URL hardening tests; no network request is made."""
from datetime import datetime, timezone
import pytest
from trading_app.policy import frozen_policy
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError, validate_public_url
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
START=datetime(2024,1,1,tzinfo=timezone.utc)
END=datetime(2024,1,2,tzinfo=timezone.utc)

@pytest.mark.requirement("NET-01")
def test_encoded_traversal_rejected():
    """Frozen acceptance case: NET-01."""
    with pytest.raises(ValueError): validate_public_url("https://data-api.binance.vision/api/v3/klines/%2e%2e/order")

@pytest.mark.requirement("PATH-01")
def test_exact_normalized_paths():
    """Frozen acceptance case: PATH-01."""
    assert validate_public_url("https://data-api.binance.vision/api/v3/time") is True
    with pytest.raises(ValueError): validate_public_url("https://data-api.binance.vision/api/v3/timeX")

@pytest.mark.requirement("NET-01")
def test_exact_path_allowlist():
    """Frozen acceptance case: NET-01."""
    assert validate_public_url("https://data-api.binance.vision/api/v3/klines") is True
    with pytest.raises(ValueError): validate_public_url("https://data-api.binance.vision/api/v3/klines/../order")

@pytest.mark.requirement("NET-01")
@pytest.mark.parametrize("_facet", ['encoded-traversal', 'query-trick', 'timeX', 'traversal'], ids=['encoded-traversal', 'query-trick', 'timeX', 'traversal'])
def test_exact_paths(_facet):
    """Frozen acceptance case: NET-01."""
    candidate={"encoded-traversal":"https://data-api.binance.vision/api/v3/klines/%2e%2e/order", "query-trick":"https://data-api.binance.vision/api/v3/time?path=/api/v3/order", "timeX":"https://data-api.binance.vision/api/v3/timeX", "traversal":"https://data-api.binance.vision/api/v3/klines/../order"}[_facet]
    with pytest.raises(ValueError): validate_public_url(candidate)

@pytest.mark.requirement("HOST-01")
def test_frozen_host_set():
    """Frozen acceptance case: HOST-01."""
    policy=frozen_policy()["network"]["hosts"]
    assert policy["primary"] == "data-api.binance.vision"
    assert policy["fallback"] == "api.binance.com"
    assert "testnet.binance.vision" in policy["excluded"]

@pytest.mark.requirement("NET-01")
def test_redirects_disabled():
    """Frozen acceptance case: NET-01."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision")
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("REDIRECT-01")
def test_redirects_disabled_and_3xx_rejected():
    """Frozen acceptance case: REDIRECT-01."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient([FakeResponse(status_code=302, headers={"Location":"https://example.com"})]))
    with pytest.raises(BinanceClientError): client.get_server_time()

@pytest.mark.requirement("NET-01")
def test_untrusted_host_rejected():
    """Frozen acceptance case: NET-01."""
    with pytest.raises(ValueError): validate_public_url("https://evil.example/api/v3/time")

