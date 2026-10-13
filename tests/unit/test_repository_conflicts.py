"""Conflict behavior is compared field-by-field using exact Decimal values."""
from decimal import Decimal
import pytest
from tests.fixtures.candles import candle
from trading_app.data.repository import CandleRepository, CandleConflictError, create_engine_from_url

@pytest.mark.requirement("CONFLICT-03")
def test_conflict_compares_all_fields_and_never_overwrites():
    engine = create_engine_from_url("sqlite:///:memory:")
    repository = CandleRepository(engine); repository.create_tables()
    original = candle()
    assert repository.insert_candles([original]) == 1
    variants = [
        candle(close_time=original.close_time.replace(second=1)),
        candle(open="100.11"), candle(high="101.01"), candle(low="99.49"),
        candle(close="100.51"), candle(volume="12.34500001"),
        candle(quote_volume="1240.00000001"), candle(trade_count=101),
    ]
    for variant in variants:
        with pytest.raises(CandleConflictError, match="conflict|different|mismatch"):
            repository.insert_candles([variant])
        stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")
        assert len(stored) == 1
        assert stored[0].open == Decimal("100.10")

@pytest.mark.requirement("CONFLICT-02")
def test_decimal_numeric_equality_and_created_at_exclusion():
    engine = create_engine_from_url("sqlite:///:memory:")
    repository = CandleRepository(engine); repository.create_tables()
    first = candle(open="100.1", high="101.0", low="99.50", close="100.50", created_at_ms=1000)
    equivalent = candle(open="100.10", high="101.00", low="99.500", close="100.500", created_at_ms=999999)
    assert first.open == equivalent.open == Decimal("100.10")
    assert repository.insert_candles([first]) == 1
    assert repository.insert_candles([equivalent]) == 0
    assert repository.count(symbol="BTCUSDT", timeframe="5m") == 1
