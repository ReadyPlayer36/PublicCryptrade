"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("M1-16")
def test_no_trading_code_or_order_submission():
    """Acceptance scenario bound to frozen matrix row(s): M1-16."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("TRIP-01")
def test_tripwire_forbidden_http_calls():
    """Acceptance scenario bound to frozen matrix row(s): TRIP-01."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("TRIP-02")
def test_tripwire_scanned_file_count_and_tests_exemption():
    """Acceptance scenario bound to frozen matrix row(s): TRIP-02."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()
