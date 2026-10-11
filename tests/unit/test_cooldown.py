"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("COOLDOWN-03")
def test_cooldown_atomic_persistence():
    """Acceptance scenario bound to frozen matrix row(s): COOLDOWN-03."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()


@pytest.mark.requirement("COOLDOWN-02")
def test_cooldown_trigger_minimums_and_retry_after():
    """Acceptance scenario bound to frozen matrix row(s): COOLDOWN-02."""
    from trading_app.data.binance_client import BinanceMarketDataClient
    BinanceMarketDataClient(base_url="https://data-api.binance.vision").get_historical_klines()
