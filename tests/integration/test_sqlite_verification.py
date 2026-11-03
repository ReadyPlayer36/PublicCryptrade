"""Direct verification of stored candles: counts, continuity, OHLC, volume, duplicates; read-only, never repairs."""
import hashlib
import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from tests.fixtures.service_env import I, S0, Env, ok_responses
from trading_app.data import verification
from trading_app.data.repository import CandleRepository, create_engine_from_url
from trading_app.data.verification import verify_database

COLS = ("symbol", "timeframe", "open_time_ms", "close_time_ms", "open_price", "high_price", "low_price", "close_price",
        "volume", "quote_volume", "trade_count", "created_at_ms")
PLAIN_TABLE = (  # same columns as the real table but WITHOUT the unique constraint, to model a damaged database
    "CREATE TABLE candles (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol VARCHAR(32) NOT NULL, timeframe VARCHAR(16) NOT NULL, "
    "open_time_ms BIGINT NOT NULL, close_time_ms BIGINT NOT NULL, open_price VARCHAR(80) NOT NULL, high_price VARCHAR(80) NOT NULL, "
    "low_price VARCHAR(80) NOT NULL, close_price VARCHAR(80) NOT NULL, volume VARCHAR(80) NOT NULL, quote_volume VARCHAR(80) NOT NULL, "
    "trade_count INTEGER NOT NULL, created_at_ms BIGINT NOT NULL)")


def raw_insert(db, open_ms, timeframe="5m", **overrides):
    row = dict(symbol="BTCUSDT", timeframe=timeframe, open_time_ms=open_ms, close_time_ms=open_ms + I - 1, open_price="100",
               high_price="101", low_price="99", close_price="100.5", volume="1", quote_volume="1", trade_count=1,
               created_at_ms=S0 + 100 * I)
    row.update(overrides)
    connection = sqlite3.connect(db)
    connection.execute(f"INSERT INTO candles ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    connection.commit()
    connection.close()


def make_db(tmp_path, *, plain=False):
    db = tmp_path / "v.db"
    if plain:
        connection = sqlite3.connect(db)
        connection.execute(PLAIN_TABLE)
        connection.commit()
        connection.close()
    else:
        CandleRepository(create_engine_from_url(f"sqlite:///{db}")).create_tables()
    return db, create_engine_from_url(f"sqlite:///{db}")


def codes(report):
    return sorted((i.code, i.open_time_ms) for i in report.issues)


def file_digest(db):
    return hashlib.sha256(db.read_bytes()).hexdigest()


@pytest.mark.requirement("M1-15")
def test_direct_sqlite_verification_procedure(tmp_path):
    # End to end: ingest through the real service, then verify the stored file directly.
    db = tmp_path / "proc.db"
    env = Env(ok_responses(12), db_url=f"sqlite:///{db}")
    assert env.run(12) == 12
    report = verify_database(create_engine_from_url(f"sqlite:///{db}"))
    assert report.ok and report.issues == ()
    assert report.counts == {("BTCUSDT", "5m"): 12}
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT COUNT(*) FROM candles").fetchone() == (12,)
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    connection.close()


@pytest.mark.requirement("VERIFY-03")
def test_stored_data_verification_queries(tmp_path):
    db, engine = make_db(tmp_path)
    for k in range(3):
        raw_insert(db, S0 + k * I)
    raw_insert(db, S0, timeframe="15m", close_time_ms=S0 + 3 * I - 1)
    report = verify_database(engine)
    assert report.ok
    assert report.counts == {("BTCUSDT", "15m"): 1, ("BTCUSDT", "5m"): 3}
    assert report.issue_counts() == {}


@pytest.mark.requirement("VERIFY-03")
def test_timestamp_continuity_query(tmp_path):
    db, engine = make_db(tmp_path)
    raw_insert(db, S0)
    raw_insert(db, S0 + I)
    raw_insert(db, S0 + 3 * I)                       # one candle missing before this one
    raw_insert(db, S0 + 9 * I, timeframe="15m", close_time_ms=S0 + 9 * I + 3 * I - 1)   # other series, aligned: must not be compared with 5m rows
    report = verify_database(engine)
    assert [(i.code, i.timeframe, i.open_time_ms) for i in report.issues if i.code == "SERIES_GAP"] == [("SERIES_GAP", "5m", S0 + 3 * I)]
    assert [i for i in report.issues if i.timeframe == "15m"] == []         # series are never mixed
    raw_insert(db, S0 + 4 * I + 7)                    # off-grid open time
    assert ("MISALIGNED_OPEN", S0 + 4 * I + 7) in codes(verify_database(engine))


@pytest.mark.requirement("VERIFY-03")
def test_ohlc_correctness_query(tmp_path):
    db, engine = make_db(tmp_path)
    raw_insert(db, S0)                                             # healthy
    raw_insert(db, S0 + I, high_price="100.4")                     # high below close
    raw_insert(db, S0 + 2 * I, low_price="100.6")                  # low above close
    raw_insert(db, S0 + 3 * I, high_price="98", low_price="99")    # low above high
    raw_insert(db, S0 + 4 * I, open_price="0")                     # non-positive price
    raw_insert(db, S0 + 5 * I, close_price="not-a-number")         # undecodable decimal text
    raw_insert(db, S0 + 6 * I, close_price="NaN")                  # non-finite
    found = codes(verify_database(engine))
    assert (("INVALID_OHLC", S0 + I)) in found and ("INVALID_OHLC", S0 + 2 * I) in found and ("INVALID_OHLC", S0 + 3 * I) in found
    assert ("NONPOSITIVE_PRICE", S0 + 4 * I) in found
    assert ("BAD_DECIMAL_TEXT", S0 + 5 * I) in found and ("BAD_DECIMAL_TEXT", S0 + 6 * I) in found
    assert not [c for c in found if c[1] == S0]                    # the healthy row is never flagged


@pytest.mark.requirement("VERIFY-03")
def test_invalid_volume_query(tmp_path):
    db, engine = make_db(tmp_path)
    raw_insert(db, S0, volume="0", quote_volume="0")               # zero volume is valid
    raw_insert(db, S0 + I, volume="-0.00000001")
    raw_insert(db, S0 + 2 * I, quote_volume="-5")
    raw_insert(db, S0 + 3 * I, volume="Infinity")
    found = codes(verify_database(engine))
    assert found == [("BAD_DECIMAL_TEXT", S0 + 3 * I), ("NEGATIVE_VOLUME", S0 + I), ("NEGATIVE_VOLUME", S0 + 2 * I)]


@pytest.mark.requirement("VERIFY-03")
def test_suspicious_data_query(tmp_path):
    # Duplicates can only exist in a damaged database (the real table has a unique constraint); verification reports
    # them, never repairs, and leaves the database file byte-for-byte untouched.
    db, engine = make_db(tmp_path, plain=True)
    raw_insert(db, S0)
    raw_insert(db, S0)
    raw_insert(db, S0 + I, high_price="90")
    verify_database(engine)                           # first open switches the file to WAL mode (not a data write)
    engine.dispose()
    before = file_digest(db)
    report = verify_database(engine)
    assert ("DUPLICATE_CANDLE", S0) in codes(report)
    assert ("INVALID_OHLC", S0 + I) in codes(report)
    assert report.counts == {("BTCUSDT", "5m"): 3}
    assert not report.ok
    engine.dispose()
    assert file_digest(db) == before
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT COUNT(*) FROM candles").fetchone() == (3,)      # nothing removed or fixed
    connection.close()


@pytest.mark.requirement("VERIFY-03")
def test_verification_is_read_only_and_restores_write_mode(tmp_path):
    db, engine = make_db(tmp_path)
    raw_insert(db, S0)
    statements = []
    from sqlalchemy import event
    event.listen(engine, "connect", lambda c, r: c.set_trace_callback(lambda s: statements.append(s.strip().upper())))
    verify_database(engine)
    writes = [s for s in statements if s.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE"))]
    assert writes == []
    assert statements.index("PRAGMA QUERY_ONLY=ON") < min(i for i, s in enumerate(statements) if s.startswith("SELECT"))
    assert statements[-1] == "PRAGMA QUERY_ONLY=OFF"


@pytest.mark.requirement("VERIFY-03")
def test_unknown_timeframe_rows_are_counted_without_crashing(tmp_path):
    db, engine = make_db(tmp_path)
    raw_insert(db, S0, timeframe="2m")
    report = verify_database(engine)
    assert report.counts == {("BTCUSDT", "2m"): 1} and report.ok
