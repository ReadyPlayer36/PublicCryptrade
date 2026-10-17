"""Red-reason gate rejects test-body placeholders, unexpected passes, and collection errors."""
import subprocess, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
GATE=ROOT/"tools/red_reason_gate.py"

def run_gate(tmp_path, xml, exit_code=1):
    path=tmp_path/"junit.xml"; path.write_text(xml)
    return subprocess.run([sys.executable,str(GATE),str(path),"--pytest-exit-code",str(exit_code)],capture_output=True,text=True)

@pytest.mark.requirement("TOOLS-04")
def test_source_stub_notimplemented_error_is_expected_red(tmp_path):
    xml='''<testsuite tests="1" failures="1"><testcase classname="tests.unit.test_x" name="test_x"><failure message="NotImplementedError">Traceback\n  File "src/trading_app/data/client.py", line 3\nNotImplementedError: stub</failure></testcase></testsuite>'''
    result=run_gate(tmp_path,xml)
    assert result.returncode == 0, result.stdout + result.stderr

@pytest.mark.requirement("TOOLS-04")
def test_test_body_notimplemented_error_is_rejected(tmp_path):
    xml='''<testsuite tests="1" failures="1"><testcase classname="tests.unit.test_x" name="test_x"><failure message="NotImplementedError">Traceback\n  File "tests/unit/test_x.py", line 3\nNotImplementedError: placeholder</failure></testcase></testsuite>'''
    result=run_gate(tmp_path,xml)
    assert result.returncode != 0
    assert "not a production NotImplementedError stub" in result.stdout

@pytest.mark.requirement("TOOLS-04")
def test_unexpected_behavioral_pass_is_rejected(tmp_path):
    xml='<testsuite tests="1"><testcase classname="tests.unit.test_x" name="test_behavior" /></testsuite>'
    result=run_gate(tmp_path,xml,0)
    assert result.returncode != 0
    assert "passed against stubs" in result.stdout

@pytest.mark.requirement("TOOLS-04")
def test_collection_error_is_rejected(tmp_path):
    xml='<testsuite tests="0" errors="1"><error message="collection failed">ImportError</error></testsuite>'
    result=run_gate(tmp_path,xml,2)
    assert result.returncode != 0
    assert "SUITE-LEVEL error" in result.stdout
