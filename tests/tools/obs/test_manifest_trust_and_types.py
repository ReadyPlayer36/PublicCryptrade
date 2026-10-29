"""Fix 7: (1) AuthenticatedManifest provenance is by identity, not by copyable fields; (2) persisted artifacts are validated
strictly, with no coercion. Offline and deterministic."""
import copy
import dataclasses
import json
from types import SimpleNamespace

import pytest

from tests.tools.obs.test_run_manifest_e2e import audit, build_run, rewrite_manifest, text
from tools.obs import runstore
from tools.obs.audit import audit_pace, audit_run
from tools.obs.runstore import AuthenticatedManifest, ManifestError, is_loader_issued, load_manifest, load_run


@pytest.fixture
def run(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    manifest = load_manifest(run_dir / runstore.MANIFEST_FILE, pinned_sha256=pin)
    return run_dir, pin, records, events, skips, manifest


def audit_with(records, events, skips, manifest):
    return audit_pace(records, jsonl_count=len(records), wrapper_count=len(records), manifest_count=len(records), skips=skips,
                      event_log=events, manifest=manifest)


# ---- 7.1: trust boundary ----
def test_only_the_instance_minted_by_the_loader_is_issued(run):
    *_, manifest = run
    assert is_loader_issued(manifest) is True


def forgeries(manifest):
    fields = {f.name: getattr(manifest, f.name) for f in dataclasses.fields(manifest)}
    raw = object.__new__(AuthenticatedManifest)                                        # bypasses __init__ and the token check entirely
    for name, value in fields.items():
        object.__setattr__(raw, name, value)

    class Sub(AuthenticatedManifest):
        pass

    sub = object.__new__(Sub)
    for name, value in fields.items():
        object.__setattr__(sub, name, value)
    return {
        "dataclasses.replace": dataclasses.replace(manifest),                           # re-passes every init field, token included
        "replace_with_change": dataclasses.replace(manifest, record_count=manifest.record_count),
        "object.__new__": raw,
        "subclass": sub,
        "copy.copy": copy.copy(manifest),
        "copy.deepcopy": copy.deepcopy(manifest),
        "namespace_lookalike": SimpleNamespace(**fields),
        "dict": fields,
        "none": None,
        "int": 7,
    }


@pytest.mark.parametrize("kind", ["dataclasses.replace", "replace_with_change", "object.__new__", "subclass", "copy.copy", "copy.deepcopy",
                                  "namespace_lookalike", "dict", "none", "int"])
def test_forged_or_copied_manifests_are_not_loader_issued_and_the_audit_rejects_them(run, kind):
    run_dir, pin, records, events, skips, manifest = run
    forged = forgeries(manifest)[kind]
    assert is_loader_issued(forged) is False
    result = audit_with(records, events, skips, forged)
    assert not result.ok and "no authenticated run manifest was supplied" in text(result)
    assert audit_with(records, events, skips, manifest).ok                              # the genuine instance still passes


def test_a_forged_manifest_carrying_a_matching_head_is_rejected_even_though_every_field_is_equal(run):
    run_dir, pin, records, events, skips, manifest = run
    twin = dataclasses.replace(manifest)
    assert (twin.event_log_head, twin.record_count, twin.records_digest, twin.event_count) == \
           (manifest.event_log_head, manifest.record_count, manifest.records_digest, manifest.event_count)
    assert twin is not manifest and not is_loader_issued(twin)                           # equal values, different identity: not issued


def test_the_check_happens_before_any_attribute_access(run):
    run_dir, pin, records, events, skips, manifest = run
    touched = []

    class Tripwire:
        def __getattribute__(self, name):
            touched.append(name)
            raise AssertionError(f"attribute {name} was read before the provenance check")

    assert is_loader_issued(Tripwire()) is False
    result = audit_with(records, events, skips, Tripwire())
    assert not result.ok and touched == []                                               # rejected without reading a single attribute


def test_every_load_mints_a_fresh_issued_instance_and_equal_loads_are_distinct_identities(run):
    run_dir, pin, records, events, skips, manifest = run
    again = load_manifest(run_dir / runstore.MANIFEST_FILE, pinned_sha256=pin)
    assert is_loader_issued(again) and again is not manifest
    assert is_loader_issued(manifest)


def test_audit_run_still_passes_end_to_end(run):
    run_dir, pin, records, events, skips, manifest = run
    assert audit(run_dir, pin, skips, records).ok
    assert not audit_run(run_dir, pinned_manifest_sha256="0" * 64, wrapper_count=len(records), skips=skips).ok


# ---- 7.2: strict persisted-artifact types ----
def edit_line(run_dir, filename, line_no, key, value):
    """Change one JSON field of one persisted line and re-pin everything, so ONLY the type validators can object."""
    path = run_dir / filename
    lines = path.read_bytes().splitlines()
    obj = json.loads(lines[line_no])
    obj[key] = value
    lines[line_no] = runstore._canonical(obj).encode()
    data = b"".join(line + b"\n" for line in lines)
    path.write_bytes(data)
    column = "records_file_sha256" if filename == runstore.RECORDS_FILE else "events_file_sha256"
    return rewrite_manifest(run_dir, **{column: runstore._sha256(data)})


RECORD_CASES = [
    ("seq", "1", "seq must be an integer"), ("seq", True, "seq must be an integer"), ("seq", 1.0, "seq must be an integer"),
    ("seq", -1, "outside"), ("seq", 10**30, "outside"), ("seq", None, "seq must be an integer"),
    ("start_ns", 1.5, "start_ns must be an integer"), ("start_ns", True, "start_ns must be an integer"), ("start_ns", "5", "start_ns must be an integer"),
    ("start_ns", -1, "outside"), ("end_ns", 2.0, "end_ns must be an integer"), ("end_ns", "5", "end_ns must be an integer"),
    ("status", True, "status must be an integer"), ("status", 200.0, "status must be an integer"), ("status", "200", "status must be an integer"),
    ("status", 99, "outside"), ("status", 600, "outside"),
    ("role", 5, "role must be a string"), ("path", None, "path must be a string"), ("error", 5, "error must be a string"),
    ("group_name", 3, "group_name must be a string"), ("group_kind", True, "group_kind must be a string"),
    ("boundary_ms", True, "boundary_ms must be an integer"), ("boundary_ms", 1.5, "boundary_ms must be an integer"), ("boundary_ms", "7", "boundary_ms must be an integer"),
    ("body_b64", 5, "body_b64 must be a string"), ("body_b64", "***", "invalid body"),
    ("headers", "x", "headers must be a list"), ("headers", {"a": "b"}, "headers must be a list"), ("headers", [["a"]], "two-element"),
    ("headers", [["a", "b", "c"]], "two-element"), ("headers", [["a", 1]], "value must be a string"), ("headers", [[1, "b"]], "name must be a string"),
    ("headers", [{"a": "b"}], "two-element"), ("headers", ["ab"], "two-element"), ("headers", [["a", None]], "value must be a string"),
]


@pytest.mark.parametrize("key,value,fragment", RECORD_CASES, ids=[f"{k}={v!r}" for k, v, _ in RECORD_CASES])
def test_a_wrongly_typed_record_field_is_rejected_without_coercion(tmp_path, key, value, fragment):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    new_pin = edit_line(run_dir, runstore.RECORDS_FILE, 0, key, value)
    with pytest.raises(ManifestError, match=fragment):
        load_run(run_dir, pinned_manifest_sha256=new_pin)
    result = audit(run_dir, new_pin, skips, records)
    assert not result.ok and "run rejected" in text(result)


EVENT_CASES = [
    ("index", True, "index must be an integer"), ("index", "0", "index must be an integer"), ("index", 0.0, "index must be an integer"),
    ("kind", 5, "kind must be a string"), ("kind", None, "kind must be a string"),
    ("fields", "x", "fields must be a list"), ("fields", [["k"]], "two-element"), ("fields", [["k", 1.5]], "integer or string"),
    ("fields", [["k", True]], "integer or string"), ("fields", [["k", None]], "integer or string"), ("fields", [[1, 2]], "key must be a string"),
    ("fields", [["k", [1]]], "integer or string"), ("fields", {"k": 1}, "fields must be a list"),
    ("records_before", True, "records_before must be an integer"), ("records_before", 1.5, "records_before must be an integer"),
    ("records_before", -1, "outside"), ("records_before", "2", "records_before must be an integer"),
    ("records_digest", 5, "64 lowercase hex"), ("records_digest", "G" * 64, "64 lowercase hex"), ("records_digest", "A" * 64, "64 lowercase hex"),
    ("prev_hash", "0" * 63, "64 lowercase hex"), ("prev_hash", None, "64 lowercase hex"), ("entry_hash", 7, "64 lowercase hex"),
]


@pytest.mark.parametrize("key,value,fragment", EVENT_CASES, ids=[f"{k}={v!r}" for k, v, _ in EVENT_CASES])
def test_a_wrongly_typed_event_field_is_rejected_without_coercion(tmp_path, key, value, fragment):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    new_pin = edit_line(run_dir, runstore.EVENTS_FILE, 0, key, value)
    with pytest.raises(ManifestError, match=fragment):
        load_run(run_dir, pinned_manifest_sha256=new_pin)
    result = audit(run_dir, new_pin, skips, records)
    assert not result.ok and "run rejected" in text(result)


def test_valid_artifacts_load_with_exact_types_and_no_coercion(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    loaded = load_run(run_dir, pinned_manifest_sha256=pin)
    for r in loaded.records:
        assert all(type(v) is int for v in (r.seq, r.start_ns, r.end_ns))
        assert type(r.headers) is tuple and all(type(h) is tuple and all(type(x) is str for x in h) for h in r.headers)
        assert type(r.body) is bytes
    for e in loaded.events:
        assert type(e.index) is int and type(e.records_before) is int
        assert all(type(k) is str and type(v) in (int, str) for k, v in e.fields)


def test_headers_with_content_survive_a_round_trip_exactly(tmp_path):
    from dataclasses import replace
    from tests.fixtures.obs_fakes import recorded_events
    from tests.tools.obs.test_audit import evidence_case
    records, decision, boundary = evidence_case("g2")
    records = [replace(records[0], headers=(("Retry-After", "5"), ("X-Mbx-Used-Weight", "12")), body=b"\x00\xffbody")] + records[1:]
    events, _ = recorded_events(records, {(boundary, "g2"): decision})
    pin = runstore.write_run(tmp_path / "hdr", records, events)
    loaded = load_run(tmp_path / "hdr", pinned_manifest_sha256=pin)
    assert loaded.records[0].headers == (("Retry-After", "5"), ("X-Mbx-Used-Weight", "12")) and loaded.records[0].body == b"\x00\xffbody"


# ---- Fix 7b: in-place mutation of a genuine, loader-issued manifest (object.__setattr__) ----
from tools.obs.eventlog import EventLogWriter
from tools.obs.runstore import _SEALS, _TRUSTED_FIELDS, manifest_trust_error

MUTATED = "mutated in place after issue"
NOT_SUPPLIED = "no authenticated run manifest was supplied"


def test_a_genuine_manifest_has_no_trust_error_and_its_seal_lives_off_the_instance(run):
    *_, manifest = run
    assert manifest_trust_error(manifest) is None and is_loader_issued(manifest)
    assert manifest in _SEALS and not any("seal" in name for name in vars(manifest))             # nothing on the instance to overwrite


@pytest.mark.parametrize("field", _TRUSTED_FIELDS)
def test_object_setattr_on_any_authenticated_field_is_detected(run, field):
    run_dir, pin, records, events, skips, manifest = run
    original = getattr(manifest, field)
    replacement = original + 1 if isinstance(original, int) else "f" * 64
    object.__setattr__(manifest, field, replacement)
    assert is_loader_issued(manifest) is False
    assert MUTATED in manifest_trust_error(manifest)
    result = audit_with(records, events, skips, manifest)
    assert not result.ok and MUTATED in text(result)


@pytest.mark.parametrize("replacement", [None, 1.5, True, b"bytes", object()])
def test_replacing_a_trusted_field_with_any_other_type_is_detected(run, replacement):
    run_dir, pin, records, events, skips, manifest = run
    object.__setattr__(manifest, "event_log_head", replacement)
    assert manifest_trust_error(manifest) is not None and MUTATED in manifest_trust_error(manifest)


def test_deleting_a_trusted_field_in_place_is_detected(run):
    run_dir, pin, records, events, skips, manifest = run
    object.__delattr__(manifest, "records_digest")
    assert MUTATED in manifest_trust_error(manifest)


def test_a_mutated_manifest_cannot_authenticate_a_fabricated_event_log(run):
    """The attack: build a different, internally valid log and point the genuine manifest's head at it in place."""
    run_dir, pin, records, events, skips, manifest = run
    fabricated = EventLogWriter()
    for event in events:
        if event.kind == "DECISION":
            fabricated.append_decision(boundary_ms=event.get("boundary_ms"), group_name=event.get("group_name"),
                                       decided_at_ns=event.get("decided_at_ns") + 1, m_e_ns=event.get("m_e_ns"), records=records[: event.records_before])
        else:
            fabricated.append_timeline_end(timeline_end_ns=event.get("timeline_end_ns"), records=records)
    control = audit_with(records, fabricated.events, skips, manifest)                              # unmutated: the head does not fit
    assert not control.ok and "manifest digest" in text(control)
    object.__setattr__(manifest, "event_log_head", fabricated.head_digest)                         # now the head fits the fabricated log ...
    object.__setattr__(manifest, "event_count", len(fabricated.events))
    result = audit_with(records, fabricated.events, skips, manifest)
    assert not result.ok and MUTATED in text(result)                                               # ... but the manifest is no longer trusted


def test_the_gate_runs_before_any_manifest_attribute_is_read(run):
    run_dir, pin, records, events, skips, manifest = run
    object.__setattr__(manifest, "record_count", 10**6)                                            # would otherwise trip the record-count check
    result = audit_with(records, events, skips, manifest)
    assert MUTATED in text(result) and "records do not match" not in text(result)


def test_forgeries_still_report_the_not_supplied_reason(run):
    run_dir, pin, records, events, skips, manifest = run
    for forged in (dataclasses.replace(manifest), None, 7, SimpleNamespace()):
        assert NOT_SUPPLIED in manifest_trust_error(forged)


def test_restoring_the_original_value_leaves_the_manifest_unchanged_and_trusted(run):
    run_dir, pin, records, events, skips, manifest = run
    original = manifest.event_count
    object.__setattr__(manifest, "event_count", original + 1)
    assert not is_loader_issued(manifest)
    object.__setattr__(manifest, "event_count", original)                                          # the seal covers VALUES: no net change
    assert is_loader_issued(manifest) and audit_with(records, events, skips, manifest).ok
