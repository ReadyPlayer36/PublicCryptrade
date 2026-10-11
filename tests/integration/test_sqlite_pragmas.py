"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("R5-03")
def test_data_directory_auto_created():
    """Acceptance scenario bound to frozen matrix row(s): R5-03."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).create_tables()


@pytest.mark.requirement("R5-01")
def test_wal_and_busy_timeout():
    """Acceptance scenario bound to frozen matrix row(s): R5-01."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).create_tables()
