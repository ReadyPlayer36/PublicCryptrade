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
`ManifestError` (fail closed). No key material of any kind is used or stored.

Limit (stated, not hidden): authentication is exactly as independent as the pinned digest. Whoever can rewrite the run
directory AND the place the digest is pinned can forge a consistent run.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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


@dataclass(frozen=True)
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
    return AuthenticatedManifest(data["record_count"], data["records_file_sha256"], data["records_digest"], data["event_count"],
                                 data["events_file_sha256"], data["event_log_head"], _sha256(raw), _TOKEN)


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


def load_run(run_dir: str | os.PathLike, *, pinned_manifest_sha256: object) -> LoadedRun:
    """Load records, events and the authenticated manifest from disk; every file must match the manifest."""
    directory = Path(run_dir)
    manifest = load_manifest(directory / MANIFEST_FILE, pinned_sha256=pinned_manifest_sha256)
    records_raw, events_raw = _read(directory / RECORDS_FILE, "records.jsonl"), _read(directory / EVENTS_FILE, "events.jsonl")
    if _sha256(records_raw) != manifest.records_file_sha256:
        raise ManifestError("records.jsonl does not match the manifest digest (altered or substituted)")
    if _sha256(events_raw) != manifest.events_file_sha256:
        raise ManifestError("events.jsonl does not match the manifest digest (altered or substituted log)")
    records = []
    for obj in _jsonl(records_raw, "records.jsonl", _RECORD_KEYS):
        try:
            body = base64.b64decode(obj["body_b64"], validate=True)
            headers = tuple((str(a), str(b)) for a, b in obj["headers"])
        except (ValueError, TypeError) as exc:
            raise ManifestError(f"records.jsonl: invalid body or headers: {exc}") from exc
        records.append(RequestRecord(obj["seq"], obj["role"], obj["path"], obj["start_ns"], obj["end_ns"], obj["status"], obj["error"],
                                     obj["group_name"], obj["group_kind"], obj["boundary_ms"], body, headers))
    events = []
    for obj in _jsonl(events_raw, "events.jsonl", _EVENT_KEYS):
        try:
            fields = tuple((str(k), v) for k, v in obj["fields"])
        except (ValueError, TypeError) as exc:
            raise ManifestError(f"events.jsonl: invalid fields: {exc}") from exc
        events.append(LogEvent(obj["index"], obj["kind"], fields, obj["records_before"], obj["records_digest"], obj["prev_hash"], obj["entry_hash"]))
    if len(records) != manifest.record_count or len(events) != manifest.event_count:
        raise ManifestError("record or event count does not match the manifest")
    return LoadedRun(tuple(records), tuple(events), manifest)
