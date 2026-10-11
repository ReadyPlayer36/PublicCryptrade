"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("HYGIENE-05")
def test_filterwarnings_error_and_no_coverage_warning():
    """Acceptance scenario bound to frozen matrix row(s): HYGIENE-05."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")
