"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("M1-04")
def test_no_api_keys():
    """Acceptance scenario bound to frozen matrix row(s): M1-04."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("M1-04")
def test_no_private_endpoints():
    """Acceptance scenario bound to frozen matrix row(s): M1-04."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("M1-04")
def test_public_spot_market_data_only():
    """Acceptance scenario bound to frozen matrix row(s): M1-04."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()
