"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("GATE-02")
def test_skip_or_xfail_mandatory_blocks():
    """Acceptance scenario bound to frozen matrix row(s): GATE-02."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")


@pytest.mark.requirement("GATE-01")
def test_unavailable_live_evidence_blocks():
    """Acceptance scenario bound to frozen matrix row(s): GATE-01."""
    raise NotImplementedError("Stage-2 tooling acceptance scenario is intentionally red before implementation")
