"""The concurrency evidence archive: per-scenario JSON records and the repeat-run summary tool."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.process_runner import (current_label, environment, integrity_and_uniqueness_path, make_database, make_evidence_record, max_concurrency,
                                           run_workers, scrub_stderr, write_evidence, STDERR_TAIL_CHARS)

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "concurrency_evidence.py"


@pytest.mark.requirement("EVIDENCE-01")
def test_max_concurrency_counts_overlapping_windows():
    assert max_concurrency([]) == 0
    assert max_concurrency([(0.0, 1.0)]) == 1
    assert max_concurrency([(0.0, 1.0), (1.0, 2.0)]) == 1               # touching windows are not simultaneous
    assert max_concurrency([(0.0, 2.0), (1.0, 3.0)]) == 2
    assert max_concurrency([(0.0, 4.0), (1.0, 3.0), (2.0, 5.0), (6.0, 7.0)]) == 3


@pytest.mark.requirement("EVIDENCE-01")
def test_stderr_tail_is_scrubbed_and_truncated(tmp_path):
    db = tmp_path / "shared.db"
    text = f"Traceback ... File '{db}' line 3\nopen {tmp_path}/x/y failed\n"
    scrubbed = scrub_stderr(text, tmp_path, db)
    assert str(tmp_path) not in scrubbed and "<db>" in scrubbed and "<tmp>/x/y" in scrubbed
    long = "A" * (STDERR_TAIL_CHARS + 500) + f" end {db}"
    tail = scrub_stderr(long, tmp_path, db)
    assert len(tail) == STDERR_TAIL_CHARS and tail.endswith("end <db>") and str(tmp_path) not in tail      # keeps the END, which holds the error


@pytest.mark.requirement("EVIDENCE-01")
def test_write_evidence_and_labels(tmp_path, monkeypatch):
    path = write_evidence({"label": "some_scenario", "x": 1}, tmp_path)
    assert path.parent == tmp_path and path.name.startswith("some_scenario-") and json.loads(path.read_text()) == {"label": "some_scenario", "x": 1}
    assert current_label() == "test_write_evidence_and_labels"           # taken from the running test's name
    env = environment()
    assert {"python", "sqlite", "sqlalchemy", "platform", "cpu_count"} <= set(env) and all(env[k] for k in ("python", "sqlite", "sqlalchemy"))


@pytest.mark.requirement("EVIDENCE-01")
def test_a_real_scenario_archives_complete_evidence_without_paths_or_secrets(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    monkeypatch.setenv("CONCURRENCY_EVIDENCE_DIR", str(evidence))
    db, repository = make_database(tmp_path)
    results = run_workers(tmp_path, db, [(0, 40, "1"), (20, 40, "1")], label="evidence_smoke")
    assert all(r["ok"] for r in results)
    (file,) = list(evidence.glob("evidence_smoke-*.json"))
    record = json.loads(file.read_text())
    assert record["schema"] == 1 and record["label"] == "evidence_smoke" and record["barrier"] == "file-based start barrier"
    assert record["environment"]["python"] and record["environment"]["sqlite"]
    assert [w["spec"] for w in record["workers"]] == [{"start": 0, "count": 40, "volume": "1"}, {"start": 20, "count": 40, "volume": "1"}]
    assert all(w["returncode"] == 0 and w["result"]["ok"] and w["metrics"]["elapsed_s"] >= 0 and w["metrics"]["pid"] for w in record["workers"])
    assert record["database"] == {"file": "shared.db", "rows": 60, "distinct_keys": 60, "integrity_check": "ok"}
    assert record["max_concurrency"] in (1, 2) and record["release_to_finish_s"] >= 0
    assert sum(w["result"]["inserted"] for w in record["workers"]) == 60
    text = file.read_text()
    assert str(tmp_path) not in text and "/home/" not in text and "token" not in text.lower() and "secret" not in text.lower()
    assert integrity_and_uniqueness_path(db) == ("ok", 60, 60)


def write_target(tmp_path, name, body):
    target = tmp_path / name
    target.write_text("import pytest\nfrom tests.fixtures.process_runner import make_evidence_record, write_evidence\n\n" + body)
    return target


def run_tool(tmp_path, target, runs=2, *extra):
    out = tmp_path / "out"
    done = subprocess.run([sys.executable, str(TOOL), "--runs", str(runs), "--target", str(target), "--out", str(out), *extra],
                          cwd=ROOT, capture_output=True, text=True, timeout=180)
    return done, out


def scenario(windows="[(100.0, 101.0), (100.5, 101.5)]", label="good", extra="", assertion="assert True"):
    return f"""
def test_ok():
    record = make_evidence_record("{label}", {windows})
{extra}
    write_evidence(record)
    {assertion}
"""


GOOD = scenario()
EXPECT_GOOD = ("--expect", "good:2")


@pytest.mark.requirement("EVIDENCE-01")
def test_tool_archives_logs_junit_evidence_and_a_summary_for_every_run(tmp_path):
    done, out = run_tool(tmp_path, write_target(tmp_path, "test_good.py", GOOD), 2, *EXPECT_GOOD)
    assert done.returncode == 0 and "CONCURRENCY EVIDENCE PASS: 2 run(s), 2 evidence file(s), overlap observed in 2" in done.stdout
    summary = json.loads((out / "summary.json").read_text())
    assert summary["all_passed"] is True and summary["errors"] == [] and len(summary["runs"]) == 2 and summary["expected"] == {"good": [2]}
    assert {"python", "sqlite", "platform", "cpu_count"} <= set(summary["environment"])
    for n in (1, 2):
        run_dir = out / f"run-{n}"
        assert (run_dir / "pytest-output.txt").read_text().strip() and (run_dir / "junit.xml").exists() and len(list(run_dir.glob("good-*.json"))) == 1
    assert all(r["exit_code"] == 0 and r["tests"] == 1 and r["failures"] == 0 and r["integrity_ok"] and r["seconds"] >= 0 for r in summary["runs"])
    assert summary["runs"][0]["scenarios"][0]["max_concurrency"] == 2 and summary["runs"][0]["scenarios"][0]["min_overlap_degree"] == 1


@pytest.mark.requirement("EVIDENCE-01")
@pytest.mark.parametrize("name,body,expected", [
    ("failing", scenario(assertion="assert False"), "failed (exit"),
    ("no_evidence", "def test_ok():\n    assert True\n", "produced no evidence files (fail closed)"),
    ("bad_integrity", scenario(extra='    record["database"]["integrity_check"] = "corrupt"'), "database integrity not confirmed ok"),
    ("duplicate_rows", scenario(extra='    record["database"]["distinct_keys"] = 9'), "rows are not unique (rows=10, distinct_keys=9)"),
    ("worker_exit", scenario(extra='    record["workers"][1]["returncode"] = 3'), "worker 1 did not exit 0"),
    ("bad_result", scenario(extra='    record["workers"][0]["result"] = {"inserted": 1}'), "worker 0 has no well-formed result"),
    ("unreadable", scenario().replace("    write_evidence(record)", '    (__import__("pathlib").Path(__import__("os").environ["CONCURRENCY_EVIDENCE_DIR"]) / "junk.json").write_text("{nope")\n    write_evidence(record)'),
     "unreadable evidence file"),
])
def test_tool_fails_closed_on_the_existing_requirements(tmp_path, name, body, expected):
    done, out = run_tool(tmp_path, write_target(tmp_path, f"test_{name}.py", body), 1, *EXPECT_GOOD)
    assert done.returncode == 1 and expected in done.stdout and "CONCURRENCY EVIDENCE FAIL" in done.stdout
    summary = json.loads((out / "summary.json").read_text())
    assert summary["all_passed"] is False and summary["errors"]


@pytest.mark.requirement("EVIDENCE-01")
@pytest.mark.parametrize("name,body,expected", [
    ("disjoint", scenario("[(100.0, 101.0), (102.0, 103.0)]"), "no temporal overlap between the workers"),
    ("touching", scenario("[(100.0, 101.0), (101.0, 102.0)]"), "no temporal overlap between the workers"),
    ("lying_max", scenario("[(100.0, 101.0), (102.0, 103.0)]", extra='    record["max_concurrency"] = 2'), "no temporal overlap"),
    ("lying_max_value", scenario(extra='    record["max_concurrency"] = 5'), "recorded max_concurrency 5 does not match the recomputed value 2"),
    ("missing_recorded_max", scenario(extra='    del record["max_concurrency"]'), "recorded max_concurrency None does not match"),
    ("isolated_worker", scenario("[(100.0, 101.0), (100.5, 101.5), (200.0, 201.0)]"), "worker 2 overlapped no other worker"),
    ("no_metrics", scenario(extra='    record["workers"][0]["metrics"] = {}'), "worker 0 has no timing metrics"),
    ("missing_metrics_key", scenario(extra='    del record["workers"][1]["metrics"]'), "worker 1 has no timing metrics"),
    ("string_time", scenario(extra='    record["workers"][0]["metrics"]["started_at"] = "100"'), "worker 0 has malformed timing"),
    ("nan_time", scenario(extra='    record["workers"][0]["metrics"]["finished_at"] = float("nan")'), "worker 0 has malformed timing"),
    ("inf_time", scenario(extra='    record["workers"][0]["metrics"]["finished_at"] = float("inf")'), "worker 0 has malformed timing"),
    ("zero_time", scenario(extra='    record["workers"][0]["metrics"]["started_at"] = 0'), "worker 0 has malformed timing"),
    ("bool_time", scenario(extra='    record["workers"][0]["metrics"]["started_at"] = True'), "worker 0 has malformed timing"),
    ("backwards", scenario(extra='    record["workers"][0]["metrics"]["finished_at"] = 99.0'), "worker 0 finished before it started"),
    ("no_pid", scenario(extra='    record["workers"][0]["metrics"]["pid"] = None'), "worker 0 has no process id"),
])
def test_tool_fails_closed_unless_the_windows_really_overlapped(tmp_path, name, body, expected):
    done, _ = run_tool(tmp_path, write_target(tmp_path, f"test_{name}.py", body), 1, *EXPECT_GOOD)
    assert done.returncode == 1 and expected in done.stdout, done.stdout


@pytest.mark.requirement("EVIDENCE-01")
@pytest.mark.parametrize("name,body,expect,expected", [
    ("wrong_label", scenario(label="other"), ("--expect", "good:2"), "expected scenario 'good' with 2 workers was not recorded"),
    ("wrong_size", scenario(), ("--expect", "good:4"), "expected scenario 'good' with 4 workers was not recorded"),
    ("missing_second", scenario(), ("--expect", "good:2,2"), "expected scenario 'good' with 2 workers was not recorded"),
    ("single_worker_only", scenario("[(100.0, 101.0)]"), ("--expect", "good:2"), "expected scenario 'good' with 2 workers was not recorded"),
    ("unexpected_extra", scenario(label="rogue"), ("--expect", "good:2"), "unexpected multi-worker scenario 'rogue'"),
])
def test_tool_fails_closed_when_expected_scenarios_are_missing_or_unexpected(tmp_path, name, body, expect, expected):
    done, _ = run_tool(tmp_path, write_target(tmp_path, f"test_{name}.py", body), 1, *expect)
    assert done.returncode == 1 and expected in done.stdout, done.stdout


@pytest.mark.requirement("EVIDENCE-01")
def test_single_worker_setup_records_of_an_expected_scenario_are_allowed(tmp_path):
    body = """
def test_ok():
    write_evidence(make_evidence_record("good", [(100.0, 101.0)]))
    write_evidence(make_evidence_record("good", [(100.0, 101.0), (100.5, 101.5)]))
"""
    done, _ = run_tool(tmp_path, write_target(tmp_path, "test_setup.py", body), 1, *EXPECT_GOOD)
    assert done.returncode == 0, done.stdout


@pytest.mark.requirement("EVIDENCE-01")
def test_a_custom_target_without_a_manifest_fails_closed_unless_explicitly_allowed(tmp_path):
    target = write_target(tmp_path, "test_good.py", GOOD)
    done, _ = run_tool(tmp_path, target, 1)
    assert done.returncode == 1 and "no expected scenarios for this target (fail closed)" in done.stdout
    allowed, _ = run_tool(tmp_path, target, 1, "--allow-no-expectations")
    assert allowed.returncode == 0                                              # overlap and integrity are STILL verified without a manifest
    bad = write_target(tmp_path, "test_bad.py", scenario("[(100.0, 101.0), (102.0, 103.0)]"))
    still, _ = run_tool(tmp_path, bad, 1, "--allow-no-expectations")
    assert still.returncode == 1 and "no temporal overlap" in still.stdout


@pytest.mark.requirement("EVIDENCE-01")
@pytest.mark.parametrize("value", ["good", "good:", ":2", "good:1", "good:x", "good:2,0", "good:2,x"])
def test_malformed_expect_arguments_fail_closed(tmp_path, value):
    done = subprocess.run([sys.executable, str(TOOL), "--runs", "1", "--target", "x.py", "--expect", value, "--out", str(tmp_path / "o")],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 1 and "--expect needs LABEL:N" in done.stdout


@pytest.mark.requirement("EVIDENCE-01")
def test_verify_only_checks_an_existing_directory_without_running_tests(tmp_path):
    good = tmp_path / "good"
    write_evidence(make_evidence_record("good", [(100.0, 101.0), (100.5, 101.5)]), good)
    ok = subprocess.run([sys.executable, str(TOOL), "--verify-only", str(good), "--expect", "good:2"], cwd=ROOT, capture_output=True, text=True)
    assert ok.returncode == 0 and "CONCURRENCY EVIDENCE VERIFY PASS: 1 evidence file(s), overlap observed in 1 scenario(s)" in ok.stdout
    assert json.loads((good / "verification.json").read_text())["all_passed"] is True
    again = subprocess.run([sys.executable, str(TOOL), "--verify-only", str(good), "--expect", "good:2"], cwd=ROOT, capture_output=True, text=True)
    assert again.returncode == 0 and "1 evidence file(s)" in again.stdout           # its own verification.json is not mistaken for evidence
    bad = tmp_path / "bad"
    write_evidence(make_evidence_record("good", [(100.0, 101.0), (102.0, 103.0)]), bad)
    failed = subprocess.run([sys.executable, str(TOOL), "--verify-only", str(bad), "--expect", "good:2"], cwd=ROOT, capture_output=True, text=True)
    assert failed.returncode == 1 and "no temporal overlap" in failed.stdout
    (tmp_path / "empty").mkdir()
    for target, message in ((tmp_path / "empty", "no evidence files found (fail closed)"), (tmp_path / "missing", "is not a directory")):
        result = subprocess.run([sys.executable, str(TOOL), "--verify-only", str(target), "--expect", "good:2"], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 1 and message in result.stdout


@pytest.mark.requirement("EVIDENCE-01")
def test_tool_rejects_zero_runs(tmp_path):
    done = subprocess.run([sys.executable, str(TOOL), "--runs", "0", "--out", str(tmp_path / "o")], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 1 and "--runs must be >= 1" in done.stdout


@pytest.mark.requirement("EVIDENCE-01")
def test_overlap_helpers_agree_with_the_runner_and_handle_edge_cases():
    from tools.concurrency_evidence import max_concurrency as tool_max, overlap_degrees
    from tests.fixtures.process_runner import max_concurrency as runner_max
    for windows in ([], [(1.0, 2.0)], [(1.0, 2.0), (2.0, 3.0)], [(1.0, 4.0), (2.0, 3.0), (3.5, 5.0)], [(1.0, 2.0), (1.0, 2.0)]):
        assert tool_max(windows) == runner_max(windows)
    assert overlap_degrees([(1.0, 4.0), (2.0, 3.0), (3.5, 5.0), (9.0, 10.0)]) == [2, 1, 1, 0]
    assert overlap_degrees([(1.0, 2.0), (2.0, 3.0)]) == [0, 0]                      # touching is not overlapping


@pytest.mark.requirement("EVIDENCE-01")
def test_the_built_in_manifest_matches_the_real_concurrency_suite():
    import ast
    from tools.concurrency_evidence import DEFAULT_TARGET, EXPECTED_SCENARIOS
    tree = ast.parse((ROOT / DEFAULT_TARGET).read_text())
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    assert set(EXPECTED_SCENARIOS) == names                                          # every real test is expected, and nothing else
    assert all(isinstance(v, list) and v and all(isinstance(c, int) and c >= 2 for c in v) for v in EXPECTED_SCENARIOS.values())


@pytest.mark.requirement("EVIDENCE-01")
def test_the_real_suite_passes_the_strict_gate(tmp_path):
    done = subprocess.run([sys.executable, str(TOOL), "--runs", "1", "--out", str(tmp_path / "real")], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout
    summary = json.loads((tmp_path / "real" / "summary.json").read_text())
    multi = [s for s in summary["runs"][0]["scenarios"] if s["workers"] >= 2]
    assert len(multi) == 4 and all(s["max_concurrency"] >= 2 and s["min_overlap_degree"] >= 1 for s in multi)
