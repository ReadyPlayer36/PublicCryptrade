"""PACE-5 post-run audit (protocol v0.5, section 3): from recorded monotonic timestamps only.

Any failure means INVALID-PACING (harness defect, run unusable). Pure function over the request records.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tools.obs.pacer import OBS01_PROFILE, OBS02_PROFILE, PaceProfile, RequestRecord, window_count
from tools.obs.params import AUDIT_MAX_DURATION_NS, DEADLINE_NS
from tools.obs.transport import DEADLINE

ROLES_5M = ("S1", "K5m", "S2")
ROLES_4TF = ("S1", "K4h", "K1h", "K15m", "K5m", "S2")
GROUP_ORDER = ("resync", "g0", "g1", "g2", "g3", "ref")
RESYNC_COUNTS = range(3, 8)          # 3 resync calls plus up to 4 extra


@dataclass(frozen=True)
class AuditFailure:
    check: str                       # "a".."g"
    seq: int | None
    detail: str


@dataclass(frozen=True)
class AuditResult:
    failures: tuple[AuditFailure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures

    def checks(self) -> set[str]:
        return {failure.check for failure in self.failures}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def audit_pace(records: Sequence[RequestRecord], *, profile: PaceProfile = OBS02_PROFILE, abort_seq: int | None = None,
               jsonl_count: int | None = None, wrapper_count: int | None = None, manifest_count: int | None = None) -> AuditResult:
    failures: list[AuditFailure] = []

    def fail(check: str, seq: int | None, detail: str) -> None:
        failures.append(AuditFailure(check, seq, detail))

    # (a) integrity
    typed_ok = True
    for index, record in enumerate(records):
        if record.seq != index + 1:
            fail("a", record.seq, f"seq {record.seq!r} at position {index + 1}; sequence must be contiguous from 1")
        if not (_is_int(record.start_ns) and _is_int(record.end_ns) and _is_int(record.seq)):
            fail("a", record.seq, "timestamps and seq must be integers")
            typed_ok = False
            continue
        if record.end_ns < record.start_ns:
            fail("a", record.seq, "end before start (monotonic regression)")
        if index and _is_int(records[index - 1].start_ns) and record.start_ns < records[index - 1].start_ns:
            fail("a", record.seq, "start times must be non-decreasing in seq")
    if abort_seq is not None and len(records) > abort_seq:
        fail("a", abort_seq + 1, "record exists after an ABORT")
    if not typed_ok:
        return AuditResult(tuple(failures))
    starts = [record.start_ns for record in records]

    # (b) completion ordering and non-overlap, (c) spacing
    for prev, cur in zip(records, records[1:]):
        if prev.end_ns > cur.start_ns:
            fail("b", cur.seq, "request started before the previous one completed")
        if cur.start_ns - prev.start_ns < profile.spacing_ns:
            fail("c", cur.seq, f"start-to-start gap {cur.start_ns - prev.start_ns} ns below {profile.spacing_ns} ns")
    ends = [record.end_ns for record in records]
    if any(later < earlier for earlier, later in zip(ends, ends[1:])):
        fail("b", None, "completions are not in start order")

    # (d) rolling caps, windows (t - W, t] open left / closed right, integer nanoseconds
    for record in records:
        for window_ns, cap in profile.windows:
            count = window_count(starts, record.start_ns, window_ns)
            if count > cap:
                fail("d", record.seq, f"{count} starts in the {window_ns} ns window ending at this start (cap {cap})")

    # (e) durations (backstop for PACE-8)
    for record in records:
        duration = record.end_ns - record.start_ns
        if duration > AUDIT_MAX_DURATION_NS:
            fail("e", record.seq, f"duration {duration} ns exceeds {AUDIT_MAX_DURATION_NS} ns")
        if record.error == DEADLINE and not DEADLINE_NS <= duration <= AUDIT_MAX_DURATION_NS:
            fail("e", record.seq, f"deadline cancellation took {duration} ns, expected between {DEADLINE_NS} and {AUDIT_MAX_DURATION_NS}")

    # (f) group integrity
    _audit_groups(records, fail)

    # (g) egress counters
    for label, count in (("jsonl", jsonl_count), ("wrapper", wrapper_count), ("manifest", manifest_count)):
        if count is not None and count != len(records):
            fail("g", None, f"{label} count {count} != {len(records)} request records")
    return AuditResult(tuple(failures))


def _group_aborted(last: RequestRecord) -> bool:
    return last.status != 200


def _audit_groups(records: Sequence[RequestRecord], fail) -> None:
    last_boundary: int | None = None
    last_order = -1
    index = 0
    while index < len(records):
        record = records[index]
        if record.group_name is None:
            index += 1
            continue
        key = (record.boundary_ms, record.group_name)
        run = [record]
        j = index + 1
        while j < len(records) and (records[j].boundary_ms, records[j].group_name) == key:
            run.append(records[j])
            j += 1
        # the same group must not reappear later (a foreign request inside a group splits it)
        for later in records[j:]:
            if (later.boundary_ms, later.group_name) == key:
                fail("f", later.seq, f"group {key} is not consecutive in seq")
                break
        roles = tuple(r.role for r in run)
        kind = run[0].group_kind
        name = record.group_name
        if name == "resync":
            short_abort = _group_aborted(run[-1]) and len(roles) < 3
            if any(role != "T" for role in roles) or (len(roles) not in RESYNC_COUNTS and not short_abort):
                fail("f", record.seq, f"resync group has roles {roles}")
        elif name in GROUP_ORDER:
            expected = ROLES_4TF if kind == "4tf" else ROLES_5M if kind == "5m" else None
            if expected is None:
                fail("f", record.seq, f"group {name} has unknown kind {kind!r}")
            elif roles != expected and not (_group_aborted(run[-1]) and roles == expected[: len(roles)]):
                fail("f", record.seq, f"group {name} roles {roles} differ from {expected}")
        if record.boundary_ms is not None and name in GROUP_ORDER:
            order = GROUP_ORDER.index(name)
            if last_boundary is not None and record.boundary_ms < last_boundary:
                fail("f", record.seq, "boundaries are not in time order")
            elif record.boundary_ms == last_boundary and order < last_order:
                fail("f", record.seq, f"group {name} appears out of order within its boundary")
            last_boundary, last_order = record.boundary_ms, order
        index = j
