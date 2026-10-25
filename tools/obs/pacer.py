"""Completion-aware single pacer (protocol v0.5, section 3: PACE-1, 2, 3, 4, 6, 8)."""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Protocol

from tools.obs.clock import Clock
from tools.obs.params import (MAX_CONSECUTIVE_NO_RESPONSE, OBS01_SPACING_NS, OBS01_WINDOWS, SPACING_NS, WINDOWS)
from tools.obs.specs import RequestSpec, validate_spec
from tools.obs.transport import TransportResult


class Transport(Protocol):
    def send(self, spec: RequestSpec) -> TransportResult: ...


class PacerAborted(RuntimeError):
    """The run was aborted; no further request may be sent."""


class NetworkIncident(RuntimeError):
    """INCIDENT-NETWORK: three consecutive requests without an HTTP response."""


@dataclass(frozen=True)
class PaceProfile:
    spacing_ns: int
    windows: tuple[tuple[int, int], ...]          # (window ns, max starts); open left, closed right


OBS02_PROFILE = PaceProfile(SPACING_NS, WINDOWS)
OBS01_PROFILE = PaceProfile(OBS01_SPACING_NS, OBS01_WINDOWS)


@dataclass(frozen=True)
class RequestRecord:
    seq: int
    role: str
    path: str
    start_ns: int
    end_ns: int
    status: int | None
    error: str | None
    group_name: str | None = None
    group_kind: str | None = None
    boundary_ms: int | None = None
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = ()


def release_ns(starts: list[int], windows: tuple[tuple[int, int], ...]) -> int:
    """Earliest start t such that every window (t - W, t] would hold at most `cap` starts INCLUDING the new one.

    Windows are open on the left: the cap-th most recent start leaves the window exactly W later.
    """
    earliest = 0
    for window_ns, cap in windows:
        if len(starts) >= cap:
            earliest = max(earliest, starts[-cap] + window_ns)
    return earliest


def window_count(starts: list[int], t_ns: int, window_ns: int) -> int:
    """Number of starts in (t - W, t] for a sorted list of starts."""
    return bisect.bisect_right(starts, t_ns) - bisect.bisect_right(starts, t_ns - window_ns)


class Pacer:
    """The only network egress. One request in flight; the next may start only after the previous one completed,
    at least `spacing` after its start, and when the rolling windows allow it. Never starts early, never catches up."""

    def __init__(self, clock: Clock, transport: Transport, *, profile: PaceProfile = OBS02_PROFILE) -> None:
        self.clock = clock
        self.transport = transport
        self.profile = profile
        self.records: list[RequestRecord] = []
        self.abort_reason: str | None = None
        self.abort_seq: int | None = None
        self._no_response_streak = 0

    # ----- scheduling -----
    def earliest_start_ns(self) -> int:
        """PACE-6: max(end(prev), start(prev) + spacing, release). 0 when nothing was sent yet."""
        if not self.records:
            return 0
        last = self.records[-1]
        starts = [record.start_ns for record in self.records]
        return max(last.end_ns, last.start_ns + self.profile.spacing_ns, release_ns(starts, self.profile.windows))

    def earliest_possible_start_ns(self) -> int:
        """m_e of PACE-7: the earliest instant a request could start if issued now."""
        return max(self.clock.now_ns(), self.earliest_start_ns())

    def abort(self, reason: str) -> None:
        if self.abort_reason is None:
            self.abort_reason = reason
            self.abort_seq = len(self.records)

    # ----- execution -----
    def execute(self, spec: RequestSpec, *, target_ns: int | None = None) -> RequestRecord:
        if self.abort_reason is not None:
            raise PacerAborted(self.abort_reason)
        validate_spec(spec)                                       # refused before any socket is opened
        start_at = max(self.earliest_start_ns(), target_ns or 0)
        while self.clock.now_ns() < start_at:
            self.clock.sleep_until_ns(start_at)
        start_ns = self.clock.now_ns()
        result = self.transport.send(spec)
        end_ns = self.clock.now_ns()
        record = RequestRecord(seq=len(self.records) + 1, role=spec.role, path=spec.path, start_ns=start_ns, end_ns=end_ns,
                               status=result.status, error=result.error, group_name=spec.group_name, group_kind=spec.group_kind,
                               boundary_ms=spec.boundary_ms, body=result.body, headers=tuple(sorted(result.headers.items())))
        self.records.append(record)
        if result.status is None:
            self._no_response_streak += 1
            if self._no_response_streak >= MAX_CONSECUTIVE_NO_RESPONSE:
                self.abort("INCIDENT-NETWORK")
                raise NetworkIncident("3 consecutive requests without an HTTP response")
        else:
            self._no_response_streak = 0
        return record
