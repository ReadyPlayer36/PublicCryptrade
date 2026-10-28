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


def audit_all(records, **kw):
    """audit_pace with the three egress counters supplied (they are required; tests pass the true number by default)."""
    from tools.obs.audit import audit_pace
    kw.setdefault("jsonl_count", len(records))
    kw.setdefault("wrapper_count", len(records))
    kw.setdefault("manifest_count", len(records))
    kw.setdefault("timeline_end_ns", 10**15)                      # an audited run end far after every record (tests of the bound pass their own)
    return audit_pace(records, **kw)
