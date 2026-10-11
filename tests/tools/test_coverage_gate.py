"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("COV-02")
def test_coverage_gate_fails_closed():
    """Acceptance scenario bound to frozen matrix row(s): COV-02."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")


@pytest.mark.requirement("COV-01")
def test_coverage_scope_and_thresholds():
    """Acceptance scenario bound to frozen matrix row(s): COV-01."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")


@pytest.mark.requirement("TOOLS-06")
def test_negative_below_threshold():
    """Acceptance scenario bound to frozen matrix row(s): TOOLS-06."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")
