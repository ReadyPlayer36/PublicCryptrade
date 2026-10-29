"""Deterministic doubles for the OBS harness tests: a fake monotonic clock and a scripted transport."""
from __future__ import annotations

from tools.obs.specs import RequestSpec
from tools.obs.transport import TransportResult


class FakeClock:
    def __init__(self, start_ns: int = 0) -> None:
        self.now = start_ns
        self.sleeps: list[int] = []
        self.wake_lateness_ns = 0

    def now_ns(self) -> int:
        return self.now

    def sleep_until_ns(self, target_ns: int) -> None:
        self.sleeps.append(target_ns)
        if target_ns > self.now:
            self.now = target_ns + self.wake_lateness_ns


class ScriptedTransport:
    """Each send() advances the clock by the next scripted duration and returns the next scripted result."""

    def __init__(self, clock: FakeClock, durations_ns, results=None) -> None:
        self.clock = clock
        self.durations = list(durations_ns)
        self.results = list(results) if results is not None else None
        self.sent: list[RequestSpec] = []
        self.starts: list[int] = []
        self.deadlines: list[int] = []
        self.disabled: str | None = None

    def disable(self, reason: str) -> None:
        if self.disabled is None:
            self.disabled = reason

    def send(self, spec: RequestSpec, *, deadline_at_ns: int) -> TransportResult:
        if self.disabled is not None:
            raise RuntimeError(f"transport disabled: {self.disabled}")
        self.sent.append(spec)
        self.starts.append(self.clock.now)
        self.deadlines.append(deadline_at_ns)
        duration = self.durations.pop(0) if self.durations else 0
        self.clock.now += duration
        if self.results:
            return self.results.pop(0)
        return TransportResult(200, None, {}, b"[]")


def recorded_events(records, skips=None, timeline_end_ns=10**15):
    """An HONEST recorder: what a runner would log. One DECISION event per skip (logged once the records completed by the
    decision instant exist) and, unless timeline_end_ns is None, the terminal TIMELINE_END event after the last record."""
    from tools.obs.eventlog import EventLogWriter
    writer = EventLogWriter()
    entries = []
    for (boundary, group), decision in (skips or {}).items():
        decided = getattr(decision, "decided_at_ns", None)
        done = len(records) if not isinstance(decided, int) or isinstance(decided, bool) else sum(1 for r in records if r.end_ns <= decided)
        entries.append((done, boundary, group, decision))
    for done, boundary, group, decision in sorted(entries, key=lambda e: e[0]):
        writer.append_decision(boundary_ms=boundary, group_name=group, decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns,
                               records=records[:done])
    if timeline_end_ns is not None:
        writer.append_timeline_end(timeline_end_ns=timeline_end_ns, records=records)
    return writer.events, writer.head_digest


def verified_log_for(records, skips=None, timeline_end_ns=10**15):
    from tools.obs.eventlog import verify_event_log
    events, head = recorded_events(records, skips, timeline_end_ns)
    return verify_event_log(events, head, records)


def audit_all(records, **kw):
    """audit_pace with the three egress counters supplied (they are required; tests pass the true number by default).
    Timestamps are never passed as scalars to the audit: `timeline_end_ns` here is a TEST CONVENIENCE that makes an honest
    recorder log it (None = no TIMELINE_END event); pass `event_log` / `event_log_head` to test a specific log."""
    from tools.obs.audit import audit_pace
    kw.setdefault("jsonl_count", len(records))
    kw.setdefault("wrapper_count", len(records))
    kw.setdefault("manifest_count", len(records))
    timeline_end_ns = kw.pop("timeline_end_ns", 10**15)           # an audited run end far after every record (tests of the bound pass their own)
    if "event_log" not in kw and "event_log_head" not in kw:
        events, head = recorded_events(records, kw.get("skips"), timeline_end_ns)
        if events:
            kw["event_log"], kw["event_log_head"] = events, head
    return audit_pace(records, **kw)
