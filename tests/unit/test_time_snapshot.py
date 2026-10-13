"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    """Acceptance scenario bound to frozen matrix row(s): FINAL-01."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_server_time()
