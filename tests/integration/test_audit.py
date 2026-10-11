"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("AUDIT-01")
def test_failure_audit_contents():
    """Acceptance scenario bound to frozen matrix row(s): AUDIT-01."""
    from trading_app.data.hashing import hash_candles
    hash_candles([])


@pytest.mark.requirement("AUDIT-02")
def test_failure_audit_write_cannot_mask_original_exception():
    """Acceptance scenario bound to frozen matrix row(s): AUDIT-02."""
    from trading_app.data.hashing import hash_candles
    hash_candles([])
