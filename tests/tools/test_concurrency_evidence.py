"""The concurrency evidence archive: per-scenario JSON records and the repeat-run summary tool."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.process_runner import (current_label, environment, integrity_and_uniqueness_path, make_database, max_concurrency,
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
    target.write_text("import pytest\nfrom tests.fixtures.process_runner import write_evidence\n\n" + body)
    return target


def run_tool(tmp_path, target, runs=2):
    out = tmp_path / "out"
    done = subprocess.run([sys.executable, str(TOOL), "--runs", str(runs), "--target", str(target), "--out", str(out)],
                          cwd=ROOT, capture_output=True, text=True, timeout=180)
    return done, out


GOOD = '''
def test_ok():
    write_evidence({"label": "good", "max_concurrency": 2, "database": {"integrity_check": "ok", "rows": 1}})
    assert True
'''


@pytest.mark.requirement("EVIDENCE-01")
def test_tool_archives_logs_junit_evidence_and_a_summary_for_every_run(tmp_path):
    done, out = run_tool(tmp_path, write_target(tmp_path, "test_good.py", GOOD), runs=2)
    assert done.returncode == 0 and "CONCURRENCY EVIDENCE PASS: 2 run(s), 2 evidence file(s), overlap observed in 2" in done.stdout
    summary = json.loads((out / "summary.json").read_text())
    assert summary["all_passed"] is True and summary["errors"] == [] and len(summary["runs"]) == 2 and summary["target"].endswith("test_good.py")
    assert {"python", "sqlite", "platform", "cpu_count"} <= set(summary["environment"])
    for n in (1, 2):
        run_dir = out / f"run-{n}"
        assert (run_dir / "pytest-output.txt").read_text().strip() and (run_dir / "junit.xml").exists() and len(list(run_dir.glob("good-*.json"))) == 1
    assert all(r["exit_code"] == 0 and r["tests"] == 1 and r["failures"] == 0 and r["integrity_ok"] and r["seconds"] >= 0 for r in summary["runs"])


@pytest.mark.requirement("EVIDENCE-01")
@pytest.mark.parametrize("name,body,expected", [
    ("failing", GOOD.replace("assert True", "assert False"), "failed (exit"),
    ("no_evidence", "def test_ok():\n    assert True\n", "produced no evidence files (fail closed)"),
    ("bad_integrity", GOOD.replace('"ok"', '"corrupt"'), "database integrity not confirmed ok"),
    ("unreadable", GOOD.replace('    assert True', '    (__import__("pathlib").Path(__import__("os").environ["CONCURRENCY_EVIDENCE_DIR"]) / "junk.json").write_text("{nope")'),
     "unreadable evidence file"),
])
def test_tool_fails_closed(tmp_path, name, body, expected):
    done, out = run_tool(tmp_path, write_target(tmp_path, f"test_{name}.py", body), runs=1)
    assert done.returncode == 1 and expected in done.stdout and "CONCURRENCY EVIDENCE FAIL" in done.stdout
    summary = json.loads((out / "summary.json").read_text())
    assert summary["all_passed"] is False and summary["errors"]


@pytest.mark.requirement("EVIDENCE-01")
def test_tool_rejects_zero_runs(tmp_path):
    done = subprocess.run([sys.executable, str(TOOL), "--runs", "0", "--out", str(tmp_path / "o")], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 1 and "--runs must be >= 1" in done.stdout
