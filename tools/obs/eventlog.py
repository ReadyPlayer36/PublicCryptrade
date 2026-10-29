"""Tamper-evident event log binding decision and timeline timestamps to the recorded request stream.

The pacer (runner) appends one DECISION event per skip decision and one terminal TIMELINE_END event. Every event carries
  * the number of request records completed when it was logged (`records_before`) and a SHA-256 digest of exactly those
    records (`records_digest`), which structurally ties the event to the evidence stream;
  * `prev_hash` / `entry_hash`: a SHA-256 hash chain (canonical JSON), so editing, inserting, dropping or reordering any
    event breaks the chain.
The head digest of the chain is stored separately in the manifest. The audit trusts a timestamp only after
`verify_event_log` has rebuilt the chain, matched the manifest head digest and matched every record prefix; the result is a
`VerifiedEventLog`, which cannot be constructed outside this module's verifier.

Limits (stated, not hidden): this is tamper-EVIDENT, not tamper-PROOF. A party who controls the records, the log and the
manifest head at once can forge a consistent triple; the head digest must be recorded where the run's operator cannot rewrite
it after the fact (for example committed with the run manifest). Detecting accidental corruption, partial edits and
fabricated scalars is what this module guarantees.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

GENESIS = "0" * 64
EVENT_DECISION = "DECISION"
EVENT_TIMELINE_END = "TIMELINE_END"
_KINDS = (EVENT_DECISION, EVENT_TIMELINE_END)
_TOKEN = object()


class EventLogError(ValueError):
    """The event log failed verification; no timestamp in it may be trusted."""


@dataclass(frozen=True)
class LogEvent:
    index: int
    kind: str
    fields: tuple[tuple[str, int | str], ...]     # sorted (key, value) pairs; ints and strs only
    records_before: int
    records_digest: str
    prev_hash: str
    entry_hash: str

    def get(self, key: str) -> int | str | None:
        return dict(self.fields).get(key)


def records_digest(records: Sequence[object]) -> str:
    """SHA-256 over every evidence field of the records (body hashed), in seq order."""
    digest = hashlib.sha256()
    for r in records:
        line = json.dumps([r.seq, r.role, r.path, r.start_ns, r.end_ns, r.status, r.error, r.group_name, r.group_kind, r.boundary_ms,
                           hashlib.sha256(bytes(r.body)).hexdigest(), [list(h) for h in r.headers]],
                          separators=(",", ":"), sort_keys=True)
        digest.update(line.encode() + b"\n")
    return digest.hexdigest()


def _entry_hash(prev_hash: str, index: int, kind: str, fields: tuple, records_before: int, records_digest_hex: str) -> str:
    payload = json.dumps([prev_hash, index, kind, [list(f) for f in fields], records_before, records_digest_hex],
                         separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class EventLogWriter:
    """Runner-side recorder. `records` passed to each append must be the records completed at that instant."""

    def __init__(self) -> None:
        self._events: list[LogEvent] = []

    def _append(self, kind: str, fields: Mapping[str, int | str], records: Sequence[object]) -> LogEvent:
        if self._events and self._events[-1].kind == EVENT_TIMELINE_END:
            raise EventLogError("the timeline has ended; nothing may be appended")
        ordered = tuple(sorted(fields.items()))
        prev = self._events[-1].entry_hash if self._events else GENESIS
        digest = records_digest(records)
        event = LogEvent(len(self._events), kind, ordered, len(records), digest, prev,
                         _entry_hash(prev, len(self._events), kind, ordered, len(records), digest))
        self._events.append(event)
        return event

    def append_decision(self, *, boundary_ms: int, group_name: str, decided_at_ns: int, m_e_ns: int, records: Sequence[object]) -> LogEvent:
        return self._append(EVENT_DECISION, {"boundary_ms": boundary_ms, "group_name": group_name, "decided_at_ns": decided_at_ns,
                                             "m_e_ns": m_e_ns}, records)

    def append_timeline_end(self, *, timeline_end_ns: int, records: Sequence[object]) -> LogEvent:
        return self._append(EVENT_TIMELINE_END, {"timeline_end_ns": timeline_end_ns}, records)

    @property
    def events(self) -> tuple[LogEvent, ...]:
        return tuple(self._events)

    @property
    def head_digest(self) -> str:
        return self._events[-1].entry_hash if self._events else GENESIS


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class VerifiedEventLog:
    events: tuple[LogEvent, ...]
    _token: object = None

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise EventLogError("a VerifiedEventLog can only be produced by verify_event_log")

    def decision_event(self, boundary_ms: int, group_name: str) -> LogEvent | None:
        found = [e for e in self.events if e.kind == EVENT_DECISION and e.get("boundary_ms") == boundary_ms and e.get("group_name") == group_name]
        return found[0] if len(found) == 1 else None

    @property
    def timeline_end(self) -> LogEvent | None:
        return self.events[-1] if self.events and self.events[-1].kind == EVENT_TIMELINE_END else None


def verify_event_log(events: object, head_digest: object, records: Sequence[object]) -> VerifiedEventLog:
    """Verify structure, hash chain, manifest head digest and record-prefix binding. Raises EventLogError (fail closed)."""
    if not isinstance(head_digest, str) or len(head_digest) != 64:
        raise EventLogError("the manifest head digest is missing or malformed")
    if not isinstance(events, (list, tuple)) or any(type(e) is not LogEvent for e in events):
        raise EventLogError("the event log is missing or not a sequence of LogEvent entries")
    prev, seen_decisions, last_before = GENESIS, set(), 0
    for position, event in enumerate(events):
        if event.index != position:
            raise EventLogError(f"event {position}: index {event.index!r} breaks the sequence")
        if event.kind not in _KINDS:
            raise EventLogError(f"event {position}: unknown kind {event.kind!r}")
        if event.prev_hash != prev:
            raise EventLogError(f"event {position}: prev_hash does not link to the previous entry (tampered, dropped or reordered)")
        if event.entry_hash != _entry_hash(event.prev_hash, event.index, event.kind, event.fields, event.records_before, event.records_digest):
            raise EventLogError(f"event {position}: entry hash does not match its content (tampered)")
        if not all(_is_int(v) or isinstance(v, str) for _, v in event.fields):
            raise EventLogError(f"event {position}: field values must be ints or strings")
        if event.kind == EVENT_TIMELINE_END and position != len(events) - 1:
            raise EventLogError(f"event {position}: TIMELINE_END must be the final event")
        if event.kind == EVENT_DECISION:
            key = (event.get("boundary_ms"), event.get("group_name"))
            if key in seen_decisions:
                raise EventLogError(f"event {position}: duplicate decision for {key}")
            seen_decisions.add(key)
        if not _is_int(event.records_before) or not last_before <= event.records_before <= len(records):
            raise EventLogError(f"event {position}: records_before {event.records_before!r} is not a valid, non-decreasing record count")
        if event.records_digest != records_digest(records[: event.records_before]):
            raise EventLogError(f"event {position}: records digest does not match the recorded requests (log is not bound to this run)")
        last_before = event.records_before
        prev = event.entry_hash
    if prev != head_digest:
        raise EventLogError("the chain head does not match the manifest digest (truncated, extended or replaced log)")
    return VerifiedEventLog(tuple(events), _TOKEN)
