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


def _final_tree(root, hollow=False, listed=None):
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_a.py").write_text("def test_a():\n    " + ("pass\n" if hollow else "assert 1 + 1 == 2\n"))
    if listed is not None:
        (root / "tests" / "hollow_allowlist.txt").write_text(listed)
    return root / "tests" / "hollow_allowlist.txt"


PASSING = '<testsuite tests="1"><testcase classname="tests.test_a" name="test_a"/></testsuite>'


@pytest.mark.requirement("TOOLS-05")
def test_final_gate_passes_only_when_everything_is_real_and_green(tmp_path):
    allow = _final_tree(tmp_path, listed="# empty\n")
    result = run(tmp_path, PASSING, 0, "--final-gate", "--root", str(tmp_path), "--hollow-allowlist", str(allow))
    assert result.returncode == 0 and "FINAL GATE PASS" in result.stdout


@pytest.mark.requirement("TOOLS-05")
def test_final_gate_rejects_hollow_tests_regardless_of_the_allowlist(tmp_path):
    allow = _final_tree(tmp_path, hollow=True, listed="tests/test_a.py::test_a\n")
    result = run(tmp_path, PASSING, 0, "--final-gate", "--root", str(tmp_path), "--hollow-allowlist", str(allow))
    assert result.returncode != 0 and "allowlist must be empty" in result.stdout and "hollow test(s) remain" in result.stdout


@pytest.mark.requirement("TOOLS-05")
def test_final_gate_fails_closed_on_missing_or_malformed_allowlist(tmp_path):
    _final_tree(tmp_path)
    missing = run(tmp_path, PASSING, 0, "--final-gate", "--root", str(tmp_path), "--hollow-allowlist", str(tmp_path / "nope.txt"))
    assert missing.returncode != 0 and "missing" in missing.stdout
    bad = tmp_path / "bad.txt"
    bad.write_text("not an entry\n")
    malformed = run(tmp_path, PASSING, 0, "--final-gate", "--root", str(tmp_path), "--hollow-allowlist", str(bad))
    assert malformed.returncode != 0 and "malformed" in malformed.stdout


@pytest.mark.requirement("TOOLS-05")
def test_final_gate_rejects_failures_skips_nonzero_exit_and_stage_mode(tmp_path):
    allow = _final_tree(tmp_path, listed="")
    flags = ("--final-gate", "--root", str(tmp_path), "--hollow-allowlist", str(allow))
    failing = '<testsuite tests="1"><testcase classname="tests.test_a" name="test_a"><failure message="x">x</failure></testcase></testsuite>'
    skipped = '<testsuite tests="1"><testcase classname="tests.test_a" name="test_a"><skipped/></testcase></testsuite>'
    assert run(tmp_path, failing, 1, *flags).returncode != 0
    assert run(tmp_path, skipped, 0, *flags).returncode != 0
    assert run(tmp_path, PASSING, 1, *flags).returncode != 0
    assert run(tmp_path, PASSING, 0, *flags, "--implementation-stage").returncode != 0


@pytest.mark.requirement("TOOLS-04")
def test_gate_reports_error_only_testcases_cleanly_instead_of_crashing(tmp_path):
    """Regression: a testcase with <error> and no <failure> (e.g. a setup error) used to crash the gate with a traceback."""
    xml = ('<testsuite tests="1" errors="1"><testcase classname="tests.unit.test_a" name="test_b">'
           '<error message="failed on setup with ResourceWarning">ResourceWarning: unclosed socket</error></testcase></testsuite>')
    result = run(tmp_path, xml, 1, "--implementation-stage")
    assert result.returncode == 1
    assert "TESTCASE-LEVEL error" in result.stdout and "not an expected-red result: tests/unit/test_a.py::test_b" in result.stdout
    assert "ResourceWarning" in result.stdout                      # the reason is shown, one line
    assert "Traceback" not in result.stderr and "Traceback" not in result.stdout


@pytest.mark.requirement("TOOLS-04")
def test_gate_labels_suite_level_errors_differently_from_testcase_errors(tmp_path):
    xml = '<testsuite tests="0" errors="1"><error message="collection failure in tests/x.py">ImportError</error></testsuite>'
    result = run(tmp_path, xml, 2, "--implementation-stage")
    assert result.returncode == 1 and "SUITE-LEVEL error" in result.stdout and "TESTCASE-LEVEL" not in result.stdout
