"""No trading execution or private API implementation in the scaffold."""
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.requirement("M1-04")
def test_milestone_one_scope_boundary():
    source="\n".join(p.read_text(encoding="utf-8") for base in (ROOT/"src", ROOT/"scripts") for p in base.rglob("*.py"))
    lowered=source.lower()
    assert "/api/v3/order" not in lowered
    assert "new_order" not in lowered
    assert "api_secret" not in lowered
    assert "signature=" not in lowered
