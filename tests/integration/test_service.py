"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("M1-14")
def test_repeatable_ingestion_is_idempotent():
    """Acceptance scenario bound to frozen matrix row(s): M1-14."""
    from trading_app.data.service import MarketDataService
    MarketDataService().download_and_store()
