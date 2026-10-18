"""Failure audit contents and the guarantee that an audit failure never masks the original error."""
import logging
import re

import httpx
import pytest
from sqlalchemy import event, text

from tests.fixtures.fakes import FakeResponse
from tests.fixtures.klines import make_row, make_rows
from tests.fixtures.service_env import I, NOW, S0, Env, ok_responses, time_resp

POISON = "https://user:hunter2@evil.example/api/v3/klines?apiKey=SECRETKEY&signature=SIGVALUE Authorization: Bearer TOPSECRET open=100.5"
FORBIDDEN = re.compile(r"https?://|://|hunter2|SECRETKEY|SIGVALUE|TOPSECRET|Bearer|Authorization|apikey|api_key|secret|token|signature|password|"
                       r"@|X-MBX|\{|\}|\[\[", re.I)
CANDLE_VALUES = ("100.5", "1005", "101", "abc")


def all_text(env):
    with env.engine.connect() as connection:
        rows = connection.execute(text("SELECT * FROM data_fetches")).all()
    return rows, " | ".join(str(v) for r in rows for v in r)


def scenarios():
    bad_open = make_rows(S0, 3)
    bad_open[1][1] = "abc"
    changed = make_rows(S0, 3)
    changed[1][5] = "999"
    return {
        "poisoned-generic": lambda: Env([time_resp(S0 + 20 * I)], errors=[]),     # replaced below by a raising http
        "validation-with-values": lambda: Env(ok_responses(3, rows=bad_open)),
        "empty-result": lambda: Env(ok_responses(3, rows=[])),
        "upstream-503": lambda: Env([FakeResponse(status_code=503) for _ in range(4)]),
        "upstream-403": lambda: Env([FakeResponse(status_code=403)]),
        "empty-effective-range": lambda: Env([time_resp(S0 + 1)]),
        "non-final": lambda: Env([time_resp(S0 + 2 * I), FakeResponse(payload=make_rows(S0, 3))]),
        "http-status-error": lambda: Env([], errors=[httpx.HTTPStatusError(f"Server error for url '{POISON}'", request=httpx.Request("GET", "https://x.example"),
                                                                           response=httpx.Response(500, request=httpx.Request("GET", "https://x.example")))]),
    }


@pytest.mark.requirement("AUDIT-01")
def test_failure_audit_contents():
    outcomes = {}
    for name, make in scenarios().items():
        env = make()
        if name == "poisoned-generic":
            env.fake.errors.append(RuntimeError(POISON))             # an unexpected exception whose text carries secrets
        with pytest.raises(Exception):
            env.run(3)
        rows, dump = all_text(env)
        assert len(rows) == 1, name
        audit = env.repo.get_fetches()[0]
        outcomes[name] = audit
        # required content
        assert audit["status"] == "failed" and audit["schema_version"] == 1
        assert audit["error_class"] and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", audit["error_class"])
        assert isinstance(audit["error_text"], str) and 0 < len(audit["error_text"]) <= 240
        assert audit["fetched_at_ms"] == NOW and audit["symbol"] == "BTCUSDT" and audit["timeframe"] == "5m"
        assert (audit["requested_start_ms"], audit["requested_end_ms"]) == (S0, S0 + 3 * I)
        assert audit["dataset_sha256"] is None and audit["row_count"] == 0
        # forbidden content, in every column of the stored row
        assert not FORBIDDEN.search(dump), (name, dump)
        assert not any(v in audit["error_text"] for v in CANDLE_VALUES), (name, audit["error_text"])
        assert env.repo.count() == 0, name
    assert outcomes["poisoned-generic"]["error_text"] == "unexpected internal error" and outcomes["poisoned-generic"]["error_class"] == "RuntimeError"
    assert outcomes["validation-with-values"]["error_text"].startswith("market-data validation failed")
    assert outcomes["http-status-error"]["error_text"].startswith("binance request failed")
    assert outcomes["empty-effective-range"]["error_class"] == "EmptyEffectiveRangeError"
    assert outcomes["non-final"]["error_class"] == "NonFinalCandleError"
    assert "HTTP 403" in outcomes["upstream-403"]["error_text"]


@pytest.mark.requirement("AUDIT-01")
def test_cooldown_failures_are_audited_without_a_request():
    from trading_app.data.binance_client import BinanceClientError
    env = Env(ok_responses(3))
    env.client._cooldown_until_ms = NOW + 600_000
    env.client._now_ms = lambda: NOW
    with pytest.raises(BinanceClientError, match="cooldown active"):
        env.run(3)
    assert env.fake.calls == [] and "cooldown active" in env.repo.get_fetches()[0]["error_text"]


def _fail_first_insert(engine, table, error):
    state = {"armed": True}

    def listener(conn, cursor, statement, parameters, context, executemany):
        if state["armed"] and statement.lstrip().upper().startswith(f"INSERT INTO {table.upper()}"):
            state["armed"] = False
            raise error
    event.listen(engine, "after_cursor_execute", listener)
    return listener


def _fail_every_insert(engine, table, error):
    def listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(f"INSERT INTO {table.upper()}"):
            raise error
    event.listen(engine, "after_cursor_execute", listener)
    return listener


@pytest.mark.requirement("AUDIT-02")
def test_failure_audit_write_cannot_mask_original_exception(caplog):
    caplog.set_level(logging.DEBUG)
    env = Env(ok_responses(3))
    _fail_every_insert(env.engine, "candles", RuntimeError("injected failure after the candle write began"))
    _fail_every_insert(env.engine, "data_fetches", OSError(f"audit disk full {POISON}"))
    with pytest.raises(RuntimeError, match="injected failure after the candle write began") as failed:
        env.run(3)
    assert not isinstance(failed.value, OSError) and "audit disk full" not in str(failed.value)
    assert env.repo.count() == 0 and env.repo.get_fetches() == []                  # nothing persisted, audit missing but harmless
    assert any("failure audit could not be written error_type=OSError" in r.getMessage() for r in caplog.records)
    assert not FORBIDDEN.search("\n".join(r.getMessage() for r in caplog.records))
    # ordering: the candle transaction was explicitly rolled back BEFORE the audit write was even attempted
    timeline = env.timeline
    first_rollback = timeline.index(("sa-rollback",))
    begins = [i for i, e in enumerate(timeline) if e[0] == "sqlite" and e[1].upper().startswith("BEGIN IMMEDIATE")]
    assert len(begins) == 2 and first_rollback < begins[1]


@pytest.mark.requirement("AUDIT-02")
def test_successful_failure_audit_is_written_after_the_rollback():
    env = Env(ok_responses(3))
    _fail_first_insert(env.engine, "candles", RuntimeError("injected failure after the candle write began"))
    with pytest.raises(RuntimeError, match="injected failure"):
        env.run(3)
    assert env.repo.count() == 0
    (audit,) = env.repo.get_fetches()
    assert audit["status"] == "failed" and audit["error_class"] == "RuntimeError" and audit["error_text"] == "unexpected internal error"
    sequence = []
    for statement in env.sqlite("BEGIN", "INSERT", "COMMIT", "ROLLBACK"):
        words = statement.split()
        label = f"INSERT {words[2]}" if words[0].upper() == "INSERT" else " ".join(words[:2]) if words[0].upper() == "BEGIN" else words[0].upper()
        if not sequence or sequence[-1] != label:                 # executemany traces one INSERT per row: collapse them
            sequence.append(label)
    assert sequence == ["BEGIN IMMEDIATE", "INSERT candles", "ROLLBACK", "BEGIN IMMEDIATE", "INSERT data_fetches", "COMMIT"]


@pytest.mark.requirement("AUDIT-02")
def test_original_error_wins_even_when_no_transaction_was_open():
    from trading_app.data.binance_client import BinanceClientError
    env = Env([FakeResponse(status_code=403)])
    _fail_every_insert(env.engine, "data_fetches", OSError("audit disk full"))
    with pytest.raises(BinanceClientError, match="403"):
        env.run(3)


@pytest.mark.requirement("AUDIT-02")
def test_candles_and_success_audit_are_all_or_nothing():
    env = Env(ok_responses(3))
    _fail_first_insert(env.engine, "data_fetches", RuntimeError("injected failure writing the success audit row"))
    with pytest.raises(RuntimeError, match="injected failure"):
        env.run(3)
    assert env.repo.count() == 0                                      # the candles written before the audit row were rolled back too
    (audit,) = env.repo.get_fetches()
    assert audit["status"] == "failed"                                # and no success row exists


@pytest.mark.requirement("AUDIT-01")
def test_failure_after_rows_were_fetched_and_verified_records_that_row_count():
    # (a) conflict with stored data: the 3 rows were fetched and validated before the save failed
    changed = make_rows(S0, 3)
    changed[1][5] = "999"
    env = Env(ok_responses(3) + ok_responses(3, rows=changed))
    env.run(3)
    from trading_app.data.repository import CandleConflictError
    with pytest.raises(CandleConflictError):
        env.run(3)
    success, failure = env.repo.get_fetches()
    assert (success["status"], success["row_count"]) == ("success", 3)
    assert failure["status"] == "failed" and failure["row_count"] == 3 and failure["dataset_sha256"] is None
    assert failure["server_time_ms"] is not None and failure["effective_end_ms"] == S0 + 3 * I      # what was learned is kept too

    # (b) failure after the candle transaction began
    env = Env(ok_responses(4, rows=make_rows(S0, 4)))
    _fail_first_insert(env.engine, "candles", RuntimeError("injected failure after the candle write began"))
    with pytest.raises(RuntimeError):
        env.run(4)
    assert env.repo.get_fetches()[0]["row_count"] == 4 and env.repo.count() == 0

    # (c) failure while preparing the save (hashing), after the fetch and validation succeeded
    from trading_app.data import service as service_module
    env = Env(ok_responses(2))
    real = service_module.hash_candles
    service_module.hash_candles = lambda records: (_ for _ in ()).throw(ValueError("hash failure"))
    try:
        with pytest.raises(ValueError, match="hash failure"):
            env.run(2)
    finally:
        service_module.hash_candles = real
    assert env.repo.get_fetches()[0]["row_count"] == 2


@pytest.mark.requirement("AUDIT-01")
def test_failures_before_any_rows_were_returned_record_zero_rows():
    for responses in ([FakeResponse(status_code=503) for _ in range(4)], ok_responses(3, rows=[]), [time_resp(S0 + 1)]):
        env = Env(responses)
        with pytest.raises(Exception):
            env.run(3)
        assert env.repo.get_fetches()[0]["row_count"] == 0


class RowsClient:
    """A client double that returns rows without any client-side checks, to exercise the service's own verification."""
    finality_lag_ms = 0
    last_fetch = None

    def __init__(self, rows):
        self.rows = rows

    def get_historical_klines(self, **kwargs):
        return self.rows


def service_with(rows):
    from tests.fixtures.service_env import SETTINGS
    from trading_app.data.repository import CandleRepository, create_engine_from_url
    from trading_app.data.service import MarketDataService
    repo = CandleRepository(create_engine_from_url("sqlite:///:memory:"))
    repo.create_tables()
    return MarketDataService(settings=SETTINGS, client=RowsClient(rows), repository=repo, now_ms=lambda: NOW), repo


@pytest.mark.requirement("AUDIT-01")
def test_row_count_is_zero_before_verification_and_positive_after():
    from tests.fixtures.service_env import dt
    from trading_app.data.validator import DataValidationError
    good = make_rows(S0, 3)
    malformed = {
        "short row": [good[0], [S0 + I]],
        "non-numeric price": [good[0], good[1][:1] + ["abc"] + good[1][2:]],
        "bad trade count": [good[0], good[1][:8] + ["x"] + good[1][9:]],
        "none instead of a row": [good[0], None],
        "bad timestamp": [good[0], ["not-a-time"] + good[1][1:]],
    }
    # --- BEFORE verification completes: nothing was verified, so the failure row records 0 even though rows came back
    for name, rows in malformed.items():
        service, repo = service_with(rows)
        with pytest.raises(DataValidationError, match="MALFORMED_ROW") as failed:
            service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 3 * I))
        assert failed.value.__cause__ is None and failed.value.__context__ is None, name
        assert "abc" not in str(failed.value) and "100" not in str(failed.value) and "not-a-time" not in str(failed.value), name   # no row values in the message either
        (audit,) = repo.get_fetches()
        assert audit["row_count"] == 0, name
        assert (audit["status"], audit["error_class"]) == ("failed", "DataValidationError")
        assert audit["error_text"] == "market-data validation failed: MALFORMED_ROW", name
        assert "abc" not in audit["error_text"] and repo.count() == 0
    # --- AFTER verification: the same service, valid rows, failing later -> the real positive count
    service, repo = service_with(good)
    assert service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 3 * I)) == 3
    changed = [list(r) for r in good]
    changed[1][5] = "999"
    service.client.rows = changed
    from trading_app.data.repository import CandleConflictError
    with pytest.raises(CandleConflictError):
        service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 3 * I))
    assert [a["row_count"] for a in repo.get_fetches()] == [3, 3]
    _fail_first_insert(repo.engine, "candles", RuntimeError("injected failure after the candle write began"))
    service.client.rows = make_rows(S0 + 10 * I, 2)
    with pytest.raises(RuntimeError, match="injected"):
        service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=dt(S0 + 10 * I), end=dt(S0 + 12 * I))
    assert repo.get_fetches()[-1]["row_count"] == 2 and repo.get_fetches()[-1]["status"] == "failed"
