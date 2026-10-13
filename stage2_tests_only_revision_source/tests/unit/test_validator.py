"""Raw Binance kline validation acceptance tests."""
from datetime import datetime, timezone
import pytest
from trading_app.data.validator import DataValidationError, assert_valid_klines, timeframe_to_ms, utc_datetime_from_ms
START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
INTERVAL = 300_000

def kline(open_time_ms, *, open_price="100", high="101", low="99", close="100.5", volume="10", quote_volume="1005", close_time_ms=None, trades=100):
    return [open_time_ms, open_price, high, low, close, volume, close_time_ms if close_time_ms is not None else open_time_ms + INTERVAL - 1, quote_volume, trades, "1", "2", "0"]

@pytest.mark.requirement("M1-09")
def test_candle_duration():
    assert timeframe_to_ms("5m") == INTERVAL
    assert timeframe_to_ms("1h") == 3_600_000

@pytest.mark.requirement("M1-10")
def test_duplicate_candles():
    with pytest.raises(DataValidationError, match="DUPLICATE_CANDLE"):
        assert_valid_klines([kline(START), kline(START)], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-10")
def test_duplicate_price_volume_and_ohlc_validation():
    bad = kline(START, high="90", low="80", open_price="100", close="95")
    with pytest.raises(DataValidationError, match="INVALID_OHLC"):
        assert_valid_klines([bad], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-10")
def test_invalid_prices():
    row = kline(START); row[1] = "0"
    with pytest.raises(DataValidationError, match="INVALID_PRICE"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-10")
def test_invalid_volumes():
    row = kline(START); row[5] = "-1"
    with pytest.raises(DataValidationError, match="INVALID_VOLUME"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-09")
def test_missing_candles():
    with pytest.raises(DataValidationError, match="MISSING_CANDLES"):
        assert_valid_klines([kline(START), kline(START + 2*INTERVAL)], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-09")
def test_monotonic_timestamps():
    with pytest.raises(DataValidationError, match="NON_MONOTONIC_TIMESTAMP"):
        assert_valid_klines([kline(START + INTERVAL), kline(START)], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-10")
def test_ohlc_consistency():
    row = kline(START, open_price="100", high="99", low="90", close="95")
    with pytest.raises(DataValidationError, match="INVALID_OHLC"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-11")
def test_suspicious_data_is_reported_without_repair():
    row = kline(START, volume="-1")
    original = list(row)
    with pytest.raises(DataValidationError, match="INVALID_VOLUME"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")
    assert row == original

@pytest.mark.requirement("M1-09")
def test_timestamp_alignment():
    with pytest.raises(DataValidationError, match="MISALIGNED_TIMESTAMP"):
        assert_valid_klines([kline(START + 1)], symbol="BTCUSDT", timeframe="5m")

@pytest.mark.requirement("M1-09")
def test_timestamp_alignment_duration_monotonicity_and_missing_candles():
    rows = [kline(START), kline(START + INTERVAL), kline(START + 2*INTERVAL)]
    assert_valid_klines(rows, symbol="BTCUSDT", timeframe="5m", expected_start_ms=START, expected_end_ms_exclusive=START + 3*INTERVAL)
    assert utc_datetime_from_ms(START).tzinfo is not None
