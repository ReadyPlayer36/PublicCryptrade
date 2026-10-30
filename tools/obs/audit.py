"""PACE-5 post-run audit (protocol v0.5, section 3), hardened to FAIL CLOSED.

From recorded monotonic timestamps and metadata only. Any failure means INVALID-PACING (harness defect or incident, run
unusable). Pure function over the request records. Checks:
 (a) integrity, including: nothing after an abort condition that the records themselves show (a non-200 response, three
     consecutive requests without a response, a failed cancellation) and consistency with the recorded abort position;
 (b) completion order and non-overlap; (c) spacing; (d) rolling caps (open left, closed right);
 (e) durations (17 s deadline backstop); (f) group metadata, role sequences and VERIFIED skipped groups;
 (g) egress counters: jsonl, wrapper and manifest counts are all REQUIRED and must equal the number of records.
"""
from __future__ import annotations

import collections.abc
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence

from tools.obs.admission import AdmissionDecision
from tools.obs.estimator import OffsetEstimator, TimeSample
from tools.obs.eventlog import EventLogError, VerifiedEventLog, records_digest, verify_event_log
from tools.obs.runstore import AuthenticatedManifest, ManifestError, ManifestTrustError, load_run, validate_and_snapshot_manifest
from tools.obs.pacer import OBS02_PROFILE, PaceProfile, RequestRecord, release_ns, window_count
from tools.obs.params import AUDIT_MAX_DURATION_NS, CANCEL_GRACE_NS, DEADLINE_NS, KLINES_PATH, MAX_CONSECUTIVE_NO_RESPONSE, MS, TIME_PATH
from tools.obs.transport import CANCEL_FAILED, DEADLINE

ROLES_5M = ("S1", "K5m", "S2")
ROLES_4TF = ("S1", "K4h", "K1h", "K15m", "K5m", "S2")
GROUP_ORDER = ("resync", "g0", "g1", "g2", "g3", "ref")
BOUNDARY_GROUPS = GROUP_ORDER[1:]
SYNC_GROUP = "sync"
RESYNC_COUNTS = range(3, 8)          # 3 resync calls plus up to 4 extra
MIN_SYNC_CALLS = 10
UNGROUPED_ROLES = ("SWEEP", "PREREG", "PROBE")
ROLE_PATH = {"T": TIME_PATH, "S1": TIME_PATH, "S2": TIME_PATH, "K4h": KLINES_PATH, "K1h": KLINES_PATH, "K15m": KLINES_PATH,
             "K5m": KLINES_PATH, "SWEEP": KLINES_PATH, "PREREG": KLINES_PATH, "PROBE": KLINES_PATH}
CANCEL_FAILED_MAX_NS = DEADLINE_NS + 2 * CANCEL_GRACE_NS     # start + deadline + cancellation allowance + scheduling slack
SKIP_MISSED_WINDOW = "MISSED-WINDOW"
# (nominal offset o, start tolerance tol) in milliseconds per group: the V1 window is [T + o, T + o + tol] (protocol section 5.1)
GROUP_WINDOWS_MS = {"g0": (0, 2500), "g1": (2000, 2500), "g2": (10_000, 2500), "g3": (60_000, 5000), "ref": (180_000, 5000)}
BOUNDARY_SKIP_SYNC = "SYNC-SKIPPED"


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


def _failed(record: RequestRecord) -> bool:
    return record.status != 200


def abort_condition_seq(records: Sequence[RequestRecord]) -> int | None:
    """Seq of the first record that must have ended the run, derived from the records themselves."""
    streak = 0
    for record in records:
        if record.status is not None and record.status != 200:
            return record.seq
        if record.error == CANCEL_FAILED:
            return record.seq
        if record.status is None:
            streak += 1
            if streak >= MAX_CONSECUTIVE_NO_RESPONSE:
                return record.seq
        else:
            streak = 0
    return None


def _safe_exception_text(exc: BaseException) -> str:
    """'<type>: <message>' without ever letting a broken or hostile exception (a __str__ that raises, returns a non-string,
    or a metaclass that breaks __name__) escape the normalisation boundary; falls back to fixed text. Bounded in length."""
    try:
        kind = str(type(exc).__name__)
    except Exception:                                                                 # noqa: BLE001
        kind = "exception"
    try:
        message = str(exc)
    except Exception:                                                                 # noqa: BLE001
        message = "<message unavailable>"
    return f"{kind}: {message}"[:300]


def audit_pace(records: Sequence[RequestRecord], *, profile: PaceProfile = OBS02_PROFILE, abort_seq: int | None = None,
               jsonl_count: int | None = None, wrapper_count: int | None = None, manifest_count: int | None = None,
               skips: Mapping[tuple[int, str], AdmissionDecision] | None = None,
               expected_boundaries: Sequence[int] | None = None,
               boundary_skips: Mapping[int, str] | None = None,
               event_log: Sequence[object] | None = None, manifest: AuthenticatedManifest | None = None) -> AuditResult:
    """`decided_at_ns` and the terminal `timeline_end_ns` are never accepted as bare scalars: they are trusted only when
    they match events of a hash-chained event log that verifies against the head digest of an AUTHENTICATED run manifest
    (tools.obs.runstore.load_manifest: pinned SHA-256, strict parse, self-digest; never a scalar) and against the records
    themselves (tools.obs.eventlog). A log without an authenticated manifest is rejected. An unverifiable log is a failure of check (a) and counts as no log."""
    # Freeze every caller-owned input ONCE, before anything is checked: the digest check, the event-log binding, the decision
    # matching and every traversal below read these immutable objects, never the caller's (possibly concurrently mutated)
    # list or mapping. RequestRecord is a frozen dataclass of immutable fields, so a tuple of them is a stable snapshot.
    # Snapshot construction runs caller-controlled code (iterators, __iter__, mapping access) and can itself raise if the caller
    # mutates a container while it is being copied. Any such failure is a controlled audit failure, never an escaping exception
    # (fail closed). Only Exception is caught: KeyboardInterrupt / SystemExit still propagate.
    try:
        name = "records"
        records = tuple(records)
        name = "skips"
        skips = None if skips is None else dict(skips)
        name = "expected_boundaries"
        expected_boundaries = None if expected_boundaries is None else tuple(expected_boundaries)
        name = "boundary_skips"
        boundary_skips = None if boundary_skips is None else dict(boundary_skips)
        name = "event_log"
        if event_log is not None:
            if not isinstance(event_log, collections.abc.Sequence):                   # list, tuple or any registered Sequence; nothing else
                raise TypeError("event_log must be a sequence of log events")
            event_log = tuple(event_log)                                              # after this, len()/indexing never touch caller code
    except Exception as exc:                                                          # noqa: BLE001 - deliberate fail-closed boundary
        return AuditResult((AuditFailure("a", None, f"input snapshot failed for {name}: {_safe_exception_text(exc)}"),))
    failures: list[AuditFailure] = []

    def fail(check: str, seq: int | None, detail: str) -> None:
        failures.append(AuditFailure(check, seq, detail))

    verified: VerifiedEventLog | None = None
    timeline_end_ns: int | None = None
    if event_log is not None or manifest is not None:
        try:
            try:
                snapshot = validate_and_snapshot_manifest(manifest)               # before any manifest attribute is used
            except ManifestTrustError as exc:
                raise EventLogError(str(exc)) from exc
            if snapshot.record_count != len(records) or snapshot.records_digest != records_digest(records):
                raise EventLogError("the records do not match the authenticated manifest (record count or digest)")
            if event_log is None or snapshot.event_count != len(event_log):
                raise EventLogError("the event log does not match the authenticated manifest event count")
            verified = verify_event_log(event_log, snapshot.event_log_head, records)
        except EventLogError as exc:
            fail("a", None, f"event log rejected: {exc}")
        else:
            end_event = verified.timeline_end
            if end_event is not None:
                timeline_end_ns = end_event.get("timeline_end_ns")
                if end_event.records_before != len(records):
                    fail("a", None, f"TIMELINE_END was logged after {end_event.records_before} records but {len(records)} exist")
                    timeline_end_ns = None

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
    if not typed_ok:
        return AuditResult(tuple(failures))
    if timeline_end_ns is not None:
        if not _is_int(timeline_end_ns):
            fail("a", None, "timeline_end_ns must be an integer")
        elif records and timeline_end_ns < records[-1].end_ns:
            fail("a", None, f"timeline_end_ns {timeline_end_ns} precedes the last record's completion ({records[-1].end_ns})")
    derived = abort_condition_seq(records)
    if derived is not None and len(records) > derived:
        fail("a", derived + 1, f"record exists after the abort condition at seq {derived} (non-200, 3 failures in a row, or failed cancellation)")
    if derived is not None and abort_seq != derived:
        fail("a", derived, f"the records show an abort at seq {derived} but the recorded abort position is {abort_seq!r}")
    if derived is None and abort_seq is not None and abort_seq != len(records):
        fail("a", abort_seq, f"abort recorded at position {abort_seq} but {len(records)} records exist")
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

    # (e) durations (backstop for PACE-8; the deadline is anchored at start_ns)
    for record in records:
        duration = record.end_ns - record.start_ns
        if record.error == CANCEL_FAILED:
            if not DEADLINE_NS <= duration <= CANCEL_FAILED_MAX_NS:
                fail("e", record.seq, f"failed cancellation lasted {duration} ns, expected between {DEADLINE_NS} and {CANCEL_FAILED_MAX_NS}")
            continue
        if duration > AUDIT_MAX_DURATION_NS:
            fail("e", record.seq, f"duration {duration} ns exceeds {AUDIT_MAX_DURATION_NS} ns")
        if record.error == DEADLINE and not DEADLINE_NS <= duration <= AUDIT_MAX_DURATION_NS:
            fail("e", record.seq, f"deadline cancellation took {duration} ns, expected between {DEADLINE_NS} and {AUDIT_MAX_DURATION_NS}")

    # (f) group metadata, group integrity, verified skips
    usable_end = timeline_end_ns if _is_int(timeline_end_ns) and (not records or timeline_end_ns >= records[-1].end_ns) else None   # a bad bound is no bound
    _audit_groups(records, skips or {}, expected_boundaries, boundary_skips or {}, derived, abort_seq, profile, usable_end, fail, verified)

    # (g) egress counters: all three are required
    for label, count in (("jsonl", jsonl_count), ("wrapper", wrapper_count), ("manifest", manifest_count)):
        if count is None:
            fail("g", None, f"{label} count was not supplied; it must be verified")
        elif not _is_int(count):
            fail("g", None, f"{label} count {count!r} is not an integer")
        elif count != len(records):
            fail("g", None, f"{label} count {count} != {len(records)} request records")
    return AuditResult(tuple(failures))


def _number(value: object) -> Fraction | None:
    """An exact number (int or Fraction, never bool/float/str), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        return None
    return Fraction(value)


def validate_missed_window_decision(decision: object, *, boundary_ms: int, group_name: str, previous_end_ns: int | None) -> list[str]:
    """Return every inconsistency of a MISSED-WINDOW admission decision (empty list = the decision is internally and externally
    consistent). Exact arithmetic; nothing is trusted from the decision object:
      * exact class, `admitted` is False, reason is MISSED-WINDOW;
      * every number is an exact int or Fraction (no bool, float, str);
      * `lower_server_ns == m_e_ns + theta_lo` and `upper_server_ns == m_e_ns + theta_hi` EXACTLY, and `theta_lo <= theta_hi`;
      * `limit_ns == (T + o + tol) * 1e6` recomputed from the boundary and the group's own window (not the decision's claim);
      * the strict skip inequality `lower_server_ns > limit_ns` (equality is NOT a skip);
      * `m_e_ns` is a non-negative integer not earlier than the completion of the preceding request of that boundary.
    """
    if type(decision) is not AdmissionDecision:
        return ["not an AdmissionDecision"]
    problems: list[str] = []
    if decision.admitted is not False:
        problems.append("admitted must be exactly False")
    if decision.reason != SKIP_MISSED_WINDOW:
        problems.append(f"reason must be {SKIP_MISSED_WINDOW}")
    values = {name: _number(getattr(decision, name)) for name in ("m_e_ns", "theta_lo", "theta_hi", "lower_server_ns", "upper_server_ns", "limit_ns")}
    for name, value in values.items():
        if value is None:
            problems.append(f"{name} is not an exact number")
    if problems and any(v is None for v in values.values()):
        return problems
    m_e, theta_lo, theta_hi = values["m_e_ns"], values["theta_lo"], values["theta_hi"]
    lower, upper, limit = values["lower_server_ns"], values["upper_server_ns"], values["limit_ns"]
    if not _is_int(decision.m_e_ns) or decision.m_e_ns < 0:
        problems.append("m_e_ns must be a non-negative integer")
    if not _is_int(decision.limit_ns):
        problems.append("limit_ns must be an integer")
    if not _is_int(decision.decided_at_ns) or decision.decided_at_ns < 0:
        problems.append("decided_at_ns must be a recorded non-negative integer decision timestamp")
    elif _is_int(decision.m_e_ns) and decision.decided_at_ns > decision.m_e_ns:
        problems.append("decided_at_ns is later than m_e_ns (the earliest start cannot precede the decision)")
    if theta_lo > theta_hi:
        problems.append("theta_lo exceeds theta_hi")
    if lower != m_e + theta_lo:
        problems.append("lower_server_ns != m_e_ns + theta_lo")
    if upper != m_e + theta_hi:
        problems.append("upper_server_ns != m_e_ns + theta_hi")
    window = GROUP_WINDOWS_MS.get(group_name)
    if window is None:
        problems.append(f"group {group_name!r} has no admission window")
    elif limit != (boundary_ms + window[0] + window[1]) * MS:
        problems.append(f"limit_ns != (T + o + tol) for boundary {boundary_ms} and group {group_name}")
    if not lower > limit:
        problems.append("the strict skip inequality lower_server_ns > limit_ns does not hold")
    if previous_end_ns is None:
        problems.append("no preceding request to anchor m_e_ns")
    elif m_e < previous_end_ns:
        problems.append("m_e_ns is earlier than the completion of the preceding request")
    return problems


def server_time_from_body(body: object) -> int | None:
    """The integer `serverTime` of a recorded /api/v3/time body, or None when the body is not usable."""
    if not isinstance(body, (bytes, bytearray)):
        return None
    try:
        payload = json.loads(bytes(body))
    except (ValueError, UnicodeDecodeError):
        return None
    value = payload.get("serverTime") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def time_samples_before(records: Sequence[RequestRecord], m_e_ns: int) -> tuple[list[TimeSample], list[str]]:
    """The estimator inputs implied by the RECORDS: every /api/v3/time request that completed (end_ns <= m_e) with HTTP 200.
    A 200 whose body has no usable serverTime is reported (fail closed); requests without a response give no sample."""
    samples: list[TimeSample] = []
    problems: list[str] = []
    for record in records:
        if record.path != TIME_PATH or record.status != 200 or not _is_int(record.end_ns) or record.end_ns > m_e_ns:
            continue
        server_ms = server_time_from_body(record.body)
        if server_ms is None:
            problems.append(f"/time record seq {record.seq} has no usable serverTime body")
            continue
        try:
            samples.append(TimeSample(record.start_ns, record.end_ns, server_ms))
        except (TypeError, ValueError):
            problems.append(f"/time record seq {record.seq} cannot form an estimator sample")
    return samples, problems


def validate_decision_evidence(decision: AdmissionDecision, records: Sequence[RequestRecord], *, previous_record: RequestRecord,
                               profile: PaceProfile, verified_log: VerifiedEventLog | None, boundary_ms: int, group_name: str) -> list[str]:
    """Tie an admission decision to the recorded evidence instead of trusting its arithmetic.
      * theta: the estimator (the approved implementation: exact rationals, drift widening from the request start, retention by
        completion time, 60 s fallback after an empty intersection) is re-run on the /time responses recorded before `m_e_ns`,
        and its theta_lo / theta_hi must equal the decision's claims EXACTLY;
      * decision time: the recorded `decided_at_ns` must lie between the completion of the preceding request and an AUDITED
        UPPER BOUND: the start of the next recorded request, or, for a terminal skip (nothing was sent afterwards), the audited
        `timeline_end_ns` of the run. A terminal skip with no such bound is rejected: its decision time would be unbounded;
      * provenance: `decided_at_ns` and m_e_ns must equal the fields of the ONE recorded DECISION event for (boundary, group) in
        a verified, hash-chained event log, logged right after the preceding request completed (records_before ==
        previous_record.seq); the terminal upper bound is that log's TIMELINE_END event, never a caller-supplied scalar. A
        missing log, a missing event or any mismatch fails, however consistent the arithmetic is;
      * m_e_ns is exactly max(decided_at_ns, earliest pacer start), the earliest start being recomputed from the records
        (completion, spacing, rolling caps) as the pacer computes it.
    The decision must already have passed `validate_missed_window_decision` (so its numbers are exact and consistent)."""
    problems: list[str] = []
    m_e = decision.m_e_ns
    decided = decision.decided_at_ns
    timeline_end_ns: int | None = None
    if not isinstance(verified_log, VerifiedEventLog):
        problems.append("decided_at_ns is not bound to recorded evidence: no verified event log was supplied")
    else:
        event = verified_log.decision_event(boundary_ms, group_name)
        if event is None:
            problems.append(f"no recorded DECISION event for ({boundary_ms}, {group_name}): decided_at_ns {decided} is unrecorded")
        else:
            if event.get("decided_at_ns") != decided:
                problems.append(f"decided_at_ns {decided} does not match the recorded decision event ({event.get('decided_at_ns')})")
            if event.get("m_e_ns") != m_e:
                problems.append(f"m_e_ns {m_e} does not match the recorded decision event ({event.get('m_e_ns')})")
            if event.records_before != previous_record.seq:
                problems.append(f"the decision was recorded after {event.records_before} records, not right after record {previous_record.seq}")
        end_event = verified_log.timeline_end
        if end_event is not None and end_event.records_before == len(records):
            candidate = end_event.get("timeline_end_ns")
            if _is_int(candidate) and (not records or candidate >= records[-1].end_ns):
                timeline_end_ns = candidate
    prefix = list(records[: previous_record.seq])
    starts = [record.start_ns for record in prefix]
    earliest = max(previous_record.end_ns, previous_record.start_ns + profile.spacing_ns, release_ns(starts, profile.windows))
    following = records[previous_record.seq] if previous_record.seq < len(records) else None
    if following is not None:
        upper, upper_name = following.start_ns, "the start of the next recorded request"
    else:
        upper, upper_name = timeline_end_ns, "the audited timeline end"
    if upper is None:
        problems.append("terminal skip: no recorded TIMELINE_END event bounds the run, so the decision time is unbounded")
    elif decided > upper:
        problems.append(f"decided_at_ns {decided} is later than {upper_name} ({upper})")
    if decided < previous_record.end_ns:
        problems.append(f"decided_at_ns {decided} precedes the completion of the preceding request ({previous_record.end_ns})")
    expected = max(decided, earliest)
    if m_e < earliest:
        problems.append(f"m_e_ns {m_e} is earlier than the earliest start the pacer rules allow after the preceding request ({earliest})")
    elif m_e < decided:
        problems.append(f"m_e_ns {m_e} precedes decided_at_ns {decided}")
    elif m_e > expected:
        problems.append(f"m_e_ns {m_e} is later than max(decided_at_ns, earliest pacer start) = {expected}")
    samples, sample_problems = time_samples_before(records, m_e)
    problems.extend(sample_problems)
    estimator = OffsetEstimator()
    for sample in samples:
        estimator.add(sample)
    estimate = estimator.estimate(m_e)
    if estimate is None:
        problems.append("the recorded /time evidence yields no offset estimate at m_e_ns")
        return problems
    if Fraction(decision.theta_lo) != estimate.lo:
        problems.append(f"theta_lo {decision.theta_lo} does not match the evidence ({estimate.lo})")
    if Fraction(decision.theta_hi) != estimate.hi:
        problems.append(f"theta_hi {decision.theta_hi} does not match the evidence ({estimate.hi})")
    return problems


def _record_metadata_ok(record: RequestRecord, fail) -> bool:
    ok = True
    expected_path = ROLE_PATH.get(record.role)
    if expected_path is None:
        fail("f", record.seq, f"unknown role {record.role!r}")
        return False
    if record.path != expected_path:
        fail("f", record.seq, f"role {record.role} must use {expected_path}, not {record.path!r}")
        ok = False
    name, kind, boundary = record.group_name, record.group_kind, record.boundary_ms
    if name is None:
        if record.role not in UNGROUPED_ROLES or kind is not None:
            fail("f", record.seq, f"ungrouped record with role {record.role!r} / kind {kind!r}")
            ok = False
    elif name == SYNC_GROUP:
        if record.role != "T" or kind is not None or boundary is not None:
            fail("f", record.seq, "sync records must be /time calls with no kind and no boundary")
            ok = False
    elif name in GROUP_ORDER:
        if not _is_int(boundary):
            fail("f", record.seq, f"group {name} requires an integer boundary")
            ok = False
        if name == "resync":
            if record.role != "T" or kind is not None:
                fail("f", record.seq, "resync records must be /time calls with no kind")
                ok = False
        elif kind not in ("5m", "4tf"):
            fail("f", record.seq, f"group {name} has unknown kind {kind!r}")
            ok = False
    else:
        fail("f", record.seq, f"unknown group name {name!r}")
        ok = False
    return ok


def _audit_groups(records, skips, expected_boundaries, boundary_skips, derived, abort_seq, profile, timeline_end_ns, fail, verified_log=None) -> None:
    meta_ok = [_record_metadata_ok(record, fail) for record in records]
    aborted = derived is not None or abort_seq is not None
    last_boundary: int | None = None
    last_order = -1
    runs: list[tuple[tuple, list[RequestRecord]]] = []
    index = 0
    while index < len(records):
        record = records[index]
        if record.group_name is None or not meta_ok[index]:
            index += 1
            continue
        key = (record.boundary_ms, record.group_name)
        run = [record]
        j = index + 1
        while j < len(records) and (records[j].boundary_ms, records[j].group_name) == key:
            run.append(records[j])
            j += 1
        for later in records[j:]:
            if (later.boundary_ms, later.group_name) == key:
                fail("f", later.seq, f"group {key} is not consecutive in seq")
                break
        runs.append((key, run))
        index = j

    seen_boundary_group = False
    for key, run in runs:
        boundary, name = key
        first = run[0]
        roles = tuple(r.role for r in run)
        if len({r.group_kind for r in run}) != 1:
            fail("f", first.seq, f"group {key} mixes group kinds")
        failed_tail = _failed(run[-1])
        if name == SYNC_GROUP:
            if seen_boundary_group:
                fail("f", first.seq, "the initial sync group must precede every boundary group")
            if any(role != "T" for role in roles) or (len(roles) < MIN_SYNC_CALLS and not failed_tail):
                fail("f", first.seq, f"sync group has {len(roles)} calls, expected at least {MIN_SYNC_CALLS}")
            continue
        seen_boundary_group = True
        if name == "resync":
            if any(role != "T" for role in roles) or (len(roles) not in RESYNC_COUNTS and not (failed_tail and len(roles) < 3)):
                fail("f", first.seq, f"resync group has roles {roles}")
        else:
            expected = ROLES_4TF if first.group_kind == "4tf" else ROLES_5M
            if roles != expected and not (failed_tail and roles == expected[: len(roles)]):
                fail("f", first.seq, f"group {name} roles {roles} differ from {expected}")
        order = GROUP_ORDER.index(name)
        if last_boundary is not None and boundary < last_boundary:
            fail("f", first.seq, "boundaries are not in time order")
        elif boundary == last_boundary and order < last_order:
            fail("f", first.seq, f"group {name} appears out of order within its boundary")
        last_boundary, last_order = boundary, order

    # verified skipped groups, per boundary
    by_boundary: dict[int, dict[str, list[RequestRecord]]] = {}
    for (boundary, name), run in runs:
        if name in GROUP_ORDER:
            by_boundary.setdefault(boundary, {})[name] = run
    last_record_seq = records[-1].seq if records else None
    for boundary, groups in by_boundary.items():
        present = [name for name in GROUP_ORDER if name in groups]
        if "resync" not in groups:
            fail("f", groups[present[0]][0].seq, f"boundary {boundary} has groups but no resync group")
        covered = False                       # a verified MISSED-WINDOW decision also covers the rest of the boundary (nothing is sent after it)
        for position, name in enumerate(GROUP_ORDER):
            if name in groups or name == "resync":
                continue
            later_present = [n for n in GROUP_ORDER[position + 1:] if n in groups]
            earlier_present = [n for n in GROUP_ORDER[:position] if n in groups]
            decision = skips.get((boundary, name))
            if decision is not None:
                previous = groups[earlier_present[-1]][-1] if earlier_present else None
                problems = validate_missed_window_decision(decision, boundary_ms=boundary, group_name=name,
                                                           previous_end_ns=previous.end_ns if previous is not None else None)
                if not problems and previous is not None:
                    problems = validate_decision_evidence(decision, records, previous_record=previous, profile=profile, verified_log=verified_log,
                                                          boundary_ms=boundary, group_name=name)
                if problems:
                    fail("f", None, f"skip evidence for ({boundary}, {name}) is not a consistent MISSED-WINDOW decision: " + "; ".join(problems))
                elif later_present:
                    fail("f", groups[later_present[0]][0].seq, f"group {later_present[0]} was sent after {name} was skipped (rest of the boundary must not be sent)")
                else:
                    covered = True
                continue
            if covered:
                continue
            if later_present:
                fail("f", groups[later_present[0]][0].seq, f"group {name} of boundary {boundary} is missing without verified skip evidence")
                continue
            # trailing absence: justified by a failed last request of the last present group, or by an abort at the end of the records
            last_group = groups[earlier_present[-1]] if earlier_present else None
            justified = last_group is not None and (_failed(last_group[-1]) or (aborted and last_group[-1].seq == last_record_seq))
            if not justified:
                fail("f", last_group[-1].seq if last_group else None, f"group {name} of boundary {boundary} is missing without verified skip evidence")
        for (b, name) in skips:
            if b == boundary and name in groups:
                fail("f", groups[name][0].seq, f"group {name} of boundary {boundary} has skip evidence but was sent")

    # skip evidence must refer to a recorded boundary and a real, skippable group
    for (b, name) in skips:
        if b not in by_boundary or name not in BOUNDARY_GROUPS:
            fail("f", None, f"skip evidence ({b!r}, {name!r}) refers to an unknown boundary or group")

    # whole-boundary expectations
    if expected_boundaries is not None:
        recorded = set(by_boundary)
        for boundary in expected_boundaries:
            reason = boundary_skips.get(boundary)
            if boundary in recorded and reason is not None:
                fail("f", None, f"boundary {boundary} has records but is declared skipped")
            elif boundary not in recorded and reason != BOUNDARY_SKIP_SYNC:
                fail("f", None, f"boundary {boundary} has no records and no verified skip reason")
        for boundary in recorded - set(expected_boundaries):
            fail("f", None, f"boundary {boundary} was sent but is not an expected boundary")


def audit_run(run_dir, *, pinned_manifest_sha256: object, wrapper_count: int | None = None, **kwargs) -> AuditResult:
    """Audit a persisted run end to end: records, event log and manifest are loaded from `run_dir`; the manifest is
    authenticated against the out-of-band `pinned_manifest_sha256`. Any load or authentication failure is an audit failure
    (check a), never an exception. The jsonl and manifest counts come from the persisted files; the wrapper count must be
    supplied by the caller (it is an independent egress counter)."""
    try:
        run = load_run(run_dir, pinned_manifest_sha256=pinned_manifest_sha256)
    except ManifestError as exc:
        return AuditResult((AuditFailure("a", None, f"run rejected: {exc}"),))
    kwargs.setdefault("jsonl_count", len(run.records))
    try:
        snapshot = validate_and_snapshot_manifest(run.manifest)
    except ManifestTrustError as exc:
        return AuditResult((AuditFailure("a", None, f"run rejected: {exc}"),))
    kwargs.setdefault("manifest_count", snapshot.record_count)
    return audit_pace(run.records, event_log=run.events, manifest=run.manifest, wrapper_count=wrapper_count, **kwargs)
