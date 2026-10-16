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


_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _own_nodes(node: ast.AST):
    """Nodes of this function's own body, NOT descending into nested functions, lambdas or classes."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if not isinstance(current, _NESTED):
            stack.extend(ast.iter_child_nodes(current))


def _is_generator(function: ast.AST) -> bool:
    return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in _own_nodes(function))


def _has_meaningful_check(function: ast.AST) -> bool:
    own = list(_own_nodes(function))
    if any(_meaningful(n) for n in own):
        return True
    # A nested helper counts only if its body would really execute:
    #  * sync helper: the test body calls it by name;
    #  * async helper: the test body AWAITS the call (a bare call only creates a coroutine);
    #  * generator helper: never counted (calling it does not run its body; consumption is not tracked).
    sync_helpers: set[str] = set()
    async_helpers: set[str] = set()
    for n in own:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(_meaningful(c) for c in _own_nodes(n)) \
                and not _is_generator(n):
            (async_helpers if isinstance(n, ast.AsyncFunctionDef) else sync_helpers).add(n.name)
    awaited = {n.value.func.id for n in own if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Name)}
    called = {n.func.id for n in own if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return bool(sync_helpers & called) or bool(async_helpers & awaited)


def hollow_tests(root: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted((Path(root) / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                if not _has_meaningful_check(node):
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
