"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("VERIFY-01")
@pytest.mark.requirement("VERIFY-02")
def test_decimal_string_safe_comparisons():
    """Acceptance scenario bound to frozen matrix row(s): VERIFY-01, VERIFY-02."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).get_candles()


@pytest.mark.requirement("VERIFY-02")
def test_no_cast_as_real():
    """Acceptance scenario bound to frozen matrix row(s): VERIFY-02."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).get_candles()
