"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("HASH-01")
def test_decimal_format_f_is_exact():
    """Acceptance scenario bound to frozen matrix row(s): HASH-01."""
    from trading_app.data.hashing import hash_candles
    hash_candles([])
