"""SQLite conflict tests verify idempotence, rollback, and no overwrite."""
from datetime import timedelta
import pytest
from tests.fixtures.candles import candle
from trading_app.data.repository import CandleRepository, CandleConflictError, create_engine_from_url

@pytest.mark.requirement("CONFLICT-01")
def test_conflict_compares_complete_field_set():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    original = candle()
    assert repository.insert_candles([original]) == 1
    conflicting = candle(close="100.51")
    with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
        repository.insert_candles([conflicting])
    assert repository.get_candles(symbol="BTCUSDT", timeframe="5m")[0].close == original.close

@pytest.mark.requirement("CONFLICT-01")
def test_conflict_never_overwrites():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    original = candle(); repository.insert_candles([original])
    with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
        repository.insert_candles([candle(volume="99")])
    stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")
    assert len(stored) == 1 and stored[0].volume == original.volume

@pytest.mark.requirement("CONFLICT-01")
def test_conflict_raises_and_rolls_back():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    original = candle(); repository.insert_candles([original])
    new_row = candle(open_time=original.open_time + timedelta(minutes=5))
    conflict = candle(close="999")
    with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
        repository.insert_candles([new_row, conflict])
    stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")
    assert len(stored) == 1
    assert stored[0].open_time == original.open_time

@pytest.mark.requirement("CONFLICT-01")
def test_conflicting_row_raises():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    repository.insert_candles([candle()])
    with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
        repository.insert_candles([candle(trade_count=999)])

@pytest.mark.requirement("CONFLICT-01")
def test_identical_rows_idempotent():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    row = candle()
    assert repository.insert_candles([row]) == 1
    assert repository.insert_candles([row]) == 0
    assert repository.count(symbol="BTCUSDT", timeframe="5m") == 1

@pytest.mark.requirement("CONFLICT-01")
def test_identical_rows_idempotent_and_conflicts_raise():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    repository.insert_candles([candle(open="100.1")])
    assert repository.insert_candles([candle(open="100.10", created_at_ms=999999)]) == 0
    with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
        repository.insert_candles([candle(open="100.11")])


@pytest.mark.requirement("CONFLICT-01")
def test_every_failure_mode_leaves_the_persisted_state_unchanged():
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:")); repository.create_tables()
    original = candle()
    repository.insert_candles([original])
    snapshot = repository.get_candles(symbol="BTCUSDT", timeframe="5m")
    t = original.open_time
    valid_new = candle(open_time=t + timedelta(minutes=5))
    more_new = candle(open_time=t + timedelta(minutes=10))
    failing_batches = [
        [valid_new, more_new, candle(close="1.00")],                                          # existing-row conflict last
        [candle(open_time=t + timedelta(minutes=15)), candle(open_time=t + timedelta(minutes=20), volume="1"),
         candle(open_time=t + timedelta(minutes=20), volume="2")],                            # in-batch conflict after valid entries
        [valid_new, candle(open_time=t + timedelta(minutes=25), trade_count=-1)],             # invalid field after a valid entry
    ]
    for batch in failing_batches:
        with pytest.raises((CandleConflictError, ValueError)):
            repository.insert_candles(batch)
        assert repository.get_candles(symbol="BTCUSDT", timeframe="5m") == snapshot
        assert repository.count() == 1
