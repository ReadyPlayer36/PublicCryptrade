"""OBS-02 time-dependent finality protocol contract, using pure-function vectors."""
import json
from pathlib import Path
import pytest
from trading_app.data.finality import is_final
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("OBS-02")
def test_time_dependent_finality_observation_protocol():
    vectors = json.loads((ROOT / "tests/fixtures/vectors/finality_vectors.json").read_text())
    for case in vectors["cases"]:
        assert is_final(case["candle_close_ms"], case["S_ms"], case["L_ms"]) is case["expected_final"]
    assert "offsets_seconds" in (ROOT / "matrix.yaml").read_text()
