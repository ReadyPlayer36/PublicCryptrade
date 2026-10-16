"""Detect hollow tests: test functions that assert nothing meaningful."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ENTRY = re.compile(r"tests/[\w/.\-]+\.py::test_\w+")
CHECK_CALLS = {"pytest.raises", "pytest.fail", "pytest.warns", "pytest.skip"}


def _meaningful(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return not isinstance(node.test, ast.Constant)          # `assert True` / `assert 1` check nothing
    if isinstance(node, ast.Call):
        name = ast.unparse(node.func)
        return name in CHECK_CALLS or name.rsplit(".", 1)[-1].startswith("assert_")   # e.g. assert_valid_klines(...)
    return False


def hollow_tests(root: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted((Path(root) / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                if not any(_meaningful(child) for child in ast.walk(node)):
                    found.add(f"{path.relative_to(root).as_posix()}::{node.name}")
    return found


def load_allowlist(path: Path) -> set[str]:
    """Strict parse: a missing file or any malformed line raises ValueError (fail closed)."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"hollow allowlist missing: {path}")
    entries: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not ENTRY.fullmatch(line):
            raise ValueError(f"malformed hollow allowlist entry on line {number}: {line!r}")
        entries.add(line)
    return entries
