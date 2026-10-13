"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("META-01")
def test_data_fetch_metadata_fields():
    """Acceptance scenario bound to frozen matrix row(s): META-01."""
    from trading_app.data.service import MarketDataService
    MarketDataService().download_and_store()
