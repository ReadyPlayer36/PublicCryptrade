"""Only reviewer approval can change the frozen milestone status."""
from pathlib import Path
import pytest, yaml
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("OUTCOME-01")
def test_only_reviewer_sets_final_status():
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    approval=(ROOT/"evidence/freeze/stage1-reviewer-approval.txt").read_text()
    assert matrix["status"]["milestone_1"] == "BLOCKED"
    assert "reviewer_approval_line: null" in (ROOT/"matrix.yaml").read_text()
    assert "reviewer" in approval.lower()
