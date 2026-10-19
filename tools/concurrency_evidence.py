"""Run the separate-process concurrency suite several times, archive logs/JUnit/evidence, and VERIFY the evidence.

Output (default artifacts/concurrency-evidence/stability): run-N/{pytest-output.txt, junit.xml, *.json evidence}
and summary.json. The gate fails closed (exit 1) unless, in EVERY run:
  * pytest exited 0 and every worker exited 0;
  * every expected multi-worker scenario was recorded with the expected number of workers;
  * every multi-worker record has well-formed timing for every worker, its recorded ``max_concurrency`` equals the value
    RECOMPUTED from the raw windows, the windows really overlapped (>= 2 at once) and no worker ran in isolation;
  * the rows are unique (rows == distinct keys) and ``PRAGMA integrity_check`` returned ``ok``.

``--verify-only DIR`` applies the same checks to an existing evidence directory without running any tests.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = "tests/integration/test_concurrency.py"
# Authoritative manifest for the default target: scenario label (= test name) -> worker counts of the MULTI-worker records
# that must appear (single-worker setup records of the same test are allowed and ignored).
EXPECTED_SCENARIOS: dict[str, list[int]] = {
    "test_two_processes_overlap_without_duplicates": [2],
    "test_no_duplicate_rows_after_overlap": [4],
    "test_conflict_rolls_back_entire_transaction": [2],
    "test_racing_conflicting_writers_leave_exactly_one_complete_winner": [2],
}
DEFAULT_OUT = ROOT / "artifacts" / "concurrency-evidence" / "stability"


def junit_counts(path: Path) -> dict:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return {"tests": None, "failures": None, "errors": None, "skipped": None}
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    attrs = suite.attrib if suite is not None else {}
    return {k: int(attrs.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("not a finite positive number")
    return float(value)


def windows_of(record: dict) -> list[tuple[float, float]]:
    """Execution windows [started_at, finished_at] of every worker; raises ValueError if ANY timing is missing or malformed."""
    workers = record.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("no workers recorded")
    windows = []
    for index, worker in enumerate(workers):
        metrics = worker.get("metrics") if isinstance(worker, dict) else None
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError(f"worker {index} has no timing metrics")
        try:
            start, end = _number(metrics.get("started_at")), _number(metrics.get("finished_at"))
        except ValueError:
            raise ValueError(f"worker {index} has malformed timing") from None
        if end < start:
            raise ValueError(f"worker {index} finished before it started")
        if isinstance(metrics.get("pid"), bool) or not isinstance(metrics.get("pid"), int) or metrics["pid"] <= 0:
            raise ValueError(f"worker {index} has no process id")
        windows.append((start, end))
    return windows


def max_concurrency(windows: list[tuple[float, float]]) -> int:
    """Largest number of windows open at one instant; touching windows (one ends exactly when another starts) do not overlap."""
    events = sorted([(a, 1) for a, _ in windows] + [(b, -1) for _, b in windows], key=lambda e: (e[0], e[1]))
    best = current = 0
    for _, delta in events:
        current += delta
        best = max(best, current)
    return best


def overlap_degrees(windows: list[tuple[float, float]]) -> list[int]:
    """For each worker, how many OTHER workers' windows strictly overlap its own."""
    return [sum(1 for j, (c, d) in enumerate(windows) if i != j and a < d and c < b) for i, (a, b) in enumerate(windows)]


def verify_records(records: list[tuple[str, dict]], expected: dict[str, list[int]] | None) -> tuple[list[str], list[dict]]:
    """Verify one run's evidence records. Returns (errors, per-scenario info). ``expected`` None = no manifest was supplied."""
    errors: list[str] = []
    info: list[dict] = []
    seen: dict[str, list[int]] = {}
    for name, record in records:
        if not isinstance(record, dict) or record.get("schema") != 1 or not isinstance(record.get("label"), str) or not record["label"]:
            errors.append(f"{name}: not a schema-1 evidence record")
            continue
        label = record["label"]
        workers = record.get("workers")
        if not isinstance(workers, list) or not workers:
            errors.append(f"{name}: no workers recorded")
            continue
        database = record.get("database")
        if not isinstance(database, dict):
            errors.append(f"{name}: no database statistics")
        else:
            if database.get("integrity_check") != "ok":
                errors.append(f"{name}: database integrity check is not ok")
            rows, distinct = database.get("rows"), database.get("distinct_keys")
            if isinstance(rows, bool) or not isinstance(rows, int) or isinstance(distinct, bool) or not isinstance(distinct, int):
                errors.append(f"{name}: row statistics are malformed")
            elif rows != distinct:
                errors.append(f"{name}: rows are not unique (rows={rows}, distinct_keys={distinct})")
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict) or worker.get("returncode") != 0:
                errors.append(f"{name}: worker {index} did not exit 0")
            elif not isinstance(worker.get("result"), dict) or not isinstance(worker["result"].get("ok"), bool):
                errors.append(f"{name}: worker {index} has no well-formed result")
        entry = {"file": name, "label": label, "workers": len(workers)}
        if len(workers) >= 2:
            seen.setdefault(label, []).append(len(workers))
            try:
                windows = windows_of(record)
            except ValueError as exc:
                errors.append(f"{name}: {exc}")
            else:
                recomputed, degrees = max_concurrency(windows), overlap_degrees(windows)
                entry.update({"max_concurrency": recomputed, "min_overlap_degree": min(degrees)})
                if record.get("max_concurrency") != recomputed:
                    errors.append(f"{name}: recorded max_concurrency {record.get('max_concurrency')!r} does not match the recomputed value {recomputed}")
                if recomputed < 2:
                    errors.append(f"{name}: no temporal overlap between the workers (windows never overlap)")
                elif min(degrees) < 1:
                    errors.append(f"{name}: worker {degrees.index(0)} overlapped no other worker")
        info.append(entry)
    if expected is not None:
        for label, sizes in expected.items():
            found = list(seen.get(label, []))
            for size in sizes:
                if size in found:
                    found.remove(size)
                else:
                    errors.append(f"expected scenario {label!r} with {size} workers was not recorded")
        for label in seen:
            if label not in expected:
                errors.append(f"unexpected multi-worker scenario {label!r} (not in the manifest)")
    return errors, info


def load_records(directory: Path) -> tuple[list[tuple[str, dict]], list[str]]:
    records, problems = [], []
    for file in sorted(directory.glob("*.json")):
        if file.name in ("summary.json", "verification.json"):      # the tool's own outputs are not evidence
            continue
        try:
            records.append((file.name, json.loads(file.read_text(encoding="utf-8"))))
        except Exception:
            problems.append(f"unreadable evidence file: {file.name}")
    return records, problems


def run_once(index: int, target: str, out: Path, expected: dict[str, list[int]] | None) -> dict:
    run_dir = out / f"run-{index}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CONCURRENCY_EVIDENCE_DIR": str(run_dir)}
    started = time.time()
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={run_dir / 'junit.xml'}", target],
                               cwd=ROOT, env=env, capture_output=True, text=True)
    seconds = round(time.time() - started, 3)
    (run_dir / "pytest-output.txt").write_text(completed.stdout + ("\n--- stderr ---\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
    records, problems = load_records(run_dir)
    errors, scenarios = verify_records(records, expected)
    return {"run": index, "exit_code": completed.returncode, "seconds": seconds, **junit_counts(run_dir / "junit.xml"),
            "evidence_files": len(records), "scenarios": scenarios,
            "overlap_observed": sum(1 for s in scenarios if s.get("max_concurrency", 0) >= 2),
            "integrity_ok": bool(records) and not any("integrity" in e for e in errors),
            "problems": problems + errors}


def parse_expect(values: list[str]) -> dict[str, list[int]]:
    """--expect LABEL:N[,N...] (repeatable) -> {label: [worker counts]}; malformed input raises ValueError."""
    manifest: dict[str, list[int]] = {}
    for value in values:
        label, _, sizes = value.partition(":")
        try:
            counts = [int(x) for x in sizes.split(",")]
        except ValueError:
            counts = []
        if not label or not counts or any(c < 2 for c in counts):
            raise ValueError(f"--expect needs LABEL:N[,N...] with every N >= 2, got {value!r}")
        manifest.setdefault(label, []).extend(counts)
    return manifest


def resolve_expectations(args) -> dict[str, list[int]] | None:
    if args.expect:
        return parse_expect(args.expect)
    if args.target == DEFAULT_TARGET:
        return dict(EXPECTED_SCENARIOS)
    if args.allow_no_expectations:
        return None
    raise ValueError("no expected scenarios for this target (fail closed): pass --expect LABEL:N or --allow-no-expectations")


def report(title: str, errors: list[str], counts: str) -> int:
    print(f"{title} {'PASS' if not errors else 'FAIL'}: {counts}")
    for error in errors:
        print(" - " + error)
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--expect", action="append", default=[], metavar="LABEL:N[,N]",
                        help="expected multi-worker scenario and its worker count(s); overrides the built-in manifest")
    parser.add_argument("--allow-no-expectations", action="store_true",
                        help="for a custom --target only: run without a manifest (overlap and integrity are still verified for every multi-worker record)")
    parser.add_argument("--verify-only", type=Path, metavar="DIR", help="verify an existing evidence directory; run no tests")
    args = parser.parse_args(argv)
    try:
        expected = resolve_expectations(args)
    except ValueError as exc:
        print(f"CONCURRENCY EVIDENCE FAIL: {exc}")
        return 1

    if args.verify_only is not None:
        if not args.verify_only.is_dir():
            print(f"CONCURRENCY EVIDENCE FAIL: {args.verify_only} is not a directory")
            return 1
        records, problems = load_records(args.verify_only)
        errors, scenarios = verify_records(records, expected)
        errors = problems + errors
        if not records:
            errors.append("no evidence files found (fail closed)")
        (args.verify_only / "verification.json").write_text(json.dumps(
            {"schema": 1, "expected": expected, "scenarios": scenarios, "errors": errors, "all_passed": not errors}, indent=2, sort_keys=True), encoding="utf-8")
        return report("CONCURRENCY EVIDENCE VERIFY", errors, f"{len(records)} evidence file(s), overlap observed in "
                      f"{sum(1 for s in scenarios if s.get('max_concurrency', 0) >= 2)} scenario(s)")

    if args.runs < 1:
        print("CONCURRENCY EVIDENCE FAIL: --runs must be >= 1")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    runs = [run_once(i, args.target, args.out, expected) for i in range(1, args.runs + 1)]
    errors = []
    for run in runs:
        if run["exit_code"] != 0:
            errors.append(f"run {run['run']} failed (exit {run['exit_code']})")
        if run["evidence_files"] == 0:
            errors.append(f"run {run['run']} produced no evidence files (fail closed)")
        if not run["integrity_ok"]:
            errors.append(f"run {run['run']}: database integrity not confirmed ok")
        errors.extend(f"run {run['run']}: {p}" for p in run["problems"])
    summary = {"schema": 2, "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "target": args.target, "expected": expected,
               "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "cpu_count": os.cpu_count()},
               "runs": runs, "all_passed": not errors, "errors": errors}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return report("CONCURRENCY EVIDENCE", errors, f"{len(runs)} run(s), {sum(r['evidence_files'] for r in runs)} evidence file(s), "
                  f"overlap observed in {sum(r['overlap_observed'] for r in runs)}")


if __name__ == "__main__":
    raise SystemExit(main())
