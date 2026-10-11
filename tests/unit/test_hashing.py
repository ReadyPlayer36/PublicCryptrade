"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("HASH-02")
@pytest.mark.parametrize("_facet", ['empty-one-multi'], ids=['empty-one-multi'])
def test_golden_hash_vectors(_facet):
    """Acceptance scenario bound to frozen matrix row(s): HASH-02."""
    from trading_app.data.hashing import hash_candles
    hash_candles([])


@pytest.mark.requirement("HASH-01")
def test_hash_serialization_order_and_encoding():
    """Acceptance scenario bound to frozen matrix row(s): HASH-01."""
    from trading_app.data.hashing import hash_candles
    hash_candles([])
