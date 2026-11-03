"""Live evidence manifest contract is checked offline without performing a live run."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("LIVE-05")
def test_live_run_evidence_manifest():
    matrix = (ROOT / "matrix.yaml").read_text()
    assert "evidence_class: live" in matrix
    assert "run_manifest" in matrix.lower() or "manifest" in matrix.lower()
    # Actual signed/live-run artifacts intentionally remain absent until the reviewer authorizes a LIVE run.
    assert not (ROOT / "evidence/live/manifest.json").exists()
