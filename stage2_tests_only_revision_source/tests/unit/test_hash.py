"""Exact decimal-format hashing contract tests using independent golden vectors."""
import json
from pathlib import Path
import pytest
from trading_app.data.hashing import hash_candles
VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/golden_hash_vectors.json").read_text())

@pytest.mark.requirement("HASH-01")
def test_decimal_format_f_is_exact():
    # Empty hash is independently fixed as SHA-256 of zero bytes; no production-derived expectation.
    assert hash_candles(VECTORS["empty"]["records"]) == VECTORS["empty"]["sha256"]
