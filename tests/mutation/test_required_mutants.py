"""Required mutation set and killer bindings are read from the frozen matrix."""
import ast, re
from pathlib import Path
import yaml, pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("MUT-03")
def test_each_mutant_has_killer():
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    killers=matrix["mutation_killers"]
    assert len(killers) >= 16
    test_functions=set()
    for path in (ROOT/"tests").rglob("test_*.py"):
        tree=ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node,ast.FunctionDef): test_functions.add(f"{path.relative_to(ROOT).as_posix()}::{node.name}")
    for mutant,nodes in killers.items():
        assert nodes, f"mutant {mutant} has no killer"
        for nodeid in nodes:
            base=re.sub(r"\[[^]]+\]$", "", nodeid)
            assert base in test_functions, f"missing killer nodeid {nodeid} for {mutant}"

@pytest.mark.requirement("MUT-02")
def test_required_mutant_set():
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    required={"finality_boundary","conflict_raise","rollback","path_check","403_418_retry","fallback_after_429","retry_after_reduction","silent_discard","redirects","overwrite","decimal_format","float_comparison","local_clock","begin_immediate","host_allowlist","cooldown_persistence"}
    assert set(matrix["mutation_killers"]) == required
