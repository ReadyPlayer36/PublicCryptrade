"""Download service: repeatable ingestion and failure behaviour (fake HTTP, no network)."""
import hashlib

import pytest

from tests.fixtures.klines import make_row, make_rows
from tests.fixtures.service_env import I, S0, Env, dt, ok_responses, time_resp
from tests.fixtures.fakes import FakeResponse
from trading_app.data.repository import CandleConflictError
from trading_app.data.validator import DataValidationError


def independent_sha256(rows, symbol="BTCUSDT", timeframe="5m"):
    """Re-implements the frozen serialization without using trading_app.data.hashing (cross-check)."""
    lines = []
    for r in rows:
        fields = [symbol, timeframe, str(int(r[0])), str(int(r[6])), r[1], r[2], r[3], r[4], r[5], r[7], str(int(r[8]))]
        lines.append("\x1f".join(fields))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@pytest.mark.requirement("M1-14")
def test_repeatable_ingestion_is_idempotent():
    rows = make_rows(S0, 3)
    env = Env(ok_responses(3, rows=rows) + ok_responses(3, rows=rows) + ok_responses(4, rows=make_rows(S0, 4)))
    assert env.run(3) == 3                                           # first run stores everything
    first = env.repo.get_candles(symbol="BTCUSDT", timeframe="5m")
    assert env.run(3) == 0                                           # identical rerun stores nothing new
    assert env.repo.get_candles(symbol="BTCUSDT", timeframe="5m") == first and env.repo.count() == 3
    assert env.run(4) == 1                                           # a longer range adds exactly the one missing candle
    assert env.repo.count() == 4 and env.repo.get_candles(symbol="BTCUSDT", timeframe="5m")[:3] == first
    audits = env.repo.get_fetches()
    assert [a["status"] for a in audits] == ["success"] * 3
    assert audits[0]["dataset_sha256"] == audits[1]["dataset_sha256"] == independent_sha256(rows)   # same data, same fingerprint
    assert audits[2]["dataset_sha256"] != audits[0]["dataset_sha256"] and [a["row_count"] for a in audits] == [3, 3, 4]


@pytest.mark.requirement("M1-14")
def test_rerun_with_changed_data_is_a_conflict_and_changes_nothing():
    changed = make_rows(S0, 3)
    changed[1][5] = "999"                                          # same candle, different volume: valid data, but a conflict
    env = Env(ok_responses(3) + ok_responses(3, rows=changed))
    env.run(3)
    snapshot = env.repo.get_candles(symbol="BTCUSDT", timeframe="5m")
    with pytest.raises(CandleConflictError):
        env.run(3)
    assert env.repo.get_candles(symbol="BTCUSDT", timeframe="5m") == snapshot
    audits = env.repo.get_fetches()
    assert [a["status"] for a in audits] == ["success", "failed"]
    assert audits[1]["error_class"] == "CandleConflictError" and audits[1]["error_text"] == "candle conflict with stored data in fields: volume"


@pytest.mark.requirement("M1-14")
@pytest.mark.parametrize("symbol,timeframe", [("DOGEUSDT", "5m"), ("BTCUSDT", "1d"), ("BTC/USDT", "5m"), ("", "5m")])
def test_unconfigured_symbol_or_timeframe_is_rejected_before_any_network_or_database_work(symbol, timeframe):
    env = Env(ok_responses(3))
    with pytest.raises(ValueError, match="not configured"):
        env.run(3, symbol=symbol, timeframe=timeframe)
    assert env.fake.calls == [] and env.repo.count() == 0 and env.repo.get_fetches() == []
    assert not [e for e in env.timeline if e[0] == "sqlite" and e[1].upper().startswith(("BEGIN", "INSERT"))]


@pytest.mark.requirement("M1-14")
def test_symbol_is_case_insensitive_and_stored_upper_case():
    env = Env(ok_responses(2))
    assert env.run(2, symbol="btcusdt") == 2
    assert env.repo.get_candles(symbol="BTCUSDT", timeframe="5m") and env.repo.get_fetches()[0]["symbol"] == "BTCUSDT"


@pytest.mark.requirement("M1-14")
def test_naive_datetimes_are_rejected_before_any_network_or_database_work():
    from datetime import datetime
    env = Env(ok_responses(3))
    with pytest.raises(ValueError, match="timezone"):
        env.service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=datetime(2026, 1, 5), end=dt(S0 + I))
    assert env.fake.calls == [] and env.repo.get_fetches() == []


@pytest.mark.requirement("M1-14")
def test_validation_failure_stores_no_candles_and_records_a_failure():
    gap = [make_row(S0), make_row(S0 + 2 * I)]
    env = Env(ok_responses(3, rows=gap))
    with pytest.raises(DataValidationError):
        env.run(3)
    assert env.repo.count() == 0
    (audit,) = env.repo.get_fetches()
    assert audit["status"] == "failed" and audit["error_class"] == "DataValidationError" and "MISSING_CANDLES" in audit["error_text"]


@pytest.mark.requirement("M1-14")
def test_upstream_failure_stores_nothing_and_records_a_failure():
    env = Env([FakeResponse(status_code=503) for _ in range(4)])
    from trading_app.data.binance_client import BinanceClientError
    with pytest.raises(BinanceClientError):
        env.run(3)
    (audit,) = env.repo.get_fetches()
    assert env.repo.count() == 0 and audit["status"] == "failed" and audit["server_time_ms"] is None and "HTTP 503" in audit["error_text"]


@pytest.mark.requirement("M1-14")
def test_empty_upstream_response_is_a_failure_not_a_silent_success():
    env = Env(ok_responses(3, rows=[]))
    with pytest.raises(DataValidationError, match="EMPTY_RESULT"):
        env.run(3)
    assert env.repo.count() == 0 and env.repo.get_fetches()[0]["status"] == "failed"
