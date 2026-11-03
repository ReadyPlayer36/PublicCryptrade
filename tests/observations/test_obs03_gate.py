"""OBS-03 must block live acceptance while the observation rows remain open."""
from pathlib import Path
import yaml
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("OBS-03")
def test_observation_gate_before_live_acceptance():
    matrix = yaml.safe_load((ROOT / "matrix.yaml").read_text())
    assert matrix["status"]["milestone_1"] == "BLOCKED"
    assert matrix["observations"]["OBS-01"]["status"] == "open"
    assert matrix["observations"]["OBS-02"]["status"] == "open"
