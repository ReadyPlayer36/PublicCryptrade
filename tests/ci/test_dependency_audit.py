"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("DEP-02")
def test_hash_pinned_constraints_reproducible():
    """Acceptance scenario bound to frozen matrix row(s): DEP-02."""
    raise NotImplementedError("Stage-2 behavioral test scaffold: implement this scenario before production code")


@pytest.mark.requirement("DEP-01")
def test_pip_audit_zero_known_vulnerabilities():
    """Acceptance scenario bound to frozen matrix row(s): DEP-01."""
    raise NotImplementedError("Stage-2 behavioral test scaffold: implement this scenario before production code")
