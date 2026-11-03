"""Regression: an empty result for an expected range must not validate."""
import pytest
from trading_app.data.validator import DataValidationError, assert_valid_klines


@pytest.mark.requirement("M1-09")
def test_empty_rows_with_expected_range_are_rejected():
    with pytest.raises(DataValidationError, match="EMPTY_RESULT"):
        assert_valid_klines([], symbol="BTCUSDT", timeframe="5m",
                            expected_start_ms=1767571200000,
                            expected_end_ms_exclusive=1767571500000)


@pytest.mark.requirement("M1-09")
def test_empty_rows_without_expectations_have_no_issues():
    assert_valid_klines([], symbol="BTCUSDT", timeframe="5m")
