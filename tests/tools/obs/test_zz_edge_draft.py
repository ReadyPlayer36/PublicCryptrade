"""Boundary-condition drafts for the OBS harness (target: impl-obs-harness).

Standalone scaffolding for integration. Every case below was grepped
against the current suite first, so none of them duplicate existing assertions:
JSONL line-level parsing (_jsonl), the estimator's outward rounding, zero-duration
deadline edges in watchdog/transport, a stale pacing target, and a boolean timestamp.
Offline only: fake clock, fake connections, scripted transport. No sockets, no sleep
longer than 50 ms.
"""
from __future__ import annotations

import json
import threading
import pytest

from tests.fixtures.obs_fakes import FakeClock, ScriptedTransport, audit_all
from tools.obs.clock import SystemClock
from tools.obs.estimator import TimeSample, exact_interval, interval
from tools.obs.params import DELTA, KLINES_PATH, MS, S
from tools.obs.pacer import Pacer, RequestRecord
from tools.obs.runstore import ManifestError, _RECORD_KEYS, _jsonl
from tools.obs.specs import klines_request
from tools.obs.transport import DEADLINE, HttpTransport
from tools.obs.watchdog import CancellationFailed, CancellationState, run_with_deadline

CLOCK = SystemClock()
KLINES = klines_request(symbol="BTCUSDT", interval="5m", start_ms=0, end_ms=299_999, limit=1, role="PROBE")

def at(seconds: float) -> int:
    """Absolute monotonic deadline `seconds` from now (the suite's convention)."""
    return CLOCK.now_ns() + int(seconds * S)

# ---------------- runstore: malformed JSONL streaming lines (parser level) ----------------

def _record_line(**over) -> bytes:
    obj = dict(seq=1, role="PROBE", path=KLINES_PATH, start_ns=1, end_ns=2, status=200, error=None,
               group_name=None, group_kind=None, boundary_ms=None, body_b64="", headers=[])
    obj.update(over)
    return json.dumps(obj).encode()

def test_a_blank_line_inside_records_jsonl_is_rejected_with_its_line_number():
    raw = _record_line() + b"\n" + b"\n" + _record_line(seq=2) + b"\n"
    with pytest.raises(ManifestError) as excinfo:
        _jsonl(raw, "records.jsonl", _RECORD_KEYS)
    assert "line 2" in str(excinfo.value) and "not valid JSON" in str(excinfo.value)

def test_a_jsonl_line_with_an_embedded_nul_byte_fails_closed_not_skipped():
    with pytest.raises(ManifestError, match="not valid JSON"):
        _jsonl(b'{"seq": 1, "x": \x00}\n', "records.jsonl", _RECORD_KEYS)

def test_crlf_line_endings_parse_to_exactly_the_same_records():
    lf = _jsonl(_record_line() + b"\n", "records.jsonl", _RECORD_KEYS)
    crlf = _jsonl(_record_line() + b"\r\n", "records.jsonl", _RECORD_KEYS)
    assert crlf == lf and len(crlf) == 1 and set(crlf[0]) == set(_RECORD_KEYS)

def test_an_empty_records_file_is_valid_and_yields_zero_records():
    assert _jsonl(b"", "records.jsonl", _RECORD_KEYS) == []

# ---------------- estimator: outward rounding of fractional bounds ----------------

def test_the_integer_interval_rounds_fractional_endpoints_outward_exactly():
    sample = TimeSample(0, 0, 0)
    lo, hi = exact_interval(sample, 1)
    assert lo == -DELTA and hi == MS + DELTA
    assert interval(sample, 1) == (-1, MS + 1)

# ---------------- watchdog: zero-duration deadline edges ----------------

def _capturing_thread_factory(captured: list):
    """thread_factory for run_with_deadline that records the worker so a test can assert on it and join it."""
    def factory(*args, **kwargs):
        thread = threading.Thread(*args, **kwargs)
        captured.append(thread)
        return thread
    return factory

def test_zero_cancellation_grace_fails_at_the_deadline_without_waiting():
    release, cancelled, state, workers = threading.Event(), [], CancellationState(), []

    def stubborn() -> None:
        release.wait(10)            # safety net only: the finally below always releases it

    try:
        with pytest.raises(CancellationFailed):
            run_with_deadline(stubborn, lambda: cancelled.append(1),
                              deadline_at_ns=at(0.05), clock=CLOCK, grace_ns=0, state=state,
                              thread_factory=_capturing_thread_factory(workers))
        # zero grace means no extra waiting: the failure is reported while the worker is still blocked (orphaned)
        assert len(workers) == 1 and workers[0].is_alive()
        assert cancelled == [1] and state.cancelled
    finally:
        release.set()               # guaranteed cleanup: the worker always exits, never a 10 s orphan
        for worker in workers:
            worker.join(timeout=5)
    assert all(not worker.is_alive() for worker in workers)

def test_a_deadline_that_is_already_past_cancels_at_once_and_the_grace_is_a_bound_not_a_wait():
    release, cancelled, workers = threading.Event(), [], []

    def cooperative() -> int:
        release.wait(10)            # safety net only: cancel() (and the finally below) release it
        return 42

    try:
        result = run_with_deadline(cooperative, lambda: (cancelled.append(1), release.set()),
                                   deadline_at_ns=CLOCK.now_ns(), clock=CLOCK, grace_ns=int(1 * S),
                                   thread_factory=_capturing_thread_factory(workers))
        assert result.timed_out and result.error is None and result.value is None
        assert cancelled == [1] and release.is_set()
        assert len(workers) == 1 and not workers[0].is_alive()     # the cancelled worker finished inside the grace
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=5)

# ---------------- transport: zero-duration timeout at the absolute deadline ----------------

class _Sock:
    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def shutdown(self, how: int) -> None:       # the transport shuts the socket down when it gives up
        pass

class _Resp:
    status = 200

    def read(self, limit: int) -> bytes:
        return b"[]"

    def getheaders(self):
        return [("content-type", "application/json")]

class _Conn:
    def __init__(self, on_connect=None) -> None:
        self.sock, self.auto_open = _Sock(), 1
        self.on_connect, self.requests, self.closed = on_connect, [], False

    def connect(self) -> None:
        if self.on_connect is not None:
            self.on_connect()

    def request(self, method, target, headers=None) -> None:
        self.requests.append((method, target))

    def getresponse(self):
        return _Resp()

    def close(self) -> None:
        self.closed = True

def _factory(made: list, on_connect=None, conns: list | None = None):
    def make(scheme, host, port, timeout):
        made.append((scheme, host, port, timeout))
        conn = _Conn(on_connect)
        if conns is not None:
            conns.append(conn)
        return conn
    return make

def test_a_deadline_exactly_at_now_is_a_deadline_with_no_connection_opened():
    clock, made = FakeClock(0), []
    transport = HttpTransport(clock=clock, connection_factory=_factory(made))
    result = transport.send(KLINES, deadline_at_ns=clock.now_ns())
    assert (result.status, result.error) == (None, DEADLINE)
    assert transport.sent == 1 and made == [] and transport.disabled_reason is None

def test_one_nanosecond_of_deadline_budget_still_sends_the_request():
    # ASSUMPTION: FakeClock is static (it never advances on its own), so with now == 0 and deadline == 1 ns every deadline
    # check inside the transport (before connect, before the write) sees the same 1 ns of budget. This test pins only that
    # strict boundary; the clock moving past the deadline mid-flight is covered by the controlled-clock test below.
    clock, made = FakeClock(0), []
    transport = HttpTransport(clock=clock, connection_factory=_factory(made))
    result = transport.send(KLINES, deadline_at_ns=1)
    assert (result.status, result.error) == (200, None) and result.body == b"[]"
    assert transport.sent == 1 and len(made) == 1 and transport.disabled_reason is None

def test_a_deadline_that_expires_between_the_connect_check_and_the_write_check_blocks_the_write():
    clock, made, conns = FakeClock(0), [], []
    deadline = 1_000

    def expire_during_connect() -> None:
        clock.now = deadline        # the connection phase takes "too long": the clock is exactly at the deadline afterwards

    transport = HttpTransport(clock=clock, connection_factory=_factory(made, expire_during_connect, conns))
    result = transport.send(KLINES, deadline_at_ns=deadline)
    assert (result.status, result.error) == (None, DEADLINE)
    assert len(made) == 1 and len(conns) == 1           # the pre-connect check passed: a connection was set up
    assert conns[0].requests == []                      # ...but the pre-write check refused: nothing was ever written
    assert conns[0].closed
    assert transport.sent == 1 and transport.disabled_reason is None

# ---------------- pacer: a stale target may neither delay nor rewind ----------------

def test_a_target_in_the_past_never_delays_or_rewinds_the_start():
    clock = FakeClock(100 * S)
    transport = ScriptedTransport(clock, durations_ns=[])
    pacer = Pacer(clock, transport)
    record = pacer.execute(KLINES, target_ns=5 * S)
    assert record.start_ns == 100 * S
    assert clock.sleeps == []
    assert transport.deadlines == [100 * S + 17 * S]

# ---------------- audit: a boolean timestamp is not a one-nanosecond duration ----------------

def test_a_boolean_end_ns_on_a_lone_record_is_an_audited_failure():
    record = RequestRecord(seq=1, role="PROBE", path=KLINES_PATH, start_ns=0, end_ns=True,
                           status=200, error=None, body=b"[]")
    result = audit_all([record])
    assert not result.ok and "a" in result.checks()
