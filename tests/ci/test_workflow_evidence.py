"""CI workflow must be explicit about Python baseline and test artifacts."""
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("CI-01")
def test_ci_python312_and_artifacts():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "python-version: '3.12'" in workflow
    assert "junit" in workflow.lower()
    assert "check_freeze.py" in workflow
    assert "validate_matrix.py" in workflow
    assert "spec_check.py" in workflow
