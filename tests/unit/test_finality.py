"""Finality boundary contracts; no local clock or live network is used."""
from datetime import datetime, timezone
import pytest
from trading_app.policy import frozen_policy, finality_policy
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from tests.fixtures.fakes import FakeHttpClient
START=datetime(2024,1,1,tzinfo=timezone.utc)
END=datetime(2024,1,2,tzinfo=timezone.utc)

@pytest.mark.requirement("FINAL-01")
@pytest.mark.requirement("FINAL-04")
@pytest.mark.requirement("FINAL-08")
@pytest.mark.parametrize("_facet", ['lag-0ms', 'lag-positive'], ids=['lag-0ms', 'lag-positive'])
def test_boundary_rule(_facet):
    """Frozen acceptance case: FINAL-01, FINAL-04, FINAL-08."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-05")
def test_effective_end_formula():
    """Frozen acceptance case: FINAL-05."""
    policy=finality_policy()
    assert policy["effective_end"] == "min(requested_end, floor((S-L)/I)*I)"
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-07")
def test_empty_effective_range_and_input_validation():
    """Frozen acceptance case: FINAL-07."""
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient())
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=END, end=START)

@pytest.mark.requirement("LAG-01")
def test_finality_lag_has_no_default():
    """Frozen acceptance case: LAG-01."""
    policy=finality_policy()
    assert policy["lag_default"] is None
    assert policy["lag_min_ms"] == frozen_policy()["finality"]["lag_min_ms"]

@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    """Frozen acceptance case: FINAL-01."""
    assert finality_policy()["local_clock_fallback"] is False
    client=BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient(errors=[TimeoutError("server time unavailable")]))
    with pytest.raises(BinanceClientError): client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

