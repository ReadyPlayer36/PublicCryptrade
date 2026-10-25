"""Completion-aware pacer (PACE-1, 2, 3, 4, 6): spacing, completion-before-start, rolling caps, targets, incident rule."""
import pytest

from tests.fixtures.obs_fakes import FakeClock, ScriptedTransport
from tools.obs.audit import audit_pace
from tools.obs.pacer import OBS01_PROFILE, Pacer, PacerAborted, NetworkIncident, release_ns, window_count
from tools.obs.params import MS, S
from tools.obs.specs import RequestSpec, UnsafeRequest, klines_request, time_request
from tools.obs.transport import CONNECT_ERROR, DEADLINE, TransportResult


def make(durations=(), results=None, profile=None, start=0):
    clock = FakeClock(start)
    transport = ScriptedTransport(clock, durations, results)
    kwargs = {} if profile is None else {"profile": profile}
    return clock, transport, Pacer(clock, transport, **kwargs)


def test_first_request_starts_immediately_and_records_monotonic_times():
    clock, transport, pacer = make([100 * MS], start=5 * S)
    record = pacer.execute(time_request(role="T"))
    assert (record.seq, record.start_ns, record.end_ns, record.status) == (1, 5 * S, 5 * S + 100 * MS, 200)
    assert pacer.earliest_start_ns() == 5 * S + 600 * MS


def test_minimum_spacing_between_starts_is_600_ms_even_for_instant_responses():
    clock, transport, pacer = make()
    for _ in range(5):
        pacer.execute(time_request(role="T"))
    gaps = [b - a for a, b in zip(transport.starts, transport.starts[1:])]
    assert gaps == [600 * MS] * 4


def test_next_request_waits_for_the_previous_completion_when_the_response_is_slow():
    clock, transport, pacer = make([2 * S, 100 * MS])
    first = pacer.execute(time_request(role="T"))
    assert pacer.earliest_start_ns() == first.end_ns == 2 * S                       # completion, not start + 0.6 s, governs
    second = pacer.execute(time_request(role="T"))
    assert first.end_ns == 2 * S and second.start_ns == 2 * S                       # not 0.6 s: completion-aware
    assert second.start_ns >= first.end_ns and second.start_ns - first.start_ns >= 600 * MS


def test_slow_response_shifts_everything_later_and_never_catches_up():
    clock, transport, pacer = make([3 * S, 0, 0])
    pacer.execute(time_request(role="T"))
    pacer.execute(time_request(role="T"))
    third = pacer.execute(time_request(role="T"))
    assert transport.starts == [0, 3 * S, 3 * S + 600 * MS] and third.start_ns == 3 * S + 600 * MS


def test_target_deadline_delays_the_first_request_of_a_group_but_never_advances_it():
    clock, transport, pacer = make()
    pacer.execute(time_request(role="T"))
    late = pacer.execute(time_request(role="T"), target_ns=10 * S)
    early = pacer.execute(time_request(role="T"), target_ns=0)
    assert late.start_ns == 10 * S and early.start_ns == 10 * S + 600 * MS
    assert pacer.clock.sleeps[-1] == 10 * S + 600 * MS


def test_wake_lateness_is_not_corrected():
    clock, transport, pacer = make()
    clock.wake_lateness_ns = 50 * MS
    pacer.execute(time_request(role="T"), target_ns=10 * S)
    assert transport.starts == [10 * S + 50 * MS]


def test_one_second_cap_is_never_exceeded_and_spacing_dominates():
    clock, transport, pacer = make()
    for _ in range(12):
        pacer.execute(time_request(role="T"))
    starts = [r.start_ns for r in pacer.records]
    assert max(window_count(starts, t, 1 * S) for t in starts) == 2
    assert audit_pace(pacer.records).ok


def test_sixty_second_cap_binds_exactly_sixty_seconds_after_the_oldest_start():
    # GV-8 (iii): 60 starts spaced 0.6 s end at 35.4 s; the 61st may start exactly 60 s after the first, not at 36.0 s.
    clock, transport, pacer = make()
    for _ in range(60):
        pacer.execute(time_request(role="T"))
    assert [r.start_ns for r in pacer.records][-1] == 59 * 600 * MS
    assert pacer.earliest_start_ns() == 60 * S
    sixty_first = pacer.execute(time_request(role="T"))
    assert sixty_first.start_ns == 60_000_000_000
    assert audit_pace(pacer.records).ok
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
        pacer.execute(time_request(role="T"))
    for _ in range(58):
        pacer.execute(time_request(role="T"))
    assert pacer.earliest_start_ns() == 60 * S                                      # 60 starts, failures included


def test_three_consecutive_requests_without_a_response_abort_the_run():
    results = [TransportResult(None, CONNECT_ERROR), TransportResult(None, DEADLINE), TransportResult(None, CONNECT_ERROR)]
    clock, transport, pacer = make([0, 17 * S, 0], results=results)
    pacer.execute(time_request(role="T"))
    pacer.execute(time_request(role="T"))
    with pytest.raises(NetworkIncident):
        pacer.execute(time_request(role="T"))
    assert pacer.abort_reason == "INCIDENT-NETWORK" and pacer.abort_seq == 3
    with pytest.raises(PacerAborted):
        pacer.execute(time_request(role="T"))
    assert len(transport.sent) == 3                                                # nothing is sent after the abort


def test_an_http_response_resets_the_no_response_streak():
    results = [TransportResult(None, CONNECT_ERROR), TransportResult(None, CONNECT_ERROR), TransportResult(200, None, {}, b"{}"),
               TransportResult(None, CONNECT_ERROR), TransportResult(None, CONNECT_ERROR)]
    clock, transport, pacer = make(results=results)
    for _ in range(5):
        pacer.execute(time_request(role="T"))
    assert pacer.abort_reason is None and len(pacer.records) == 5


def test_explicit_abort_blocks_further_requests():
    clock, transport, pacer = make()
    pacer.execute(time_request(role="T"))
    pacer.abort("INCIDENT")
    pacer.abort("OTHER")                                                            # the first reason is kept
    assert pacer.abort_reason == "INCIDENT" and pacer.abort_seq == 1
    with pytest.raises(PacerAborted):
        pacer.execute(time_request(role="T"))
    assert audit_pace(pacer.records, abort_seq=pacer.abort_seq).ok


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
        pacer.execute(time_request(role="T"))
    starts = [r.start_ns for r in pacer.records]
    assert starts[:3] == [0, 2 * S, 4 * S]
    assert starts[30] == 60 * S                                                     # the 31st waits for the 30/min window
    assert audit_pace(pacer.records, profile=OBS01_PROFILE).ok


def test_earliest_possible_start_is_never_before_now():
    clock, transport, pacer = make([MS])
    pacer.execute(time_request(role="T"))
    clock.now = 10 * S
    assert pacer.earliest_possible_start_ns() == 10 * S
    clock.now = 0
    assert pacer.earliest_possible_start_ns() == 600 * MS
