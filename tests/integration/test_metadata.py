"""data_fetches metadata (META-01)."""
import httpx
import pytest
from sqlalchemy import inspect

from tests.fixtures.service_env import I, NOW, S0, Env, ok_responses, time_resp
from tests.fixtures.fakes import FakeResponse
from tests.fixtures.klines import make_rows
from trading_app.data.repository import FETCH_SCHEMA_VERSION

EXPECTED_COLUMNS = ["id", "schema_version", "symbol", "timeframe", "requested_start_ms", "requested_end_ms",
                    "effective_start_ms", "effective_end_ms", "server_time_ms", "finality_lag_ms", "host", "row_count",
                    "dataset_sha256", "status", "error_class", "error_text", "fetched_at_ms"]


@pytest.mark.requirement("META-01")
def test_data_fetch_metadata_fields():
    env = Env(ok_responses(2, server_ms=S0 + 3 * I + 5), lag=I, now_ms=lambda: NOW)
    assert [c["name"] for c in inspect(env.engine).get_columns("data_fetches")] == EXPECTED_COLUMNS
    env.run(3)                                              # asks for 3 candles; the lag leaves only 2 final ones
    (row,) = env.repo.get_fetches()
    assert row["schema_version"] == FETCH_SCHEMA_VERSION == 1
    assert (row["symbol"], row["timeframe"]) == ("BTCUSDT", "5m")
    assert (row["requested_start_ms"], row["requested_end_ms"]) == (S0, S0 + 3 * I)
    assert (row["effective_start_ms"], row["effective_end_ms"]) == (S0, S0 + 2 * I)       # clamped by S - L
    assert row["server_time_ms"] == S0 + 3 * I + 5 and row["finality_lag_ms"] == I
    assert row["host"] == "data-api.binance.vision" and row["row_count"] == 2
    assert len(row["dataset_sha256"]) == 64 and set(row["dataset_sha256"]) <= set("0123456789abcdef")
    assert (row["status"], row["error_class"], row["error_text"]) == ("success", None, None)
    assert row["fetched_at_ms"] == NOW                      # the injected audit clock, never the finality clock


@pytest.mark.requirement("META-01")
def test_column_types_and_nullability():
    env = Env()
    columns = {c["name"]: c for c in inspect(env.engine).get_columns("data_fetches")}
    required = {"schema_version", "symbol", "timeframe", "requested_start_ms", "requested_end_ms", "row_count", "status", "fetched_at_ms"}
    nullable = {"effective_start_ms", "effective_end_ms", "server_time_ms", "finality_lag_ms", "host", "dataset_sha256", "error_class", "error_text"}
    assert all(not columns[n]["nullable"] for n in required) and all(columns[n]["nullable"] for n in nullable)


@pytest.mark.requirement("META-01")
def test_fallback_host_is_recorded():
    env = Env([], errors=[httpx.ConnectError("dns")])
    env.fake.responses.extend(ok_responses(2))
    env.run(2)
    assert env.repo.get_fetches()[0]["host"] == "api.binance.com"


@pytest.mark.requirement("META-01")
def test_failure_before_server_time_records_unknowns_as_null_and_keeps_the_configured_lag():
    from trading_app.data.binance_client import BinanceClientError
    env = Env([FakeResponse(status_code=503) for _ in range(4)], lag=60000)
    with pytest.raises(BinanceClientError):
        env.run(3)
    (row,) = env.repo.get_fetches()
    assert row["server_time_ms"] is None and row["effective_end_ms"] is None and row["host"] is None
    assert row["finality_lag_ms"] == 60000 and row["requested_start_ms"] == S0 and row["row_count"] == 0


@pytest.mark.requirement("META-01")
def test_failure_after_server_time_records_what_was_learned():
    from trading_app.data.validator import DataValidationError
    env = Env([time_resp(S0 + 20 * I), FakeResponse(payload=[])])
    with pytest.raises(DataValidationError):
        env.run(3)
    (row,) = env.repo.get_fetches()
    assert row["server_time_ms"] == S0 + 20 * I and row["effective_end_ms"] == S0 + 3 * I and row["host"] == "data-api.binance.vision"
    assert row["status"] == "failed" and row["dataset_sha256"] is None
