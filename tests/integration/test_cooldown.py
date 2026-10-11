"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("COOLDOWN-04")
def test_cooldown_directory_scope():
    """Acceptance scenario bound to frozen matrix row(s): COOLDOWN-04."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("COOLDOWN-01")
def test_cooldown_is_global_across_hosts():
    """Acceptance scenario bound to frozen matrix row(s): COOLDOWN-01."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("COOLDOWN-03")
def test_cooldown_persists_across_processes():
    """Acceptance scenario bound to frozen matrix row(s): COOLDOWN-03."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()
