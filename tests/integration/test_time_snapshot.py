"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("TIME-01")
def test_exactly_one_successful_server_time_per_fetch():
    """Acceptance scenario bound to frozen matrix row(s): TIME-01."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_server_time()
