"""Runs several real worker processes against one SQLite file, released together by a start barrier."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from trading_app.data.repository import CandleRepository, create_engine_from_url

WORKER = Path(__file__).with_name("concurrency_worker.py")


def make_database(tmp_path: Path) -> tuple[Path, CandleRepository]:
    db = tmp_path / "shared.db"
    repository = CandleRepository(create_engine_from_url(f"sqlite:///{db}"))
    repository.create_tables()
    return db, repository


def run_workers(tmp_path: Path, db: Path, specs: list[tuple[int, int, str]], timeout: float = 90) -> list[dict]:
    """specs = [(start_index, count, volume), ...]; returns one result dict per worker, in order."""
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
    go.write_text("go")                                  # release every worker at (nearly) the same instant
    results = []
    for p, out in zip(procs, outs):
        stdout, stderr = p.communicate(timeout=timeout)
        assert p.returncode == 0, stderr
        results.append(json.loads(out.read_text()))
    return results


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
