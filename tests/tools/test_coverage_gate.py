"""Coverage policy is fail-closed and scoped only to production modules."""
from pathlib import Path
import json, subprocess, sys, tomllib, yaml
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("COV-02")
def test_coverage_gate_fails_closed(tmp_path):
    report={"totals":{"percent_covered_branch":84.0},"files":{"src/trading_app/data/client.py":{"summary":{"percent_covered_branch":99.0}}}}
    path=tmp_path/"coverage.json"; path.write_text(json.dumps(report))
    result=subprocess.run([sys.executable,str(ROOT/"tools/check_branch_coverage.py"),str(path),"--matrix",str(ROOT/"matrix.yaml")],capture_output=True,text=True)
    assert result.returncode != 0
    assert "overall branch coverage" in result.stdout

@pytest.mark.requirement("COV-01")
def test_coverage_scope_and_thresholds():
    policy=tomllib.loads((ROOT/"pyproject.toml").read_text())["tool"]["coverage"]["run"]
    assert policy["source"] == ["trading_app"]
    matrix=yaml.safe_load((ROOT/"matrix.yaml").read_text())
    assert matrix["coverage"]["overall_branch_min"] == 85
    assert matrix["coverage"]["per_module_branch_min"] == 90

@pytest.mark.requirement("TOOLS-06")
def test_negative_below_threshold(tmp_path):
    report={"totals":{"percent_covered_branch":100.0},"files":{"src/trading_app/data/client.py":{"summary":{"percent_covered_branch":89.0}}}}
    path=tmp_path/"coverage.json"; path.write_text(json.dumps(report))
    result=subprocess.run([sys.executable,str(ROOT/"tools/check_branch_coverage.py"),str(path),"--matrix",str(ROOT/"matrix.yaml")],capture_output=True,text=True)
    assert result.returncode != 0
    assert "branch coverage" in result.stdout
