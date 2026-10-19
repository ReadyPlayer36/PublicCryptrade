"""Runs several real worker processes against one SQLite file, released together by a start barrier."""
from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from trading_app.data.repository import CandleRepository, create_engine_from_url

WORKER = Path(__file__).with_name("concurrency_worker.py")
EVIDENCE_SCHEMA = 1
STDERR_TAIL_CHARS = 2000


def evidence_dir() -> Path:
    return Path(os.environ.get("CONCURRENCY_EVIDENCE_DIR") or Path(__file__).resolve().parents[2] / "artifacts" / "concurrency-evidence")


def current_label() -> str:
    current = os.environ.get("PYTEST_CURRENT_TEST", "unknown")
    return current.split("::")[-1].split(" ")[0] or "unknown"


def environment() -> dict:
    import sqlalchemy
    return {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "sqlalchemy": sqlalchemy.__version__,
            "platform": platform.platform(), "cpu_count": os.cpu_count()}


def max_concurrency(windows: list[tuple[float, float]]) -> int:
    """Largest number of workers whose [start, end] windows overlap at one instant (1 = they never overlapped)."""
    events = sorted([(start, 1) for start, _ in windows] + [(end, -1) for _, end in windows], key=lambda e: (e[0], e[1]))
    best = current = 0
    for _, delta in events:
        current += delta
        best = max(best, current)
    return best


def scrub_stderr(stderr: str, tmp_path: Path, db: Path) -> str:
    """Last STDERR_TAIL_CHARS characters, with temp and database paths replaced so no machine-specific path is archived."""
    return stderr.replace(str(db), "<db>").replace(str(tmp_path), "<tmp>")[-STDERR_TAIL_CHARS:]


def make_evidence_record(label: str, windows: list[tuple[float, float]], *, rows: int = 10, distinct: int | None = None, integrity: str = "ok",
                         returncodes: list[int] | None = None, recorded_max: int | None = None) -> dict:
    """A well-formed schema-1 evidence record for tests of the evidence gate (windows are (started_at, finished_at) pairs)."""
    workers = [{"index": n, "spec": {"start": n, "count": 1, "volume": "1"}, "returncode": (returncodes or [0] * len(windows))[n],
                "result": {"ok": True, "inserted": 1}, "stderr_tail": "",
                "metrics": {"pid": 1000 + n, "started_at": a, "finished_at": b, "elapsed_s": round(b - a, 6)}} for n, (a, b) in enumerate(windows)]
    return {"schema": EVIDENCE_SCHEMA, "label": label, "recorded_utc": "2026-01-01T00:00:00+00:00", "environment": environment(),
            "barrier": "file-based start barrier", "workers": workers, "release_to_finish_s": 1.0,
            "max_concurrency": recorded_max if recorded_max is not None else max_concurrency(windows),
            "database": {"file": "shared.db", "rows": rows, "distinct_keys": rows if distinct is None else distinct, "integrity_check": integrity}}


def write_evidence(record: dict, directory: Path | None = None) -> Path:
    """Archive one scenario as JSON. The record must already be free of secrets and absolute temp paths."""
    target = Path(directory) if directory is not None else evidence_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{record['label']}-{os.getpid()}-{int(time.time() * 1000)}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return path


def make_database(tmp_path: Path) -> tuple[Path, CandleRepository]:
    db = tmp_path / "shared.db"
    repository = CandleRepository(create_engine_from_url(f"sqlite:///{db}"))
    repository.create_tables()
    return db, repository


def run_workers(tmp_path: Path, db: Path, specs: list[tuple[int, int, str]], timeout: float = 90, label: str | None = None) -> list[dict]:
    """specs = [(start_index, count, volume), ...]; returns one result dict per worker, in order.

    Every call also archives a JSON evidence record (environment, parameters, per-worker results, exit codes,
    timings, stderr tails, overlap and final database statistics) under ``evidence_dir()``.
    """
    go = tmp_path / "go"
    procs, readies, outs = [], [], []
    for n, (start, count, volume) in enumerate(specs):
        ready, out = tmp_path / f"ready{n}", tmp_path / f"out{n}.json"
        readies.append(ready)
        outs.append(out)
        procs.append(subprocess.Popen([sys.executable, str(WORKER), str(db), str(ready), str(go), str(out), str(start), str(count), volume],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    deadline = time.time() + timeout
    while not all(r.exists() for r in readies):
        if time.time() > deadline or any(p.poll() not in (None, 0) for p in procs):
            for p in procs:
                p.kill()
            raise AssertionError("workers failed to start: " + " | ".join(p.communicate()[1] for p in procs))
        time.sleep(0.01)
    released_at = time.time()
    go.write_text("go")                                  # release every worker at (nearly) the same instant
    results, workers = [], []
    for n, (p, out) in enumerate(zip(procs, outs)):
        stdout, stderr = p.communicate(timeout=timeout)
        assert p.returncode == 0, stderr
        results.append(json.loads(out.read_text()))
        metrics_file = Path(str(out) + ".metrics.json")
        metrics = json.loads(metrics_file.read_text()) if metrics_file.exists() else {}
        scrubbed = scrub_stderr(stderr, tmp_path, db)
        workers.append({"index": n, "spec": {"start": specs[n][0], "count": specs[n][1], "volume": specs[n][2]},
                        "returncode": p.returncode, "result": results[-1], "metrics": metrics, "stderr_tail": scrubbed})
    windows = [(w["metrics"]["started_at"], w["metrics"]["finished_at"]) for w in workers if w["metrics"]]
    check, total, distinct = integrity_and_uniqueness_path(db)
    write_evidence({
        "schema": EVIDENCE_SCHEMA, "label": label or current_label(),
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": environment(), "barrier": "file-based start barrier",
        "workers": workers,
        "release_to_finish_s": round(time.time() - released_at, 6),
        "max_concurrency": max_concurrency(windows) if windows else None,
        "database": {"file": db.name, "rows": total, "distinct_keys": distinct, "integrity_check": check},
    })
    return results


def integrity_and_uniqueness_path(db: Path):
    connection = sqlite3.connect(db)
    try:
        check = connection.execute("PRAGMA integrity_check").fetchone()[0]
        total, distinct = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol || '|' || timeframe || '|' || open_time_ms) FROM candles").fetchone()
    finally:
        connection.close()
    return check, total, distinct


def rows(repository: CandleRepository):
    from sqlalchemy import text
    with repository.engine.connect() as connection:
        return connection.execute(text("SELECT open_time_ms, volume FROM candles ORDER BY open_time_ms")).all()


def integrity_and_uniqueness(repository: CandleRepository):
    from sqlalchemy import text
    with repository.engine.connect() as connection:
        check = connection.execute(text("PRAGMA integrity_check")).scalar()
        total, distinct = connection.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT symbol || '|' || timeframe || '|' || open_time_ms) FROM candles")).one()
    return check, total, distinct
