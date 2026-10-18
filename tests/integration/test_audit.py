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
