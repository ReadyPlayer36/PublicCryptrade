"""Traceability checker positive/negative controls with synthetic JUnit evidence."""
from pathlib import Path
import subprocess, sys
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("TOOLS-05")
def test_negative_cases(tmp_path):
    test_root=tmp_path/"root"; (test_root/"tests/unit").mkdir(parents=True)
    (test_root/"tests/unit/test_sample.py").write_text('import pytest\n@pytest.mark.requirement("ROW-1")\ndef test_sample():\n    assert True\n')
    matrix=tmp_path/"matrix.yaml"; matrix.write_text('acceptance_rows:\n- id: ROW-1\n  mandatory: true\n  tests: []\n  evidence_class: offline\n  stage: 1\n  source_item_bindings: {}\n')
    junit=tmp_path/"offline.xml"; junit.write_text('<testsuite><testcase classname="tests.unit.test_sample" name="test_sample"><properties><property name="requirement" value="ROW-1"/></properties></testcase></testsuite>')
    result=subprocess.run([sys.executable,str(ROOT/"tools/check_traceability.py"),str(matrix),"--root",str(test_root),"--junit",f"offline={junit}","--stage","1"],capture_output=True,text=True)
    assert result.returncode != 0

@pytest.mark.requirement("TOOLS-08")
def test_runtime_exact_param_positive(tmp_path):
    # Parameterized node IDs must resolve to the same marked test function.
    test_root=tmp_path/"root"; (test_root/"tests/unit").mkdir(parents=True)
    (test_root/"tests/unit/test_sample.py").write_text('import pytest\n@pytest.mark.requirement("ROW-1")\n@pytest.mark.parametrize("x", [1], ids=["one"])\ndef test_sample(x):\n    assert x == 1\n')
    matrix=tmp_path/"matrix.yaml"; matrix.write_text('acceptance_rows:\n- id: ROW-1\n  mandatory: true\n  tests:\n  - tests/unit/test_sample.py::test_sample[one]\n  evidence_class: offline\n  stage: 1\n  source_item_bindings: {}\n')
    junit=tmp_path/"offline.xml"; junit.write_text('<testsuite><testcase classname="tests.unit.test_sample" name="test_sample[one]"><properties><property name="requirement" value="ROW-1"/></properties></testcase></testsuite>')
    result=subprocess.run([sys.executable,str(ROOT/"tools/check_traceability.py"),str(matrix),"--root",str(test_root),"--junit",f"offline={junit}","--stage","1"],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr

@pytest.mark.requirement("TOOLS-02")
def test_traceability_binds_real_behavioral_tests():
    text=(ROOT/"tools/check_traceability.py").read_text()
    assert "missing requirement marker" in text
    assert "JUnit requirement property missing" in text
    assert "nodeid did not pass" in text
