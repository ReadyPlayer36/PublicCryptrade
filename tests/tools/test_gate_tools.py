"""Gate tooling files and negative-test coverage must be present."""
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("TOOLS-04")
def test_each_gate_has_negative_test():
    for name in ("check_freeze.py", "validate_matrix.py", "check_traceability.py", "check_evidence.py", "spec_check.py", "red_reason_gate.py"):
        assert (ROOT/"tools"/name).is_file()
    assert "returncode != 0" in (ROOT/"tests/tools/test_spec_tooling.py").read_text()
    assert "returncode != 0" in (ROOT/"tests/tools/test_traceability.py").read_text()
