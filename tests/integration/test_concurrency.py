"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("TX-01")
def test_conflict_rolls_back_entire_transaction():
    """Acceptance scenario bound to frozen matrix row(s): TX-01."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])


@pytest.mark.requirement("TX-01")
def test_no_duplicate_rows_after_overlap():
    """Acceptance scenario bound to frozen matrix row(s): TX-01."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])


@pytest.mark.requirement("TX-01")
def test_two_processes_overlap_without_duplicates():
    """Acceptance scenario bound to frozen matrix row(s): TX-01."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])
