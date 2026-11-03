"""Separate-process SQLite concurrency (TX-01): real subprocesses, a shared file database, a start barrier."""
import pytest

from tests.fixtures.process_runner import integrity_and_uniqueness, make_database, rows, run_workers
from trading_app.data.repository import CandleConflictError


@pytest.mark.requirement("TX-01")
def test_two_processes_overlap_without_duplicates(tmp_path):
    db, repository = make_database(tmp_path)
    a, b = run_workers(tmp_path, db, [(0, 600, "1"), (300, 600, "1")])           # candles 300..599 are written by both
    assert a["ok"] and b["ok"]
    assert a["inserted"] + b["inserted"] == 900                                    # every candle was inserted exactly once
    check, total, distinct = integrity_and_uniqueness(repository)
    assert (check, total, distinct) == ("ok", 900, 900)
    assert [r[0] for r in rows(repository)] == sorted({r[0] for r in rows(repository)})


@pytest.mark.requirement("TX-01")
def test_no_duplicate_rows_after_overlap(tmp_path):
    db, repository = make_database(tmp_path)
    results = run_workers(tmp_path, db, [(0, 400, "1")] * 4)                       # four processes write the SAME 400 candles
    assert all(r["ok"] for r in results)
    assert sum(r["inserted"] for r in results) == 400                              # exactly one process inserted each candle
    assert sorted(r["inserted"] for r in results)[-1] >= 1
    check, total, distinct = integrity_and_uniqueness(repository)
    assert (check, total, distinct) == ("ok", 400, 400)
    assert {v for _, v in rows(repository)} == {"1"}


@pytest.mark.requirement("TX-01")
def test_conflict_rolls_back_entire_transaction(tmp_path):
    db, repository = make_database(tmp_path)
    (seed,) = run_workers(_sub(tmp_path, "seed"), db, [(0, 50, "1")])
    assert seed == {"ok": True, "inserted": 50}
    # B writes candles 0..199 but candle volume differs ("2" instead of "1") from the stored rows 0..49 -> conflict.
    # C writes the unrelated candles 300..399 at the same time and must be unaffected.
    b, c = run_workers(_sub(tmp_path, "race"), db, [(0, 200, "2"), (300, 100, "1")])
    assert b == {"ok": False, "error": "CandleConflictError"}
    assert c == {"ok": True, "inserted": 100}
    stored = rows(repository)
    assert len(stored) == 150                                                      # seed 50 + C's 100; NONE of B's new candles 50..199
    assert sorted((r[0] - 1767571200000) // 300000 for r in stored) == list(range(0, 50)) + list(range(300, 400))   # exactly these candles
    assert {v for _, v in stored} == {"1"}
    # the write lock is free again: a correct writer can now add the previously rejected range
    (d,) = run_workers(_sub(tmp_path, "after"), db, [(0, 200, "1")])
    assert d == {"ok": True, "inserted": 150}                                      # candles 50..199 (0..49 were already stored)
    assert integrity_and_uniqueness(repository) == ("ok", 300, 300)                # 0..199 plus 300..399 = 300 distinct candles


@pytest.mark.requirement("TX-01")
def test_racing_conflicting_writers_leave_exactly_one_complete_winner(tmp_path):
    db, repository = make_database(tmp_path)
    a, b = run_workers(tmp_path, db, [(0, 300, "1"), (0, 300, "2")])              # same candles, different values: only one may win
    outcomes = sorted([a, b], key=lambda r: r["ok"])
    assert outcomes[0] == {"ok": False, "error": "CandleConflictError"} and outcomes[1] == {"ok": True, "inserted": 300}
    stored = rows(repository)
    assert len(stored) == 300 and len({v for _, v in stored}) == 1                 # all-or-nothing: one winner's values, never a mixture
    assert integrity_and_uniqueness(repository) == ("ok", 300, 300)


def _sub(tmp_path, name):
    path = tmp_path / name
    path.mkdir()
    return path
