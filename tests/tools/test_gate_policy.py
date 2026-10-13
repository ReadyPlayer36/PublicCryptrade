"""Mandatory behavioral rows may not be skipped or xfailed."""
import ast
from pathlib import Path
import yaml, pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("GATE-02")
def test_skip_or_xfail_mandatory_blocks():
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    bound={node.split("::",1)[0] for row in matrix["acceptance_rows"] if row.get("mandatory") for node in row.get("tests",[])}
    for rel in bound:
        path=ROOT/rel
        if not path.exists(): continue
        tree=ast.parse(path.read_text())
        for fn in (n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))):
            for dec in fn.decorator_list:
                if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr in {"skip","skipif","xfail"}:
                    pytest.fail(f"mandatory test {rel}::{fn.name} has skip/xfail")

@pytest.mark.requirement("GATE-01")
def test_unavailable_live_evidence_blocks():
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    assert matrix["status"]["milestone_1"] == "BLOCKED"
    live=[row for row in matrix["acceptance_rows"] if row.get("evidence_class")=="live" and row.get("mandatory")]
    assert live
    assert all(row.get("artifact_path") for row in live)
