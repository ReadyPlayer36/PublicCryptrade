"""Repository acceptance tests (SQLite, no network)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.fixtures.candles import candle
from trading_app.data.repository import CandleRepository, create_engine_from_url


def make_repo(url="sqlite:///:memory:"):
    repository = CandleRepository(create_engine_from_url(url))
    repository.create_tables()
    return repository


@pytest.mark.requirement("M1-08")
def test_application_duplicate_prevention():
    repository = make_repo()
    first = candle()
    later = candle(open_time=first.open_time + timedelta(minutes=5))
    assert repository.insert_candles([first, later]) == 2
    assert repository.insert_candles([first, later]) == 0                  # explicit, no DB error needed
    assert repository.insert_candles([first, candle(open_time=first.open_time + timedelta(minutes=10))]) == 1
    assert repository.insert_candles([candle(), candle()]) == 0           # identical duplicates inside one batch
    fresh = make_repo()
    assert fresh.insert_candles([candle(), candle()]) == 1                # ...are stored once
    assert fresh.count() == 1
    assert fresh.insert_candles([]) == 0


@pytest.mark.requirement("M1-07")
def test_composite_uniqueness():
    repository = make_repo()
    repository.insert_candles([candle()])
    unique = inspect(repository.engine).get_unique_constraints("candles")
    assert [c["column_names"] for c in unique] == [["symbol", "timeframe", "open_time_ms"]]
    with repository.engine.connect() as connection:                        # bypass the application layer entirely
        stored = connection.execute(text("SELECT * FROM candles")).mappings().one()
        columns = ", ".join(k for k in stored if k != "id")
        placeholders = ", ".join(f":{k}" for k in stored if k != "id")
        with pytest.raises(IntegrityError):
            connection.execute(text(f"INSERT INTO candles ({columns}) VALUES ({placeholders})"), {k: v for k, v in stored.items() if k != "id"})
    # same open time but another series is a different key
    other = candle()
    other.timeframe = "15m"
    assert repository.insert_candles([other]) == 1


@pytest.mark.requirement("M1-13")
def test_decimal_values_preserved_exactly():
    for value in ["0.1234567890123456789", "12345678901234567890.123456789012345678", "100.10", "0.00000001", "1E-8", "1E+3", "0"]:
        repository = make_repo()
        repository.insert_candles([candle(open=value, high="9" * 25 + ".5", low="0.00000001", close=value, volume=value, quote_volume=value)])
        stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")[0]
        assert stored.open == stored.close == stored.volume == stored.quote_volume == Decimal(value), value
        assert stored.high == Decimal("9" * 25 + ".5")
        with repository.engine.connect() as connection:
            raw = connection.execute(text("SELECT open_price, high_price, low_price FROM candles")).one()
        assert all(isinstance(v, str) and "E" not in v.upper() for v in raw), value   # exact text, never scientific or float
        assert raw[0] == format(Decimal(value), "f") and raw[2] == "0.00000001"


@pytest.mark.requirement("M1-13")
def test_floats_and_non_finite_decimals_are_rejected_before_storage():
    repository = make_repo()
    for bad in (100.1, float("nan"), Decimal("NaN"), Decimal("Infinity"), True, "abc", None):
        row = candle()
        row.open = bad
        with pytest.raises(ValueError):
            repository.insert_candles([row])
    assert repository.count() == 0


@pytest.mark.requirement("M1-07")
def test_sqlalchemy_persistence(tmp_path):
    url = f"sqlite:///{tmp_path / 'sub' / 'candles.db'}"
    first = make_repo(url)
    rows = [candle(open_time=candle().open_time + timedelta(minutes=5 * i)) for i in (2, 0, 1)]   # inserted out of order
    assert first.insert_candles(rows) == 3
    first.engine.dispose()
    reopened = CandleRepository(create_engine_from_url(url))                 # persisted across engines
    times = [c.open_time for c in reopened.get_candles(symbol="BTCUSDT", timeframe="5m")]
    assert times == sorted(times) and len(times) == 3
    assert reopened.get_candles(symbol="ETHUSDT", timeframe="5m") == []
    assert reopened.get_candles(symbol="BTCUSDT", timeframe="1h") == []
    assert reopened.count(symbol="BTCUSDT") == 3 and reopened.count(symbol="ETHUSDT") == 0 and reopened.count(timeframe="5m") == 3


@pytest.mark.requirement("M1-07")
@pytest.mark.parametrize("field,bad", [("symbol", ""), ("timeframe", ""), ("trade_count", -1), ("trade_count", 1.5), ("trade_count", True),
                                       ("open_time", None), ("close_time", "2026-01-05")])
def test_invalid_candle_fields_are_rejected_before_any_write(field, bad):
    repository = make_repo()
    row = candle()
    setattr(row, field, bad)
    with pytest.raises(ValueError):
        repository.insert_candles([candle(open_time=candle().open_time + timedelta(minutes=5)), row])
    assert repository.count() == 0


@pytest.mark.requirement("M1-07")
def test_naive_datetimes_are_rejected():
    from datetime import datetime
    repository = make_repo()
    with pytest.raises(ValueError, match="timezone"):
        repository.insert_candles([candle(open_time=datetime(2026, 1, 5))])


@pytest.mark.requirement("M1-07")
def test_timestamps_round_trip_to_the_millisecond():
    repository = make_repo()
    row = candle()
    repository.insert_candles([row])
    stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")[0]
    assert stored.open_time == row.open_time and stored.close_time == row.close_time
    assert stored.close_time - stored.open_time == timedelta(minutes=5) - timedelta(milliseconds=1)


@pytest.mark.requirement("M1-08")
def test_conflicting_duplicates_inside_one_batch_are_rejected_not_first_wins():
    from trading_app.data.repository import CandleConflictError
    repository = make_repo()
    with pytest.raises(CandleConflictError, match="inside the batch"):
        repository.insert_candles([candle(close="100.50"), candle(close="100.51")])
    assert repository.count() == 0


@pytest.mark.requirement("TX-01")
def test_insert_runs_in_one_begin_immediate_transaction_then_commits():
    from sqlalchemy import event
    repository = make_repo()
    statements = []
    event.listen(repository.engine, "before_cursor_execute", lambda c, cur, stmt, *a: statements.append(stmt.split()[0:2]))
    repository.insert_candles([candle()])
    assert statements[0] == ["BEGIN", "IMMEDIATE"]
    assert statements.count(["BEGIN", "IMMEDIATE"]) == 1
