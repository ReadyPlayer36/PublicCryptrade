"""OBS-01 boundary protocol vector contract; does not access the network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("OBS-01")
def test_end_and_start_boundary_semantics():
    vectors = json.loads((ROOT / "tests/fixtures/vectors/finality_vectors.json").read_text())
    assert vectors["rule"] == "close_time_ms < B"
    assert {c["case"] for c in vectors["cases"]} == {"B-1_is_final", "B_not_final", "B+1_not_final"}
    assert all(c["candle_close_ms"] == c["candle_open_ms"] + vectors["interval_ms"] - 1 for c in vectors["cases"])
