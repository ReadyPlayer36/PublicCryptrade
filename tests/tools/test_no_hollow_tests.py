"""Ratchet against hollow acceptance tests (tests with no assertion at all)."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "tests" / "hollow_allowlist.txt"
CHECKS = ("assert ", "pytest.raises", "pytest.fail", "pytest.warns")


def hollow_tests(root: Path) -> set[str]:
    found = set()
    for path in sorted((root / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = ast.unparse(node)
                if not any(token in body for token in CHECKS):
                    found.add(f"{path.relative_to(root).as_posix()}::{node.name}")
    return found


def allowlisted() -> set[str]:
    return {line.strip() for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")} if ALLOWLIST.exists() else set()


@pytest.mark.requirement("HYGIENE-02")
def test_no_new_hollow_tests_may_be_added():
    new = hollow_tests(ROOT) - allowlisted()
    assert not new, f"assertion-free tests are not allowed: {sorted(new)}"


@pytest.mark.requirement("HYGIENE-02")
def test_allowlist_only_shrinks():
    stale = allowlisted() - hollow_tests(ROOT)
    assert not stale, f"remove these now-real tests from tests/hollow_allowlist.txt: {sorted(stale)}"


@pytest.mark.requirement("HYGIENE-02")
def test_detector_flags_hollow_and_accepts_real_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "import pytest\ndef test_hollow():\n    call()\ndef test_real():\n    assert 1\ndef test_raises():\n    with pytest.raises(ValueError):\n        f()\n")
    assert hollow_tests(tmp_path) == {"tests/test_x.py::test_hollow"}
