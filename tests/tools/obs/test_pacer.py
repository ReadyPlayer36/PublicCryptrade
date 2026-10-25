"""Completion-aware pacer (PACE-1, 2, 3, 4, 6): spacing, completion-before-start, rolling caps, targets, incident rule."""
import pytest

import threading
import time

from tests.fixtures.obs_fakes import FakeClock, ScriptedTransport, audit_all
from tools.obs.watchdog import CancellationFailed
from tools.obs.pacer import OBS01_PROFILE, ConcurrentExecution, NetworkIncident, NonOkResponse, Pacer, PacerAborted, release_ns, window_count
from tools.obs.params import MS, S
from tools.obs.specs import RequestSpec, UnsafeRequest, klines_request
from tools.obs.transport import CANCEL_FAILED, CONNECT_ERROR, DEADLINE, TransportResult


def probe():
    """A request that is valid for the audit when sent without a group (role PROBE, klines path)."""
    return klines_request(symbol="BTCUSDT", interval="5m", start_ms=0, end_ms=299_999, limit=1, role="PROBE")


def make(durations=(), results=None, profile=None, start=0):
    clock = FakeClock(start)
    transport = ScriptedTransport(clock, durations, results)
    kwargs = {} if profile is None else {"profile": profile}
    return clock, transport, Pacer(clock, transport, **kwargs)


def test_first_request_starts_immediately_and_records_monotonic_times():
    clock, transport, pacer = make([100 * MS], start=5 * S)
    record = pacer.execute(probe())
    assert (record.seq, record.start_ns, record.end_ns, record.status) == (1, 5 * S, 5 * S + 100 * MS, 200)
    assert pacer.earliest_start_ns() == 5 * S + 600 * MS


def test_minimum_spacing_between_starts_is_600_ms_even_for_instant_responses():
    clock, transport, pacer = make()
    for _ in range(5):
        pacer.execute(probe())
    gaps = [b - a for a, b in zip(transport.starts, transport.starts[1:])]
    assert gaps == [600 * MS] * 4


def test_next_request_waits_for_the_previous_completion_when_the_response_is_slow():
    clock, transport, pacer = make([2 * S, 100 * MS])
    first = pacer.execute(probe())
    assert pacer.earliest_start_ns() == first.end_ns == 2 * S                       # completion, not start + 0.6 s, governs
    second = pacer.execute(probe())
    assert first.end_ns == 2 * S and second.start_ns == 2 * S                       # not 0.6 s: completion-aware
    assert second.start_ns >= first.end_ns and second.start_ns - first.start_ns >= 600 * MS


def test_slow_response_shifts_everything_later_and_never_catches_up():
    clock, transport, pacer = make([3 * S, 0, 0])
    pacer.execute(probe())
    pacer.execute(probe())
    third = pacer.execute(probe())
    assert transport.starts == [0, 3 * S, 3 * S + 600 * MS] and third.start_ns == 3 * S + 600 * MS


def test_target_deadline_delays_the_first_request_of_a_group_but_never_advances_it():
    clock, transport, pacer = make()
    pacer.execute(probe())
    late = pacer.execute(probe(), target_ns=10 * S)
    early = pacer.execute(probe(), target_ns=0)
    assert late.start_ns == 10 * S and early.start_ns == 10 * S + 600 * MS
    assert pacer.clock.sleeps[-1] == 10 * S + 600 * MS


def test_wake_lateness_is_not_corrected():
    clock, transport, pacer = make()
    clock.wake_lateness_ns = 50 * MS
    pacer.execute(probe(), target_ns=10 * S)
    assert transport.starts == [10 * S + 50 * MS]


def test_one_second_cap_is_never_exceeded_and_spacing_dominates():
    clock, transport, pacer = make()
    for _ in range(12):
        pacer.execute(probe())
    starts = [r.start_ns for r in pacer.records]
    assert max(window_count(starts, t, 1 * S) for t in starts) == 2
    assert audit_all(pacer.records).ok


def test_sixty_second_cap_binds_exactly_sixty_seconds_after_the_oldest_start():
    # GV-8 (iii): 60 starts spaced 0.6 s end at 35.4 s; the 61st may start exactly 60 s after the first, not at 36.0 s.
    clock, transport, pacer = make()
    for _ in range(60):
        pacer.execute(probe())
    assert [r.start_ns for r in pacer.records][-1] == 59 * 600 * MS
    assert pacer.earliest_start_ns() == 60 * S
    sixty_first = pacer.execute(probe())
    assert sixty_first.start_ns == 60_000_000_000
    assert audit_all(pacer.records).ok
    starts = [r.start_ns for r in pacer.records]
    assert window_count(starts, 60 * S, 60 * S) == 60                              # the start at 0 left the window (open left)


def test_release_function_is_open_left_closed_right():
    starts = [k * S for k in range(60)]                                             # one per second
    assert release_ns(starts, ((60 * S, 60),)) == 60 * S                            # 61st at exactly 60 s is allowed
    assert release_ns(starts[:59], ((60 * S, 60),)) == 0                             # only 59 so far: no wait
    assert release_ns([0, 600 * MS], ((1 * S, 2),)) == 1 * S                         # third start allowed 1 s after the first
    assert window_count([0, 600 * MS, 1 * S], 1 * S, 1 * S) == 2                    # the start at 0 is excluded from (0, 1 s]
    assert window_count([0, 600 * MS, 999_999_999], 999_999_999, 1 * S) == 3        # included: 999,999,999 ns after it


def test_timed_out_and_failed_attempts_count_in_the_windows():
    results = [TransportResult(None, CONNECT_ERROR)] * 2 + [TransportResult(200, None, {}, b"[]")] * 60
    clock, transport, pacer = make(results=results)
    for _ in range(2):
        pacer.execute(probe())
    for _ in range(58):
        pacer.execute(probe())
    assert pacer.earliest_start_ns() == 60 * S                                      # 60 starts, failures included


def test_three_consecutive_requests_without_a_response_abort_the_run():
    results = [TransportResult(None, CONNECT_ERROR), TransportResult(None, DEADLINE), TransportResult(None, CONNECT_ERROR)]
    clock, transport, pacer = make([0, 17 * S, 0], results=results)
    pacer.execute(probe())
    pacer.execute(probe())
    with pytest.raises(NetworkIncident):
        pacer.execute(probe())
    assert pacer.abort_reason == "INCIDENT-NETWORK" and pacer.abort_seq == 3
    with pytest.raises(PacerAborted):
        pacer.execute(probe())
    assert len(transport.sent) == 3                                                # nothing is sent after the abort


def test_an_http_response_resets_the_no_response_streak():
    results = [TransportResult(None, CONNECT_ERROR), TransportResult(None, CONNECT_ERROR), TransportResult(200, None, {}, b"{}"),
               TransportResult(None, CONNECT_ERROR), TransportResult(None, CONNECT_ERROR)]
    clock, transport, pacer = make(results=results)
    for _ in range(5):
        pacer.execute(probe())
    assert pacer.abort_reason is None and len(pacer.records) == 5


def test_explicit_abort_blocks_further_requests():
    clock, transport, pacer = make()
    pacer.execute(probe())
    pacer.abort("INCIDENT")
    pacer.abort("OTHER")                                                            # the first reason is kept
    assert pacer.abort_reason == "INCIDENT" and pacer.abort_seq == 1
    with pytest.raises(PacerAborted):
        pacer.execute(probe())
    assert audit_all(pacer.records, abort_seq=pacer.abort_seq).ok


def test_unsafe_requests_are_refused_before_anything_is_sent():
    clock, transport, pacer = make()
    from dataclasses import replace
    good = klines_request(symbol="BTCUSDT", interval="5m", start_ms=0, end_ms=299_999, limit=1, role="K5m")
    cases = [
        replace(good, path="/api/v3/exchangeInfo"),
        replace(good, path="/api/v3/depth"),
        replace(good, params=good.params + (("extra", 1),)),
        replace(good, params=good.params[:-1]),
        replace(good, params=(("symbol", "btcusdt"),) + good.params[1:]),
        replace(good, params=(("symbol", "BTCUSDT"), ("interval", "1d")) + good.params[2:]),
        replace(good, params=good.params[:2] + (("startTime", True),) + good.params[3:]),
        replace(good, params=good.params[:4] + (("limit", 1001),)),
        RequestSpec("/api/v3/time", (("x", 1),), role="T"),
    ]
    for spec in cases:
        with pytest.raises(UnsafeRequest):
            pacer.execute(spec)
    assert transport.sent == [] and pacer.records == []
    pacer.execute(good)
    assert len(transport.sent) == 1


def test_obs01_profile_uses_two_second_spacing_and_thirty_per_minute():
    clock, transport, pacer = make(profile=OBS01_PROFILE)
    for _ in range(31):
        pacer.execute(probe())
    starts = [r.start_ns for r in pacer.records]
    assert starts[:3] == [0, 2 * S, 4 * S]
    assert starts[30] == 60 * S                                                     # the 31st waits for the 30/min window
    assert audit_all(pacer.records, profile=OBS01_PROFILE).ok


def test_earliest_possible_start_is_never_before_now():
    clock, transport, pacer = make([MS])
    pacer.execute(probe())
    clock.now = 10 * S
    assert pacer.earliest_possible_start_ns() == 10 * S
    clock.now = 0
    assert pacer.earliest_possible_start_ns() == 600 * MS


# ---------------- single flight (finding 1) ----------------
class BlockingTransport:
    """Blocks inside send() until released, so a second execute() can be attempted while the first is in flight."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.disabled = None

    def disable(self, reason):
        self.disabled = reason

    def send(self, spec, *, deadline_at_ns):
        self.calls += 1
        self.entered.set()
        self.release.wait(5)
        return TransportResult(200, None, {}, b"[]")


def test_a_concurrent_execute_is_rejected_and_changes_nothing():
    transport = BlockingTransport()
    pacer = Pacer(FakeClock(), transport)
    first = {}
    worker = threading.Thread(target=lambda: first.setdefault("record", pacer.execute(probe())))
    worker.start()
    assert transport.entered.wait(2)
    with pytest.raises(ConcurrentExecution):
        pacer.execute(probe())                                        # rejected immediately, from another thread
    assert transport.calls == 1 and pacer.records == [] and pacer.abort_reason is None
    transport.release.set()
    worker.join(2)
    assert not worker.is_alive() and first["record"].seq == 1 and len(pacer.records) == 1
    assert pacer.execute(probe()).seq == 2                            # the guard was released: normal use continues


def test_a_reentrant_execute_from_inside_the_transport_is_rejected():
    outcome = {}

    class Reentrant:
        def send(self, spec, *, deadline_at_ns):
            try:
                pacer.execute(probe())
            except ConcurrentExecution:
                outcome["rejected"] = True
            return TransportResult(200, None, {}, b"[]")

    clock = FakeClock()
    pacer = Pacer(clock, Reentrant())
    pacer.execute(probe())
    assert outcome == {"rejected": True} and len(pacer.records) == 1


def test_many_threads_never_overlap_inside_the_transport():
    state = {"inside": 0, "max": 0, "ok": 0}
    guard = threading.Lock()

    class Probe:
        def send(self, spec, *, deadline_at_ns):
            with guard:
                state["inside"] += 1
                state["max"] = max(state["max"], state["inside"])
            time.sleep(0.002)
            with guard:
                state["inside"] -= 1
            return TransportResult(200, None, {}, b"[]")

    pacer = Pacer(FakeClock(), Probe())
    barrier = threading.Barrier(12)

    def hammer():
        barrier.wait()
        for _ in range(5):
            try:
                pacer.execute(probe())
                with guard:
                    state["ok"] += 1
            except ConcurrentExecution:
                pass

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert state["max"] == 1 and state["ok"] == len(pacer.records) >= 1
    assert [r.seq for r in pacer.records] == list(range(1, len(pacer.records) + 1))
    assert all(a.end_ns <= b.start_ns for a, b in zip(pacer.records, pacer.records[1:]))


# ---------------- every non-200 aborts (finding 2) ----------------
@pytest.mark.parametrize("status", [204, 301, 302, 400, 403, 404, 418, 429, 451, 500, 503])
def test_every_non_200_response_aborts_the_pacer_and_disables_the_transport(status):
    clock, transport, pacer = make(results=[TransportResult(status, None, {}, b"{}")])
    with pytest.raises(NonOkResponse) as raised:
        pacer.execute(probe())
    assert raised.value.record is pacer.records[0] and pacer.records[0].status == status
    assert pacer.abort_reason == f"HTTP-{status}" and pacer.abort_seq == 1
    assert transport.disabled == f"HTTP-{status}"
    # continuation attempts are refused at every level and nothing more is sent
    with pytest.raises(PacerAborted):
        pacer.execute(probe())
    with pytest.raises(RuntimeError):
        transport.send(probe(), deadline_at_ns=10**12)                 # bypassing the pacer is refused by the transport too
    assert len(transport.sent) == 1 and len(pacer.records) == 1
    assert audit_all(pacer.records, abort_seq=pacer.abort_seq).ok


def test_a_200_response_does_not_abort_and_only_the_first_abort_reason_is_kept():
    clock, transport, pacer = make(results=[TransportResult(200, None, {}, b"{}"), TransportResult(429, None, {}, b"{}")])
    pacer.execute(probe())
    assert pacer.abort_reason is None and transport.disabled is None
    with pytest.raises(NonOkResponse):
        pacer.execute(probe())
    pacer.abort("LATER")
    assert pacer.abort_reason == "HTTP-429" and pacer.abort_seq == 2 and transport.disabled == "HTTP-429"


# ---------------- start-anchored deadline (finding 4) ----------------
def test_the_deadline_passed_to_the_transport_is_start_ns_plus_17_seconds():
    clock, transport, pacer = make([0, 0], start=5 * S)
    first = pacer.execute(probe(), target_ns=9 * S)
    second = pacer.execute(probe())
    assert pacer.deadline_ns == 17 * S
    assert transport.deadlines[0] == 9 * S + 17 * S and transport.deadlines[1] == second.start_ns + 17 * S


def test_the_deadline_is_anchored_at_the_recorded_start_even_after_a_late_wake():
    clock, transport, pacer = make()
    clock.wake_lateness_ns = 250 * MS
    record = pacer.execute(probe(), target_ns=10 * S)
    assert record.start_ns == 10 * S + 250 * MS
    assert transport.deadlines == [record.start_ns + 17 * S]


def test_the_deadline_length_is_configurable_only_through_the_pacer():
    clock = FakeClock()
    transport = ScriptedTransport(clock, [])
    pacer = Pacer(clock, transport, deadline_ns=300 * MS)
    record = pacer.execute(probe())
    assert transport.deadlines == [record.start_ns + 300 * MS]


# ---------------- failed cancellation and unexpected transport errors ----------------
class FailingTransport:
    def __init__(self, error, clock=None, advance=0):
        self.error, self.clock, self.advance, self.disabled, self.calls = error, clock, advance, None, 0

    def disable(self, reason):
        self.disabled = reason

    def send(self, spec, *, deadline_at_ns):
        self.calls += 1
        if self.clock:
            self.clock.now += self.advance
        raise self.error


def test_a_failed_cancellation_is_recorded_aborts_the_run_and_disables_the_transport():
    clock = FakeClock()
    transport = FailingTransport(CancellationFailed("stuck"), clock, 18 * S)
    pacer = Pacer(clock, transport)
    with pytest.raises(CancellationFailed):
        pacer.execute(probe())
    record = pacer.records[0]
    assert (record.status, record.error, record.end_ns - record.start_ns) == (None, CANCEL_FAILED, 18 * S)
    assert pacer.abort_reason == "INCIDENT-CANCEL" and transport.disabled == "INCIDENT-CANCEL"
    with pytest.raises(PacerAborted):
        pacer.execute(probe())
    assert transport.calls == 1
    assert audit_all(pacer.records, abort_seq=pacer.abort_seq).ok


def test_an_unexpected_transport_exception_fails_closed():
    clock = FakeClock()
    transport = FailingTransport(KeyError("bug"))
    pacer = Pacer(clock, transport)
    with pytest.raises(KeyError):
        pacer.execute(probe())
    assert pacer.abort_reason == "TRANSPORT-EXCEPTION" and pacer.abort_seq == 0 and transport.disabled == "TRANSPORT-EXCEPTION"
    with pytest.raises(PacerAborted):
        pacer.execute(probe())
    assert transport.calls == 1
