"""Persisted run artifacts and the authenticated run manifest.

A run directory holds exactly three files, written once (never overwritten):
  records.jsonl   one canonical JSON object per request record (body base64)
  events.jsonl    one canonical JSON object per event-log entry (tools.obs.eventlog)
  manifest.json   format, counts, SHA-256 of both files, the records digest, the event-log head digest and a
                  self-digest over all of those fields

The audit never receives the head digest as a scalar. It receives an `AuthenticatedManifest`, which can only be produced by
`load_manifest`: the manifest file's bytes must match a SHA-256 PINNED OUT OF BAND (recorded where the run operator cannot
rewrite it after the run: a committed evidence file, a ticket, a signed release note), the JSON must be strict (no duplicate
keys, exact key set, exact types), and the self-digest must verify. Anything missing, malformed or mismatching raises
`ManifestError` (fail closed). Provenance is by identity: `is_loader_issued` is True only for the instances load_manifest
minted (a weak registry), so dataclasses.replace() / object.__new__ forgeries are rejected. Persisted records and events are
validated strictly (no coercion; booleans, floats and wrong shapes are rejected). No key material of any kind is used or stored.

Limit (stated, not hidden): authentication is exactly as independent as the pinned digest. Whoever can rewrite the run
directory AND the place the digest is pinned can forge a consistent run.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from tools.obs.eventlog import EventLogError, LogEvent, GENESIS, records_digest, verify_event_log
from tools.obs.pacer import RequestRecord

FORMAT = "obs-run-manifest/1"
RECORDS_FILE, EVENTS_FILE, MANIFEST_FILE = "records.jsonl", "events.jsonl", "manifest.json"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TOKEN = object()
_MANIFEST_KEYS = {"format", "record_count", "records_file_sha256", "records_digest", "event_count", "events_file_sha256",
                  "event_log_head", "manifest_digest"}
_RECORD_KEYS = {"seq", "role", "path", "start_ns", "end_ns", "status", "error", "group_name", "group_kind", "boundary_ms", "body_b64", "headers"}
_EVENT_KEYS = {"index", "kind", "fields", "records_before", "records_digest", "prev_hash", "entry_hash"}


class ManifestError(ValueError):
    """The run manifest or a persisted run artifact is missing, malformed or fails authentication."""


# Process-level registry of manifests minted by load_manifest. A frozen dataclass can be copied with dataclasses.replace()
# (which re-passes every init field, the private token included) or built with object.__new__, so neither the token nor
# isinstance() proves provenance. Membership here does: eq=False makes the instances hash and compare BY IDENTITY, so a copy
# that merely has equal field values is not a member.
_ISSUED: "weakref.WeakSet[AuthenticatedManifest]" = weakref.WeakSet()


@dataclass(frozen=True, eq=False)
class AuthenticatedManifest:
    record_count: int
    records_file_sha256: str
    records_digest: str
    event_count: int
    events_file_sha256: str
    event_log_head: str
    manifest_sha256: str                       # SHA-256 of the manifest file bytes (equals the pinned digest)
    _token: object = None

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise ManifestError("an AuthenticatedManifest can only be produced by load_manifest")


# Off-instance seal. Identity membership alone does not stop `object.__setattr__(genuine, "event_log_head", ...)`, which
# mutates a loader-issued instance in place. At issue the loader records, OUTSIDE the instance, a SHA-256 over the canonical
# values of every authenticated field; the audit gate recomputes it from the instance's current values, so any in-place
# change (or deletion) of a trusted field is detected before the manifest is used.
_TRUSTED_FIELDS = ("record_count", "records_file_sha256", "records_digest", "event_count", "events_file_sha256", "event_log_head", "manifest_sha256")
_SEALS: "weakref.WeakKeyDictionary[AuthenticatedManifest, str]" = weakref.WeakKeyDictionary()
_NOT_SUPPLIED = "no authenticated run manifest was supplied (the head digest must come from load_manifest)"
_MUTATED = "the manifest's authenticated fields were mutated in place after issue (object.__setattr__ tampering)"


def _trusted_seal(candidate: object) -> str:
    """SHA-256 over the canonical current values of _TRUSTED_FIELDS. A missing attribute or a value that cannot be
    canonically encoded yields a value that never equals an issued seal (the caller treats the error as mutation)."""
    try:
        values = [[name, getattr(candidate, name)] for name in _TRUSTED_FIELDS]
        return _sha256(_canonical(values).encode())
    except (AttributeError, TypeError, ValueError):
        return "unsealable"


def _register(manifest: "AuthenticatedManifest") -> None:
    _ISSUED.add(manifest)
    _SEALS[manifest] = _trusted_seal(manifest)


def manifest_trust_error(candidate: object) -> str | None:
    """None when `candidate` is a genuine, unmodified loader-issued manifest; otherwise the reason it is not trusted. The
    type and identity checks read no attribute of the candidate; the seal check reads only the authenticated fields."""
    if type(candidate) is not AuthenticatedManifest:
        return _NOT_SUPPLIED
    try:
        issued = candidate in _ISSUED
    except TypeError:
        issued = False
    if not issued:
        return _NOT_SUPPLIED
    if _SEALS.get(candidate) != _trusted_seal(candidate):
        return _MUTATED
    return None


def is_loader_issued(candidate: object) -> bool:
    """True only for the exact instance objects minted by load_manifest whose authenticated fields are unchanged since issue
    (copies, replace() results, object.__new__ instances, subclasses, non-manifests and in-place-mutated instances are False)."""
    return manifest_trust_error(candidate) is None


@dataclass(frozen=True)
class LoadedRun:
    records: tuple[RequestRecord, ...]
    events: tuple[LogEvent, ...]
    manifest: AuthenticatedManifest


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_self_digest(fields: dict) -> str:
    return _sha256(_canonical({k: v for k, v in fields.items() if k != "manifest_digest"}).encode())


def _no_duplicate_keys(pairs: list) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ManifestError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _parse_json(raw: bytes, what: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys, parse_constant=lambda c: (_ for _ in ()).throw(ManifestError(f"{what}: {c} is not allowed")))
    except ManifestError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{what} is not valid JSON: {exc}") from exc


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def record_to_json(r: RequestRecord) -> dict:
    return {"seq": r.seq, "role": r.role, "path": r.path, "start_ns": r.start_ns, "end_ns": r.end_ns, "status": r.status, "error": r.error,
            "group_name": r.group_name, "group_kind": r.group_kind, "boundary_ms": r.boundary_ms,
            "body_b64": base64.b64encode(bytes(r.body)).decode("ascii"), "headers": [list(h) for h in r.headers]}


def event_to_json(e: LogEvent) -> dict:
    return {"index": e.index, "kind": e.kind, "fields": [list(f) for f in e.fields], "records_before": e.records_before,
            "records_digest": e.records_digest, "prev_hash": e.prev_hash, "entry_hash": e.entry_hash}


def _lines(objs: Sequence[dict]) -> bytes:
    return b"".join(_canonical(o).encode() + b"\n" for o in objs)


def write_run(run_dir: str | os.PathLike, records: Sequence[RequestRecord], events: Sequence[LogEvent]) -> str:
    """Persist records, events and the manifest (each file written once, never overwritten). Returns the SHA-256 of
    manifest.json: the value to PIN out of band. Refuses to persist a log that does not verify against the records."""
    head = events[-1].entry_hash if events else GENESIS
    try:
        verify_event_log(list(events), head, records)
    except EventLogError as exc:
        raise ManifestError(f"refusing to persist an inconsistent run: {exc}") from exc
    records_bytes = _lines([record_to_json(r) for r in records])
    events_bytes = _lines([event_to_json(e) for e in events])
    fields = {"format": FORMAT, "record_count": len(records), "records_file_sha256": _sha256(records_bytes), "records_digest": records_digest(records),
              "event_count": len(events), "events_file_sha256": _sha256(events_bytes), "event_log_head": head}
    fields["manifest_digest"] = _manifest_self_digest(fields)
    manifest_bytes = (_canonical(fields) + "\n").encode()
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in ((RECORDS_FILE, records_bytes), (EVENTS_FILE, events_bytes), (MANIFEST_FILE, manifest_bytes)):
        try:
            with open(directory / name, "xb") as handle:
                handle.write(data)
        except FileExistsError as exc:
            raise ManifestError(f"{name} already exists; run artifacts are written once") from exc
    return _sha256(manifest_bytes)


def _read(path: Path, what: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"{what} is missing or unreadable: {path.name}") from exc


def load_manifest(path: str | os.PathLike, *, pinned_sha256: object) -> AuthenticatedManifest:
    """Authenticate a persisted manifest against an out-of-band pinned SHA-256 (fail closed)."""
    if not isinstance(pinned_sha256, str) or not _HEX64.fullmatch(pinned_sha256):
        raise ManifestError("the pinned manifest SHA-256 is missing or malformed (64 lowercase hex characters required)")
    raw = _read(Path(path), "the run manifest")
    if _sha256(raw) != pinned_sha256:
        raise ManifestError("the manifest does not match the pinned SHA-256 (tampered, substituted or stale manifest)")
    data = _parse_json(raw, "the manifest")
    if not isinstance(data, dict) or set(data) != _MANIFEST_KEYS:
        raise ManifestError("the manifest is malformed: unexpected or missing keys")
    if data["format"] != FORMAT:
        raise ManifestError(f"unsupported manifest format {data['format']!r}")
    for key in ("record_count", "event_count"):
        if not _is_int(data[key]) or data[key] < 0:
            raise ManifestError(f"the manifest field {key} must be a non-negative integer")
    for key in ("records_file_sha256", "records_digest", "events_file_sha256", "event_log_head", "manifest_digest"):
        if not isinstance(data[key], str) or not _HEX64.fullmatch(data[key]):
            raise ManifestError(f"the manifest field {key} must be 64 lowercase hex characters")
    if data["manifest_digest"] != _manifest_self_digest(data):
        raise ManifestError("the manifest self-digest does not verify (a field was edited)")
    manifest = AuthenticatedManifest(data["record_count"], data["records_file_sha256"], data["records_digest"], data["event_count"],
                                     data["events_file_sha256"], data["event_log_head"], _sha256(raw), _TOKEN)
    _register(manifest)
    return manifest


def _jsonl(raw: bytes, what: str, keys: set) -> list[dict]:
    if raw and not raw.endswith(b"\n"):
        raise ManifestError(f"{what} is truncated (no final newline)")
    out = []
    for number, line in enumerate(raw.split(b"\n")[:-1] if raw else [], 1):
        obj = _parse_json(line, f"{what} line {number}")
        if not isinstance(obj, dict) or set(obj) != keys:
            raise ManifestError(f"{what} line {number}: unexpected or missing keys")
        out.append(obj)
    return out


def _req_int(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ManifestError(f"{what} must be an integer, got {type(value).__name__}")
    return value


def _req_range(value: object, what: str, low: int, high: int) -> int:
    number = _req_int(value, what)
    if not low <= number <= high:
        raise ManifestError(f"{what} {number} is outside [{low}, {high}]")
    return number


def _req_str(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"{what} must be a string, got {type(value).__name__}")
    return value


def _req_hex64(value: object, what: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ManifestError(f"{what} must be 64 lowercase hex characters")
    return value


def _opt(check, value: object, what: str, *args):
    return None if value is None else check(value, what, *args)


def _req_headers(value: object, what: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ManifestError(f"{what} must be a list of [name, value] pairs")
    pairs = []
    for position, pair in enumerate(value):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ManifestError(f"{what}[{position}] must be a two-element [name, value] list")
        pairs.append((_req_str(pair[0], f"{what}[{position}] name"), _req_str(pair[1], f"{what}[{position}] value")))
    return tuple(pairs)


def _req_fields(value: object, what: str) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(value, list):
        raise ManifestError(f"{what} must be a list of [key, value] pairs")
    pairs = []
    for position, pair in enumerate(value):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ManifestError(f"{what}[{position}] must be a two-element [key, value] list")
        item = pair[1]
        if not (isinstance(item, str) or _is_int(item)):
            raise ManifestError(f"{what}[{position}] value must be an integer or string, got {type(item).__name__}")
        pairs.append((_req_str(pair[0], f"{what}[{position}] key"), item))
    return tuple(pairs)


_I64 = 2**63 - 1


def _record_from_json(obj: dict, line: int) -> RequestRecord:
    tag = f"records.jsonl line {line}"
    try:
        body = base64.b64decode(_req_str(obj["body_b64"], f"{tag} body_b64"), validate=True)
    except ValueError as exc:
        raise ManifestError(f"{tag}: invalid body: {exc}") from exc
    return RequestRecord(
        _req_range(obj["seq"], f"{tag} seq", 0, _I64), _req_str(obj["role"], f"{tag} role"), _req_str(obj["path"], f"{tag} path"),
        _req_range(obj["start_ns"], f"{tag} start_ns", 0, _I64), _req_range(obj["end_ns"], f"{tag} end_ns", 0, _I64),
        _opt(_req_range, obj["status"], f"{tag} status", 100, 599), _opt(_req_str, obj["error"], f"{tag} error"),
        _opt(_req_str, obj["group_name"], f"{tag} group_name"), _opt(_req_str, obj["group_kind"], f"{tag} group_kind"),
        _opt(_req_range, obj["boundary_ms"], f"{tag} boundary_ms", 0, _I64), body, _req_headers(obj["headers"], f"{tag} headers"))


def _event_from_json(obj: dict, line: int) -> LogEvent:
    tag = f"events.jsonl line {line}"
    return LogEvent(
        _req_range(obj["index"], f"{tag} index", 0, _I64), _req_str(obj["kind"], f"{tag} kind"), _req_fields(obj["fields"], f"{tag} fields"),
        _req_range(obj["records_before"], f"{tag} records_before", 0, _I64), _req_hex64(obj["records_digest"], f"{tag} records_digest"),
        _req_hex64(obj["prev_hash"], f"{tag} prev_hash"), _req_hex64(obj["entry_hash"], f"{tag} entry_hash"))


def load_run(run_dir: str | os.PathLike, *, pinned_manifest_sha256: object) -> LoadedRun:
    """Load records, events and the authenticated manifest from disk; every file must match the manifest."""
    directory = Path(run_dir)
    manifest = load_manifest(directory / MANIFEST_FILE, pinned_sha256=pinned_manifest_sha256)
    records_raw, events_raw = _read(directory / RECORDS_FILE, "records.jsonl"), _read(directory / EVENTS_FILE, "events.jsonl")
    if _sha256(records_raw) != manifest.records_file_sha256:
        raise ManifestError("records.jsonl does not match the manifest digest (altered or substituted)")
    if _sha256(events_raw) != manifest.events_file_sha256:
        raise ManifestError("events.jsonl does not match the manifest digest (altered or substituted log)")
    try:
        records = [_record_from_json(obj, n) for n, obj in enumerate(_jsonl(records_raw, "records.jsonl", _RECORD_KEYS), 1)]
        events = [_event_from_json(obj, n) for n, obj in enumerate(_jsonl(events_raw, "events.jsonl", _EVENT_KEYS), 1)]
    except ManifestError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:      # normalise anything unforeseen into the controlled error
        raise ManifestError(f"persisted run artifact is malformed: {exc!r}") from exc
    if len(records) != manifest.record_count or len(events) != manifest.event_count:
        raise ManifestError("record or event count does not match the manifest")
    return LoadedRun(tuple(records), tuple(events), manifest)
