"""Legacy database scan: heuristic, read-only, never repairs; remediation is manual (list, delete explicitly, re-fetch, re-verify)."""
import hashlib
import sqlite3

import pytest
from sqlalchemy import event, text

from tests.fixtures.klines import make_rows
from tests.fixtures.service_env import I, S0, Env, ok_responses
from trading_app.data.repository import CandleRepository, LegacyScanReport, create_engine_from_url

LATE = S0 + 100 * I            # a created_at long after every candle used below has closed


def make_repo(tmp_path, name="legacy.db"):
    db = tmp_path / name
    repository = CandleRepository(create_engine_from_url(f"sqlite:///{db}"))
    repository.create_tables()
    return db, repository


def legacy_insert(db, open_ms, created_at=LATE, **overrides):
    """Insert a row with raw SQL, exactly as an older version of the application might have left it."""
    row = dict(symbol="BTCUSDT", timeframe="5m", open_time_ms=open_ms, close_time_ms=open_ms + I - 1, open_price="100", high_price="101",
               low_price="99", close_price="100.5", volume="1", quote_volume="1", trade_count=1, created_at_ms=created_at)
    row.update(overrides)
    connection = sqlite3.connect(db)
    connection.execute(f"INSERT INTO candles ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    connection.commit()
    connection.close()


def snapshot(repository):
    with repository.engine.connect() as connection:
        return [tuple(r) for r in connection.execute(text("SELECT * FROM candles ORDER BY id")).all()]


def codes_by_time(report):
    found = {}
    for issue in report.issues:
        found.setdefault((issue.timeframe, issue.open_time_ms), set()).add(issue.code)
    return found


@pytest.mark.requirement("LEGACY-01")
def test_legacy_scan_flags_without_repair(tmp_path):
    db, repository = make_repo(tmp_path)
    legacy_insert(db, S0)                                                      # healthy
    legacy_insert(db, S0 + 1 * I, created_at=S0 + 1 * I + 5)                   # stored before it closed: possibly a forming candle
    legacy_insert(db, S0 + 2 * I, high_price="90")                             # high below open/close and below low
    legacy_insert(db, S0 + 3 * I, open_price="1E-8")                           # scientific-notation text
    legacy_insert(db, S0 + 4 * I, volume="-1")                                 # negative volume
    legacy_insert(db, S0 + 5 * I, open_price="0", low_price="0")               # non-positive price
    legacy_insert(db, S0 + 6 * I, close_time_ms=S0 + 6 * I + 5)                # wrong duration
    legacy_insert(db, S0 + 9 * I)                                              # two candles missing before it
    legacy_insert(db, S0 + 10 * I, trade_count=-3)                             # negative trade count
    legacy_insert(db, S0 + 11 * I, timeframe="7m", close_time_ms=S0 + 11 * I + 419999)   # unsupported timeframe
    before, before_bytes = snapshot(repository), hashlib.sha256(db.read_bytes()).hexdigest()

    report = repository.scan_legacy_data(repair=False)

    assert isinstance(report, LegacyScanReport) and report.repaired is False
    assert report.scanned_rows == 10 and report.issues                          # findings are reported
    assert codes_by_time(report) == {
        ("5m", S0 + 1 * I): {"FORMING_CANDLE"},
        ("5m", S0 + 2 * I): {"INVALID_OHLC"},
        ("5m", S0 + 3 * I): {"BAD_DECIMAL_TEXT"},
        ("5m", S0 + 4 * I): {"NEGATIVE_VOLUME"},
        ("5m", S0 + 5 * I): {"NONPOSITIVE_PRICE"},
        ("5m", S0 + 6 * I): {"BAD_DURATION"},
        ("5m", S0 + 9 * I): {"SERIES_GAP"},
        ("5m", S0 + 10 * I): {"NEGATIVE_TRADE_COUNT"},
        ("7m", S0 + 11 * I): {"UNKNOWN_TIMEFRAME"},
    }                                                                           # the healthy row (S0) is not flagged at all
    from trading_app.data.repository import _LEGACY_DETAIL
    assert {i.detail for i in report.issues} <= set(_LEGACY_DETAIL.values())   # findings carry fixed text only
    assert not any(value in i.detail for i in report.issues for value in ("1E-8", "-3", "100.5", "7m"))   # never a stored value
    # --- the scan changed NOTHING
    assert snapshot(repository) == before and repository.count() == 10
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before_bytes
    assert report.flagged_keys() == sorted((s, t, o) for (t, o), _ in codes_by_time(report).items() for s in ["BTCUSDT"])
    assert report.counts() == {"BAD_DECIMAL_TEXT": 1, "BAD_DURATION": 1, "FORMING_CANDLE": 1, "INVALID_OHLC": 1, "NEGATIVE_TRADE_COUNT": 1,
                               "NEGATIVE_VOLUME": 1, "NONPOSITIVE_PRICE": 1, "SERIES_GAP": 1, "UNKNOWN_TIMEFRAME": 1}


@pytest.mark.requirement("LEGACY-01")
def test_scan_is_read_only_at_the_statement_level_and_leaves_the_engine_writable(tmp_path):
    db, repository = make_repo(tmp_path)
    legacy_insert(db, S0, created_at=S0)                                        # forming
    statements = []

    @event.listens_for(repository.engine, "connect")
    def trace(dbapi_connection, record):
        dbapi_connection.set_trace_callback(lambda s: statements.append(s.strip().upper()))

    repository.engine.dispose()                                                 # new connections now carry the trace
    repository.scan_legacy_data()
    verbs = [s.split()[0] for s in statements if s]
    assert "INSERT" not in verbs and "UPDATE" not in verbs and "DELETE" not in verbs and "DROP" not in verbs and "ALTER" not in verbs
    assert "PRAGMA QUERY_ONLY=ON" in statements and statements.index("PRAGMA QUERY_ONLY=ON") < next(i for i, s in enumerate(statements) if s.startswith("SELECT"))
    assert statements[-1] == "PRAGMA QUERY_ONLY=OFF" or "PRAGMA QUERY_ONLY=OFF" in statements
    legacy_insert(db, S0 + I)                                                   # an outside writer is not blocked either
    from tests.fixtures.candles import candle
    from datetime import timedelta
    assert repository.insert_candles([candle(open_time=candle().open_time + timedelta(minutes=500))]) == 1   # and the pooled connection is writable again


@pytest.mark.requirement("LEGACY-01")
def test_query_only_mode_really_blocks_writes_during_a_scan(tmp_path):
    db, repository = make_repo(tmp_path)
    legacy_insert(db, S0)
    with repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA query_only=ON")
        with pytest.raises(Exception, match="readonly|read-only|read only"):
            connection.execute(text("DELETE FROM candles"))
        connection.rollback()
        connection.exec_driver_sql("PRAGMA query_only=OFF")
    assert repository.count() == 1


@pytest.mark.requirement("LEGACY-01")
def test_repair_is_refused_and_defaults_to_no_repair(tmp_path):
    db, repository = make_repo(tmp_path)
    legacy_insert(db, S0, created_at=S0)
    before = snapshot(repository)
    for bad in (True, 1, "yes", None):
        with pytest.raises(ValueError, match="repair is not supported"):
            repository.scan_legacy_data(repair=bad)
    assert repository.scan_legacy_data().repaired is False and snapshot(repository) == before
    with pytest.raises(TypeError):
        repository.scan_legacy_data(True)                                       # keyword-only: no accidental positional "repair"


@pytest.mark.requirement("LEGACY-01")
def test_clean_and_empty_databases_report_no_findings(tmp_path):
    _, empty = make_repo(tmp_path, "empty.db")
    report = empty.scan_legacy_data()
    assert report.scanned_rows == 0 and report.issues == () and report.counts() == {} and report.flagged_keys() == []
    env = Env(ok_responses(5, rows=make_rows(S0, 5)), db_url=f"sqlite:///{tmp_path / 'clean.db'}")
    env.run(5)                                                                  # rows stored by the real service (created_at after close)
    clean = env.repo.scan_legacy_data()
    assert clean.scanned_rows == 5 and clean.issues == ()


@pytest.mark.requirement("LEGACY-01")
def test_forming_candle_boundary_and_series_independence(tmp_path):
    db, repository = make_repo(tmp_path)
    legacy_insert(db, S0, created_at=S0 + I - 1)              # created exactly at its close time  -> flagged
    legacy_insert(db, S0 + I, created_at=S0 + 2 * I)          # created one ms after its close time -> not flagged
    legacy_insert(db, S0, symbol="ETHUSDT")                   # same times, other series: no gap bookkeeping leaks across series
    legacy_insert(db, S0 + 5 * I, symbol="ETHUSDT")           # gap of 4 in the ETHUSDT series only
    report = repository.scan_legacy_data()
    found = {(i.symbol, i.open_time_ms): i.code for i in report.issues}
    assert found == {("BTCUSDT", S0): "FORMING_CANDLE", ("ETHUSDT", S0 + 5 * I): "SERIES_GAP"}


@pytest.mark.requirement("LEGACY-01")
def test_scan_never_touches_the_audit_table(tmp_path):
    env = Env(ok_responses(3), db_url=f"sqlite:///{tmp_path / 'a.db'}")
    env.run(3)
    legacy_insert(tmp_path / "a.db", S0 + 20 * I, created_at=S0)
    audits = env.repo.get_fetches()
    env.repo.scan_legacy_data()
    assert env.repo.get_fetches() == audits


@pytest.mark.requirement("LEGACY-01")
def test_manual_remediation_list_delete_refetch_reverify(tmp_path):
    db = tmp_path / "remediate.db"
    env = Env(ok_responses(3, rows=make_rows(S0, 3)), db_url=f"sqlite:///{db}")
    env.run(3)
    legacy_insert(db, S0 + 3 * I, created_at=S0 + 3 * I + 10, high_price="100.7", close_price="100.2")   # a stale forming copy of candle 3
    report = env.repo.scan_legacy_data()
    assert report.flagged_keys() == [("BTCUSDT", "5m", S0 + 3 * I)]            # 1. LIST the flagged rows
    with pytest.raises(ValueError, match="confirm=True"):
        env.repo.delete_candles(report.flagged_keys())                         # deletion is never implicit
    assert env.repo.count() == 4
    assert env.repo.delete_candles(report.flagged_keys(), confirm=True) == 1   # 2. DELETE explicitly
    assert env.repo.count() == 3
    env.fake.responses.extend(ok_responses(4, rows=make_rows(S0, 4)))
    assert env.run(4) == 1                                                     # 3. RE-FETCH: only the removed candle is stored again
    assert env.repo.scan_legacy_data().issues == ()                            # 4. RE-VERIFY: clean


@pytest.mark.requirement("LEGACY-01")
def test_delete_candles_safeguards_and_atomicity(tmp_path):
    db, repository = make_repo(tmp_path)
    for n in range(3):
        legacy_insert(db, S0 + n * I)
    keys = [("BTCUSDT", "5m", S0 + n * I) for n in range(3)]
    for bad in ([], [("BTCUSDT", "5m")], [("", "5m", S0)], [("BTCUSDT", "5m", True)], [("BTCUSDT", "5m", "1")], ["BTCUSDT"]):
        with pytest.raises(ValueError):
            repository.delete_candles(bad, confirm=True)
    for confirm in (False, None, 1, "yes"):
        with pytest.raises(ValueError, match="confirm=True"):
            repository.delete_candles(keys, confirm=confirm)
    assert repository.count() == 3
    assert repository.delete_candles([("BTCUSDT", "5m", S0 + 99 * I)], confirm=True) == 0       # unknown key: nothing deleted
    state = {"armed": True}

    def explode(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("DELETE") and parameters and S0 + 1 * I in parameters:
            raise RuntimeError("injected failure mid-delete")
    event.listen(repository.engine, "after_cursor_execute", explode)
    try:
        with pytest.raises(RuntimeError, match="mid-delete"):
            repository.delete_candles(keys, confirm=True)
    finally:
        event.remove(repository.engine, "after_cursor_execute", explode)
    assert repository.count() == 3                                             # the first delete was rolled back with the failure
    assert repository.delete_candles(keys, confirm=True) == 3 and repository.count() == 0


# ---- malformed-type robustness (reviewer condition): a legacy table with NO column types keeps whatever was written ----
POISON = "SECRET-hunter2-TOKEN"


def loose_db(tmp_path, name="loose.db"):
    db = tmp_path / name
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE candles (id INTEGER PRIMARY KEY, symbol, timeframe, open_time_ms, close_time_ms, open_price, high_price,"
                       " low_price, close_price, volume, quote_volume, trade_count, created_at_ms)")
    connection.commit()
    connection.close()
    return db, CandleRepository(create_engine_from_url(f"sqlite:///{db}"))


def loose_insert(db, n, **overrides):
    open_ms = S0 + n * I
    row = dict(id=n + 1, symbol="BTCUSDT", timeframe="5m", open_time_ms=open_ms, close_time_ms=open_ms + I - 1, open_price="100", high_price="101",
               low_price="99", close_price="100.5", volume="1", quote_volume="1", trade_count=1, created_at_ms=LATE)
    row.update(overrides)
    connection = sqlite3.connect(db)
    connection.execute(f"INSERT INTO candles ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    connection.commit()
    connection.close()


def everything_reported(report):
    parts = [repr(report), str(report.counts()), str(report.flagged_keys())]
    for issue in report.issues:
        parts += [repr(issue), issue.code, issue.symbol, issue.timeframe, issue.detail]
    return " | ".join(parts)


@pytest.mark.requirement("LEGACY-01")
def test_malformed_stored_types_get_one_fixed_finding_and_never_leak_values(tmp_path):
    db, repository = loose_db(tmp_path)
    loose_insert(db, 0)                                                         # id 1  healthy
    loose_insert(db, 1, trade_count=POISON)                                     # id 2  text where an integer belongs
    loose_insert(db, 2, created_at_ms=POISON)                                   # id 3  text timestamp
    loose_insert(db, 3, open_time_ms=1.5, close_time_ms=b"SECRET-bytes")        # id 4  float open time, bytes close time
    loose_insert(db, 4, trade_count=None)                                       # id 5  NULL integer
    loose_insert(db, 5, symbol="BTC " + POISON)                                 # id 6  hostile symbol
    loose_insert(db, 6, timeframe=POISON)                                       # id 7  hostile timeframe
    loose_insert(db, 7, volume=POISON)                                          # id 8  bad decimal text: NOT a malformed-field case
    loose_insert(db, 8, trade_count=POISON, created_at_ms=POISON, close_time_ms=POISON, symbol=None)   # id 9  everything wrong at once
    loose_insert(db, 9, open_price=b"SECRET-blob", high_price=None)             # id 10 non-text decimals
    before = [tuple(r) for r in sqlite3.connect(db).execute("SELECT * FROM candles ORDER BY id")]

    report = repository.scan_legacy_data()                                      # must complete without raising

    assert report.scanned_rows == 10
    per_row = {}
    for issue in report.issues:
        per_row.setdefault(issue.row_id, []).append(issue.code)
    malformed_rows = {rid for rid, codes in per_row.items() if "MALFORMED_FIELD" in codes}
    assert malformed_rows == {2, 3, 4, 5, 6, 7, 9}
    assert all(codes.count("MALFORMED_FIELD") <= 1 for codes in per_row.values())     # exactly one fixed finding per row
    # ids 8 and 10 have unparsable decimals (and, because the malformed rows between them leave real holes in the valid series, a gap)
    assert set(per_row[8]) == {"BAD_DECIMAL_TEXT", "SERIES_GAP"} and set(per_row[10]) == {"BAD_DECIMAL_TEXT", "SERIES_GAP"}
    assert 1 not in per_row                                                     # the healthy row is never flagged
    assert report.counts()["MALFORMED_FIELD"] == 7
    assert not any(token in everything_reported(report) for token in (POISON, "hunter2", "SECRET", "bytes", "blob"))
    assert {i.detail for i in report.issues} <= set(__import__("trading_app.data.repository", fromlist=["_LEGACY_DETAIL"])._LEGACY_DETAIL.values())
    # rows with untrustworthy identifiers are shown by placeholder and kept out of the delete list, but stay findable by row_id
    placeholders = [i for i in report.issues if i.symbol == "<invalid>" or i.timeframe == "<invalid>"]
    assert {i.row_id for i in placeholders} == {6, 7, 9}
    assert all(k[0] != "<invalid>" and k[1] != "<invalid>" and k[2] >= 0 for k in report.flagged_keys())
    assert [tuple(r) for r in sqlite3.connect(db).execute("SELECT * FROM candles ORDER BY id")] == before     # and still nothing was written


@pytest.mark.requirement("LEGACY-01")
def test_a_malformed_field_never_hides_the_other_findings_on_the_same_row(tmp_path):
    db, repository = loose_db(tmp_path)
    loose_insert(db, 0, created_at_ms=POISON, volume="-5", high_price="90")                    # id 1
    loose_insert(db, 1, trade_count=POISON, created_at_ms=S0, volume="-5", high_price="90")    # id 2
    loose_insert(db, 2, trade_count=POISON, close_time_ms=S0 + 2 * I + 7, volume="-5")         # id 3
    per_row = {}
    for issue in repository.scan_legacy_data().issues:
        per_row.setdefault(issue.row_id, set()).add(issue.code)
    assert per_row == {
        1: {"MALFORMED_FIELD", "NEGATIVE_VOLUME", "INVALID_OHLC"},
        2: {"MALFORMED_FIELD", "FORMING_CANDLE", "NEGATIVE_VOLUME", "INVALID_OHLC"},
        3: {"MALFORMED_FIELD", "BAD_DURATION", "NEGATIVE_VOLUME"},
    }


@pytest.mark.requirement("LEGACY-01")
def test_a_hostile_row_object_cannot_crash_the_scan_or_leak_through_an_exception():
    from trading_app.data.repository import _LEGACY_DETAIL, _scan_row

    class Hostile(dict):
        def __getitem__(self, key):
            if key == "volume":
                raise RuntimeError(f"{POISON} exploded while reading")
            return super().__getitem__(key)

    row = Hostile(id=1, symbol="BTCUSDT", timeframe="5m", open_time_ms=S0, close_time_ms=S0 + I - 1, open_price="100", high_price="101",
                  low_price="99", close_price="100.5", volume="1", quote_volume="1", trade_count=1, created_at_ms=LATE)
    (issue,) = _scan_row(row, {})
    assert issue.code == "MALFORMED_FIELD" and issue.detail == _LEGACY_DETAIL["MALFORMED_FIELD"]
    assert POISON not in repr(issue) and issue.row_id == -1 and issue.symbol == "<invalid>"
    # a row that is ALREADY malformed and then raises must still produce exactly one MALFORMED_FIELD finding
    already = Hostile(row, trade_count=POISON)
    findings = _scan_row(already, {})
    assert [i.code for i in findings] == ["MALFORMED_FIELD"] and POISON not in repr(findings)


@pytest.mark.requirement("LEGACY-01")
def test_well_formed_rows_are_unaffected_by_the_type_checks(tmp_path):
    db, repository = loose_db(tmp_path)
    for n in range(4):
        loose_insert(db, n)
    assert repository.scan_legacy_data().issues == ()
    loose_insert(db, 4, trade_count=-2)
    assert [i.code for i in repository.scan_legacy_data().issues] == ["NEGATIVE_TRADE_COUNT"]      # integer checks still work


@pytest.mark.requirement("LEGACY-01")
def test_delete_candles_signature_defaults_to_refusal():
    import inspect
    parameter = inspect.signature(CandleRepository.delete_candles).parameters["confirm"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is False       # explicit opt-in is required
