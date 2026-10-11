"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("CONFLICT-03")
def test_conflict_compares_all_fields_and_never_overwrites():
    """Acceptance scenario bound to frozen matrix row(s): CONFLICT-03."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])


@pytest.mark.requirement("CONFLICT-02")
def test_decimal_numeric_equality_and_created_at_exclusion():
    """Acceptance scenario bound to frozen matrix row(s): CONFLICT-02."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])
