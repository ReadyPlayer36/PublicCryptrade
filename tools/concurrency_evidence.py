"""Run the separate-process concurrency suite several times and archive logs, JUnit and a reproducible summary.

Output (default artifacts/concurrency-evidence/stability): run-N/{pytest-output.txt, junit.xml, *.json evidence}
and summary.json. Exit code 1 if any run fails, no run produced evidence, or a run's evidence is unreadable.
"""
from __future__ import annotations

import argparse
import json
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
DEFAULT_OUT = ROOT / "artifacts" / "concurrency-evidence" / "stability"


def junit_counts(path: Path) -> dict:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return {"tests": None, "failures": None, "errors": None, "skipped": None}
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    attrs = suite.attrib if suite is not None else {}
    return {k: int(attrs.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}


def run_once(index: int, target: str, out: Path) -> dict:
    run_dir = out / f"run-{index}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CONCURRENCY_EVIDENCE_DIR": str(run_dir)}
    started = time.time()
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={run_dir / 'junit.xml'}", target],
                               cwd=ROOT, env=env, capture_output=True, text=True)
    seconds = round(time.time() - started, 3)
    (run_dir / "pytest-output.txt").write_text(completed.stdout + ("\n--- stderr ---\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
    evidence, problems = [], []
    for file in sorted(run_dir.glob("*.json")):
        if file.name in ("summary.json",):
            continue
        try:
            evidence.append(json.loads(file.read_text(encoding="utf-8")))
        except Exception:
            problems.append(f"unreadable evidence file: {file.name}")
    return {"run": index, "exit_code": completed.returncode, "seconds": seconds, **junit_counts(run_dir / "junit.xml"),
            "evidence_files": len(evidence), "overlap_observed": sum(1 for e in evidence if (e.get("max_concurrency") or 0) >= 2),
            "integrity_ok": all((e.get("database") or {}).get("integrity_check") == "ok" for e in evidence) if evidence else False,
            "problems": problems}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.runs < 1:
        print("CONCURRENCY EVIDENCE FAIL: --runs must be >= 1")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    runs = [run_once(i, args.target, args.out) for i in range(1, args.runs + 1)]
    errors = []
    for run in runs:
        if run["exit_code"] != 0:
            errors.append(f"run {run['run']} failed (exit {run['exit_code']})")
        if run["evidence_files"] == 0:
            errors.append(f"run {run['run']} produced no evidence files (fail closed)")
        if not run["integrity_ok"]:
            errors.append(f"run {run['run']}: database integrity not confirmed ok")
        errors.extend(f"run {run['run']}: {p}" for p in run["problems"])
    summary = {"schema": 1, "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "target": args.target,
               "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "platform": platform.platform(), "cpu_count": os.cpu_count()},
               "runs": runs, "all_passed": not errors, "errors": errors}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    verdict = "PASS" if not errors else "FAIL"
    print(f"CONCURRENCY EVIDENCE {verdict}: {len(runs)} run(s), "
          f"{sum(r['evidence_files'] for r in runs)} evidence file(s), overlap observed in {sum(r['overlap_observed'] for r in runs)}")
    for error in errors:
        print(" - " + error)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
