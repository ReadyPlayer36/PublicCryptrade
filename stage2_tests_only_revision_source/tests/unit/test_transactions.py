"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("TX-03")
def test_max_candles_limit():
    """Acceptance scenario bound to frozen matrix row(s): TX-03."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])
