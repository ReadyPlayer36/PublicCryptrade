"""Regression tests for independent-review findings on Stage A."""
import pytest
from trading_app.data.finality import effective_end_ms, is_final
from trading_app.data.validator import validate_klines

S, I = 1767571200000, 300000


def kline(open_time, **over):
    close = open_time + I - 1 if isinstance(open_time, (int, float)) else 0
    row = [open_time, "100", "101", "99", "100.5", "10", close, "1005", 100, "1", "2", "0"]
    for index, value in over.items():
        row[int(index[1:])] = value
    return row


def codes(rows, **kw):
    return {i.code for i in validate_klines(rows, symbol="BTCUSDT", timeframe="5m", **kw)}


@pytest.mark.requirement("M1-09")
@pytest.mark.parametrize("bad", [S + 0.9, float("inf"), float("-inf"), float("nan"), True])
def test_bad_open_time_values_are_reported_not_truncated_or_raised(bad):
    assert "INVALID_TIMESTAMP" in codes([kline(bad)])


@pytest.mark.requirement("M1-09")
@pytest.mark.parametrize("bad", [5.5, float("inf"), float("-inf"), float("nan"), -1, "x", True])
def test_bad_trade_counts_are_reported(bad):
    assert "INVALID_TRADE_COUNT" in codes([kline(S, f8=bad)])


@pytest.mark.requirement("M1-09")
def test_valid_integer_strings_and_integral_numbers_are_accepted():
    row = kline(str(S), f8="100")
    row[6] = str(S + I - 1)
    assert codes([row]) == set()
    assert "INVALID_TRADE_COUNT" not in codes([kline(S, f8=100.0)])


@pytest.mark.requirement("M1-09")
def test_misaligned_gap_does_not_claim_zero_missing_candles():
    issues = validate_klines([kline(0), kline(300001)], symbol="BTCUSDT", timeframe="5m")
    found = {i.code for i in issues}
    assert "MISALIGNED_TIMESTAMP" in found
    assert "MISSING_CANDLES" not in found


@pytest.mark.requirement("M1-09")
def test_real_multi_candle_gap_still_reported():
    issues = validate_klines([kline(S), kline(S + 3 * I)], symbol="BTCUSDT", timeframe="5m")
    assert any(i.code == "MISSING_CANDLES" and "2 candle" in i.message for i in issues)


@pytest.mark.requirement("M1-09")
def test_multiple_defects_are_all_returned():
    row = kline(S, f1="-1", f5="Infinity", f6=S)
    found = codes([row])
    assert {"INVALID_PRICE", "INVALID_VOLUME", "INVALID_CLOSE_TIME"} <= found


@pytest.mark.requirement("M1-09")
def test_unaligned_expected_range_is_rejected_explicitly():
    assert "INVALID_EXPECTED_RANGE" in codes([kline(S)], expected_start_ms=S + 1)
    assert "INVALID_EXPECTED_RANGE" in codes([kline(S)], expected_end_ms_exclusive=S + I + 1)


@pytest.mark.requirement("M1-09")
def test_negative_lag_is_rejected_by_finality_helpers():
    with pytest.raises(ValueError, match="lag_ms"):
        is_final(S - 1, S, -1)
    with pytest.raises(ValueError, match="lag_ms"):
        effective_end_ms(S + 10 * I, S, -1, I)
