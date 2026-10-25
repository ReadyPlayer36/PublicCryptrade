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

    def send(self, spec: RequestSpec) -> TransportResult:
        self.sent.append(spec)
        self.starts.append(self.clock.now)
        duration = self.durations.pop(0) if self.durations else 0
        self.clock.now += duration
        if self.results:
            return self.results.pop(0)
        return TransportResult(200, None, {}, b"[]")
