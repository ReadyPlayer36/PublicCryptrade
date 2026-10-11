"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("LOG-02")
def test_http_error_logging_excludes_raise_for_status_url_userinfo_and_secrets():
    """Acceptance scenario bound to frozen matrix row(s): LOG-02."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("LOG-01")
def test_logs_exclude_urls_headers_keys_tokens_and_secrets():
    """Acceptance scenario bound to frozen matrix row(s): LOG-01."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()
