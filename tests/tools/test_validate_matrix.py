"""Matrix validator positive and negative controls."""
from pathlib import Path
import subprocess, sys, yaml
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("TOOLS-08")
def test_missing_item_binding_rejected(tmp_path):
    matrix = yaml.safe_load((ROOT/"matrix.yaml").read_text())
    matrix["acceptance_rows"][0]["source_item_bindings"] = {"[M1 §28 #1]": ["tests/unit/test_config.py::not_a_real_test"]}
    path=tmp_path/"matrix.yaml"; path.write_text(yaml.safe_dump(matrix, sort_keys=False))
    result=subprocess.run([sys.executable,str(ROOT/"tools/validate_matrix.py"),str(path),"--schema",str(ROOT/"matrix_schema.json"),"--m1",str(ROOT/"docs/source/milestone_1.md"),"--m12",str(ROOT/"docs/source/milestone_1_2.md")],capture_output=True,text=True)
    assert result.returncode != 0

@pytest.mark.requirement("TOOLS-01")
def test_validate_matrix_full_contract():
    result=subprocess.run([sys.executable,str(ROOT/"tools/validate_matrix.py"),str(ROOT/"matrix.yaml"),"--schema",str(ROOT/"matrix_schema.json"),"--m1",str(ROOT/"docs/source/milestone_1.md"),"--m12",str(ROOT/"docs/source/milestone_1_2.md")],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
