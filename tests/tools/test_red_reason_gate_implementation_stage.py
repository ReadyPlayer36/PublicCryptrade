"""Implementation-stage mode: passes allowed, but real failures are never excused."""
import pytest
from tests.tools.test_red_reason_gate import GATE, ROOT  # noqa: F401
import subprocess, sys

STUB = '<failure message="NotImplementedError">File "src/trading_app/data/binance_client.py", line 3\nNotImplementedError: stub</failure>'


def run(tmp_path, xml, code, *flags):
    path = tmp_path / "j.xml"
    path.write_text(xml)
    return subprocess.run([sys.executable, str(GATE), str(path), "--pytest-exit-code", str(code), *flags], capture_output=True, text=True)


@pytest.mark.requirement("TOOLS-04")
def test_passes_are_allowed_in_implementation_stage_only(tmp_path):
    xml = '<testsuite tests="2"><testcase classname="tests.unit.test_a" name="test_b"/>' \
          f'<testcase classname="tests.unit.test_a" name="test_c">{STUB}</testcase></testsuite>'
    assert run(tmp_path, xml, 1, "--implementation-stage").returncode == 0
    assert run(tmp_path, xml, 1).returncode != 0


@pytest.mark.requirement("TOOLS-04")
def test_real_assertion_failure_is_never_excused(tmp_path):
    xml = '<testsuite tests="1"><testcase classname="tests.unit.test_a" name="test_b"><failure message="assert 1 == 2">AssertionError</failure></testcase></testsuite>'
    result = run(tmp_path, xml, 1, "--implementation-stage")
    assert result.returncode != 0 and "not a production NotImplementedError stub" in result.stdout


@pytest.mark.requirement("TOOLS-04")
def test_collection_errors_and_skips_still_fail_in_implementation_stage(tmp_path):
    err = '<testsuite tests="0" errors="1"><error message="x">ImportError</error></testsuite>'
    assert run(tmp_path, err, 2, "--implementation-stage").returncode != 0
    skip = '<testsuite tests="1"><testcase classname="tests.unit.test_a" name="test_b"><skipped/></testcase></testsuite>'
    assert run(tmp_path, skip, 0, "--implementation-stage").returncode != 0


@pytest.mark.requirement("TOOLS-04")
def test_fully_implemented_suite_passes_in_implementation_stage(tmp_path):
    xml = '<testsuite tests="1"><testcase classname="tests.unit.test_a" name="test_b"/></testsuite>'
    assert run(tmp_path, xml, 0, "--implementation-stage").returncode == 0


@pytest.mark.requirement("TOOLS-04")
def test_known_hollow_placeholders_are_tolerated_only_when_listed(tmp_path):
    xml = '<testsuite tests="1"><testcase classname="tests.integration.test_h" name="test_hollow"><failure message="AttributeError">AttributeError: NoneType</failure></testcase></testsuite>'
    listed = tmp_path / "hollow.txt"
    listed.write_text("# comment\ntests/integration/test_h.py::test_hollow\n")
    ok = run(tmp_path, xml, 1, "--implementation-stage", "--hollow-allowlist", str(listed))
    assert ok.returncode == 0 and "KNOWN HOLLOW placeholders failing=1" in ok.stdout
    other = tmp_path / "other.txt"
    other.write_text("tests/integration/test_other.py::test_x\n")
    assert run(tmp_path, xml, 1, "--implementation-stage", "--hollow-allowlist", str(other)).returncode != 0
    assert run(tmp_path, xml, 1, "--hollow-allowlist", str(listed)).returncode != 0    # not honoured outside implementation stage
