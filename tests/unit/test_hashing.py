"""Golden digest checks; expected hashes are fixed external vectors, never recalculated here."""
import json
from pathlib import Path
import pytest
from trading_app.data.hashing import hash_candles
VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/golden_hash_vectors.json").read_text())

@pytest.mark.requirement("HASH-02")
@pytest.mark.parametrize("_facet", ["empty-one-multi"], ids=["empty-one-multi"])
def test_golden_hash_vectors(_facet):
    for key in ("empty", "one_record", "two_records"):
        vector = VECTORS[key]
        assert hash_candles(vector["records"]) == vector["sha256"]

@pytest.mark.requirement("HASH-01")
def test_hash_serialization_order_and_encoding():
    result = hash_candles(VECTORS["two_records"]["records"])
    assert result == VECTORS["two_records"]["sha256"]
    assert result != VECTORS["negative_control_reordered"]["sha256"]
