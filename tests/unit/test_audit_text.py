"""Unit tests for audit-safe text and fetch-record validation (no database)."""
import pytest

from trading_app.data.audit import FORBIDDEN_AUDIT_TEXT, MAX_AUDIT_TEXT, assert_safe_audit_text
from trading_app.data.binance_client import BinanceClientError
from trading_app.data.finality import EmptyEffectiveRangeError, NaiveDatetimeError, NonFinalCandleError
from trading_app.data.repository import CandleConflictError, CandleRepository, TooManyCandlesError
from trading_app.data.service import safe_error_text
from trading_app.data.validator import DataValidationError

POISON = "https://user:hunter2@evil.example/x?apiKey=SECRET Bearer TOK open=100.5 {'a': 1}"


class ExplodingEngine:
    def __getattr__(self, name):
        raise AssertionError(f"engine.{name} used before validation finished")


@pytest.mark.requirement("AUDIT-01")
@pytest.mark.parametrize("exc,expected", [
    (CandleConflictError("conflict for BTCUSDT 5m at 17: existing candle is different in: close, volume; nothing was written"),
     "candle conflict with stored data in fields: close, volume"),
    (CandleConflictError("conflict inside the batch for BTCUSDT 5m at 17: fields differ: trade_count"), "candle conflict with stored data in fields: trade_count"),
    (CandleConflictError(f"weird {POISON}"), "candle conflict with stored data"),
    (DataValidationError(f"failed:\n[INVALID_PRICE] Row 1: open is not a valid decimal: 'abc'\n[MISSING_CANDLES] x {POISON}"),
     "market-data validation failed: INVALID_PRICE, MISSING_CANDLES"),
    (DataValidationError("no codes at all"), "market-data validation failed"),
    (NonFinalCandleError(POISON), "upstream returned a non-final candle"),
    (EmptyEffectiveRangeError(POISON), "effective range is empty (requested candles are not final yet)"),
    (NaiveDatetimeError(POISON), "naive datetime rejected"),
    (TooManyCandlesError(POISON), "fetch exceeds max_candles_per_fetch"),
    (BinanceClientError(f"HTTP 503 {POISON}"), "binance request failed (HTTP 503)"),
    (BinanceClientError("HTTP 429 rate limit persisted; cooldown active until 5 ms"), "binance request failed (HTTP 429, cooldown active)"),
    (BinanceClientError(f"Binance request to /api/v3/time failed after 4 attempts: timeout (ReadTimeout) {POISON}"), "binance request failed (timeout)"),
    (BinanceClientError("cooldown state unreadable or invalid; failing closed"), "binance request failed (failing closed)"),
    (BinanceClientError(POISON), "binance request failed"),
    (ValueError(POISON), "invalid input rejected"),
    (RuntimeError(POISON), "unexpected internal error"),
    (KeyError(POISON), "unexpected internal error"),
])
def test_safe_error_text_uses_a_fixed_vocabulary(exc, expected):
    text = safe_error_text(exc)
    assert text == expected
    assert not FORBIDDEN_AUDIT_TEXT.search(text) and len(text) <= MAX_AUDIT_TEXT
    assert not any(token in text for token in ("hunter2", "SECRET", "TOK", "100.5", "abc", "evil.example"))
    assert_safe_audit_text(text)


@pytest.mark.requirement("AUDIT-01")
@pytest.mark.parametrize("text", ["https://x.example", "ftp://x", "www.x.com", "user@host", "apiKey=1", "api_key", "SECRET", "a token", "signature",
                                  "Password", "Bearer abc", "Authorization", "X-MBX-APIKEY", "cookie", "{'k': 1}", "[[1, 2]]", "open=100.5", "close = 9",
                                  "d" * 64, "x" * (MAX_AUDIT_TEXT + 1), 5])
def test_unsafe_audit_text_is_rejected(text):
    with pytest.raises(ValueError):
        assert_safe_audit_text(text)


@pytest.mark.requirement("AUDIT-01")
@pytest.mark.parametrize("text", [None, "binance request failed (HTTP 503)", "market-data validation failed: INVALID_PRICE", "candle conflict with stored data in fields: close"])
def test_safe_audit_text_is_accepted(text):
    assert_safe_audit_text(text)


GOOD_FAILED = dict(symbol="BTCUSDT", timeframe="5m", requested_start_ms=1, requested_end_ms=2, effective_start_ms=None, effective_end_ms=None,
                   server_time_ms=None, finality_lag_ms=0, host=None, row_count=0, dataset_sha256=None, status="failed",
                   error_class="RuntimeError", error_text="unexpected internal error", fetched_at_ms=3)
GOOD_SUCCESS = {**GOOD_FAILED, "status": "success", "dataset_sha256": "a" * 64, "error_class": None, "error_text": None, "row_count": 1}


@pytest.mark.requirement("META-01")
@pytest.mark.parametrize("change", [
    {"status": "success"}, {"dataset_sha256": "a" * 64}, {"error_class": None}, {"error_text": ""}, {"error_class": "bad class!"},
    {"error_text": "https://x.example"}, {"symbol": ""}, {"requested_start_ms": -1}, {"requested_start_ms": True}, {"row_count": 1.5},
    {"host": "evil.example/path"}, {"host": "u@h"}, {"host": "h:443"}, {"unknown_field": 1}, {"schema_version": 2}, {"fetched_at_ms": None},
    {"server_time_ms": -5}, {"finality_lag_ms": "0"},
])
def test_invalid_failed_fetch_records_are_rejected_before_any_database_work(change):
    repository = CandleRepository(ExplodingEngine())
    with pytest.raises(ValueError):
        repository.record_failed_fetch({**GOOD_FAILED, **change})


@pytest.mark.requirement("META-01")
@pytest.mark.parametrize("change", [
    {"status": "failed"}, {"dataset_sha256": None}, {"dataset_sha256": "A" * 64}, {"dataset_sha256": "a" * 63}, {"dataset_sha256": "g" * 64},
    {"error_class": "RuntimeError"}, {"error_text": "x"}, {"row_count": -1},
])
def test_invalid_success_fetch_records_are_rejected_before_any_database_work(change):
    repository = CandleRepository(ExplodingEngine())
    with pytest.raises(ValueError):
        repository.insert_candles_with_fetch([], {**GOOD_SUCCESS, **change})
