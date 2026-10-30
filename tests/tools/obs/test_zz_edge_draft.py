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
import time
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

def test_zero_cancellation_grace_fails_at_the_deadline_without_waiting():
    release, cancelled, state = threading.Event(), [], CancellationState()

    def stubborn() -> None:
        release.wait(10)

    t0 = time.monotonic()
    with pytest.raises(CancellationFailed):
        run_with_deadline(stubborn, lambda: cancelled.append(1),
                          deadline_at_ns=at(0.05), clock=CLOCK, grace_ns=0, state=state)
    elapsed = time.monotonic() - t0
    assert 0.05 <= elapsed < 0.5
    assert cancelled == [1] and state.cancelled

def test_a_deadline_that_is_already_past_cancels_at_once_and_the_grace_is_a_bound_not_a_wait():
    release, cancelled = threading.Event(), []

    def cooperative() -> int:
        release.wait(10)
        return 42

    t0 = time.monotonic()
    result = run_with_deadline(cooperative, lambda: (cancelled.append(1), release.set()),
                               deadline_at_ns=CLOCK.now_ns(), clock=CLOCK, grace_ns=int(1 * S))
    elapsed = time.monotonic() - t0
    assert result.timed_out and result.error is None and result.value is None
    assert cancelled == [1]
    assert elapsed < 0.5

# ---------------- transport: zero-duration timeout at the absolute deadline ----------------

class _Sock:
    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

class _Resp:
    status = 200

    def read(self, limit: int) -> bytes:
        return b"[]"

    def getheaders(self):
        return [("content-type", "application/json")]

class _Conn:
    def __init__(self) -> None:
        self.sock, self.auto_open = _Sock(), 1

    def connect(self) -> None:
        pass

    def request(self, method, target, headers=None) -> None:
        pass

    def getresponse(self):
        return _Resp()

    def close(self) -> None:
        pass

def _factory(made: list):
    def make(scheme, host, port, timeout):
        made.append((scheme, host, port, timeout))
        return _Conn()
    return make

def test_a_deadline_exactly_at_now_is_a_deadline_with_no_connection_opened():
    clock, made = FakeClock(0), []
    transport = HttpTransport(clock=clock, connection_factory=_factory(made))
    result = transport.send(KLINES, deadline_at_ns=clock.now_ns())
    assert (result.status, result.error) == (None, DEADLINE)
    assert transport.sent == 1 and made == [] and transport.disabled_reason is None

def test_one_nanosecond_of_deadline_budget_still_sends_the_request():
    clock, made = FakeClock(0), []
    transport = HttpTransport(clock=clock, connection_factory=_factory(made))
    result = transport.send(KLINES, deadline_at_ns=1)
    assert (result.status, result.error) == (200, None) and result.body == b"[]"
    assert transport.sent == 1 and len(made) == 1 and transport.disabled_reason is None

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
