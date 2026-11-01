"""Deep immutability at the direct audit entry (F-01) and in event-log verification (F-02). Offline and deterministic.

A frozen dataclass only freezes its own attributes. These tests prove that mutable nested objects (bytearray bodies,
list headers, list event fields) are normalised or refused at the boundary, and that nothing the caller does AFTER the audit
has started can change what is audited."""
from dataclasses import FrozenInstanceError, dataclass, replace
from types import SimpleNamespace

import pytest

from tests.fixtures.obs_fakes import audit_all, authenticated_manifest, recorded_events
from tests.tools.obs.test_provenance import skip_case
from tools.obs import audit as audit_module
from tools.obs.eventlog import (EVENT_DECISION, EVENT_TIMELINE_END, GENESIS, EventLogError, LogEvent, _entry_hash, records_digest,
                                verify_event_log)
from tools.obs.pacer import RequestRecord

SNAPSHOT_FAILED = "input snapshot failed for records: TypeError: "
DECISION = (("boundary_ms", 1_700_000_100_000), ("decided_at_ns", 5), ("group_name", "g2"), ("m_e_ns", 4))
TL_END = (("timeline_end_ns", 10**15),)


def text(result):
    return " | ".join(f.detail for f in result.failures)


@pytest.fixture
def run():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    return records, skips, events, head


def body_index(records):
    return next(i for i, r in enumerate(records) if r.body)


def audit_hostile(hostile_records, run):
    """audit_pace on records that cannot be digested by the test helpers; the manifest is built from the GOOD records."""
    records, skips, events, head = run
    manifest = authenticated_manifest(records, events, head)
    return audit_module.audit_pace(hostile_records, skips=skips, event_log=events, manifest=manifest, jsonl_count=len(records),
                                   wrapper_count=len(records), manifest_count=len(records))


def with_record(records, index, **changes):
    changed = list(records)
    changed[index] = replace(records[index], **changes)
    return changed


# ------------------------------------------------------------------------------------------------ F-01 normalisation
@pytest.mark.parametrize("make", [bytearray, memoryview], ids=["bytearray", "memoryview"])
def test_a_mutable_body_is_normalised_to_bytes_and_the_audit_still_passes(make, run):
    records, skips, _, _ = run
    i = body_index(records)
    mutable = with_record(records, i, body=make(bytearray(records[i].body)))
    events, head = recorded_events(mutable, skips)
    assert audit_all(mutable, skips=skips, event_log=events, event_log_head=head).ok


@pytest.mark.parametrize("headers", [[["x-a", "1"], ["x-b", "2"]], (["x-a", "1"],), [("x-a", "1")], (("x-a", "1"),)],
                         ids=["list-of-lists", "tuple-of-lists", "list-of-tuples", "tuple-of-tuples"])
def test_list_headers_are_normalised_to_a_tuple_of_pairs_and_the_audit_still_passes(headers, run):
    records, skips, _, _ = run
    changed = with_record(records, 0, headers=headers)
    events, head = recorded_events(changed, skips)
    assert audit_all(changed, skips=skips, event_log=events, event_log_head=head).ok


def test_the_frozen_copy_is_a_distinct_deeply_immutable_record():
    original = RequestRecord(1, "time", "/api/v3/time", 1, 2, 200, None, body=bytearray(b"abc"), headers=[["k", "v"]])
    frozen = audit_module._freeze_record(original)
    assert frozen is not original and type(frozen.body) is bytes and frozen.body == b"abc"
    assert frozen.headers == (("k", "v"),) and type(frozen.headers) is tuple and type(frozen.headers[0]) is tuple
    original.body[:] = b"XYZ"
    original.headers[0][1] = "changed"
    assert frozen.body == b"abc" and frozen.headers == (("k", "v"),)
    with pytest.raises(FrozenInstanceError):
        frozen.body = b""
    with pytest.raises(TypeError):
        frozen.headers[0][1] = "x"


# ------------------------------------------------------------------------------------------------ F-01 post-entry mutation
def test_mutations_after_the_audit_has_started_cannot_reach_the_audited_data(monkeypatch, run):
    records, skips, _, _ = run
    i = body_index(records)
    body, headers = bytearray(records[i].body), [["k", "v"]]
    live = with_record(records, i, body=body, headers=headers)
    events, head = recorded_events(live, skips)
    real = audit_module.verify_event_log

    def hostile(event_log, head_digest, recs):
        body[:] = b"X" * len(body)                          # in-place bytearray edit
        headers[0][1] = "tampered"                          # inner list edit
        headers.append(["more", "x"])                       # outer list edit
        live.clear()                                        # the caller's records list emptied
        return real(event_log, head_digest, recs)

    monkeypatch.setattr(audit_module, "verify_event_log", hostile)
    result = audit_all(live, skips=skips, event_log=events, event_log_head=head)
    assert body == b"X" * len(body) and headers[0][1] == "tampered" and live == []        # control: the hostile edits really happened
    assert result.ok, text(result)


def test_without_the_snapshot_the_same_hostile_edit_would_have_been_detected_as_a_digest_change(run):
    records, skips, _, _ = run
    i = body_index(records)
    body = bytearray(records[i].body)
    live = with_record(records, i, body=body)
    before = records_digest(live)
    body[:] = b"X" * len(body)
    assert records_digest(live) != before                  # control: the edit is visible to the digest, so the snapshot matters


# ------------------------------------------------------------------------------------------------ F-01 rejection
class _Bytearray(bytearray):
    pass


class _Str(str):
    pass


@dataclass(frozen=True)
class _SubRecord(RequestRecord):
    pass


BODY_CASES = [("body str", "abc", "str"), ("body None", None, "NoneType"), ("body int", 5, "int"), ("body list", [1, 2], "list"),
              ("body bytearray subclass", _Bytearray(b"a"), "_Bytearray")]
HEADER_CASES = [("headers str", "ab", "headers must be a tuple or list of pairs, not str"),
                ("headers None", None, "headers must be a tuple or list of pairs, not NoneType"),
                ("headers dict", {"a": "b"}, "headers must be a tuple or list of pairs, not dict"),
                ("header triple", [("a", "b", "c")], "every header must be a (str, str) pair"),
                ("header single", [("a",)], "every header must be a (str, str) pair"),
                ("header str pair", ["ab"], "every header must be a (str, str) pair"),
                ("header int value", [("a", 1)], "every header must be a (str, str) pair"),
                ("header bytes name", [(b"a", "b")], "every header must be a (str, str) pair"),
                ("header str subclass", [("a", _Str("b"))], "every header must be a (str, str) pair")]


@pytest.mark.parametrize("name,value,kind", BODY_CASES, ids=[c[0] for c in BODY_CASES])
def test_an_unsupported_body_type_is_a_controlled_failure(name, value, kind, run):
    records = run[0]
    i = body_index(records)
    result = audit_hostile(with_record(records, i, body=value), run)
    expected = f"{SNAPSHOT_FAILED}record {records[i].seq}: body must be bytes, bytearray or memoryview, not {kind}"
    assert not result.ok and expected in [f.detail for f in result.failures]


@pytest.mark.parametrize("name,value,message", HEADER_CASES, ids=[c[0] for c in HEADER_CASES])
def test_unsupported_headers_are_a_controlled_failure(name, value, message, run):
    records = run[0]
    result = audit_hostile(with_record(records, 0, headers=value), run)
    assert not result.ok and f"{SNAPSHOT_FAILED}record {records[0].seq}: {message}" in [f.detail for f in result.failures]


def test_a_non_request_record_and_a_record_subclass_are_refused(run):
    records = run[0]
    duck = SimpleNamespace(**{k: getattr(records[0], k) for k in RequestRecord.__dataclass_fields__})
    sub = _SubRecord(**{k: getattr(records[0], k) for k in RequestRecord.__dataclass_fields__})
    for bad, kind in ((duck, "SimpleNamespace"), (sub, "_SubRecord"), ("record", "str"), (None, "NoneType")):
        result = audit_hostile([bad] + list(records[1:]), run)
        assert not result.ok and f"{SNAPSHOT_FAILED}record must be a RequestRecord, not {kind}" in [f.detail for f in result.failures]


@pytest.mark.parametrize("field", ["seq", "start_ns", "end_ns"])
def test_a_boolean_is_not_an_integer_in_a_record_field(field, run):
    records, skips, events, head = run
    changed = with_record(records, 0, **{field: True})
    result = audit_all(changed, skips=skips, event_log=events, event_log_head=head)
    assert not result.ok


# ------------------------------------------------------------------------------------------------ F-02 schema (hash-consistent forgeries)
def forge(records, specs):
    """A forger who recomputes every hash. specs: (index, kind, fields, records_before) with NO normalisation of any value."""
    events, prev = [], GENESIS
    for index, kind, fields, before in specs:
        digest = records_digest(records[:before])
        entry = _entry_hash(prev, index, kind, fields, before, digest)
        events.append(LogEvent(index, kind, fields, before, digest, prev, entry))
        prev = entry
    return tuple(events), prev


def decision_with(fields):
    return [(0, EVENT_DECISION, fields, 0)]


SCHEMA_CASES = [
    ("duplicate field name", decision_with((DECISION[0], DECISION[1], DECISION[1], DECISION[2], DECISION[3])),
     "event 0: duplicate field name(s) ['decided_at_ns']"),
    ("unexpected field", decision_with(tuple(sorted(DECISION + (("note", "x"),)))), "event 0: unexpected field(s) ['note'] for a DECISION event"),
    ("two unexpected fields", decision_with(tuple(sorted(DECISION + (("a", 1), ("z", 2))))), "event 0: unexpected field(s) ['a', 'z'] for a DECISION event"),
    ("missing field", decision_with(DECISION[:3]), "event 0: missing field(s) ['m_e_ns'] for a DECISION event"),
    ("no fields at all", decision_with(()), "event 0: missing field(s) ['boundary_ms', 'decided_at_ns', 'group_name', 'm_e_ns'] for a DECISION event"),
    ("non-canonical order", decision_with(tuple(reversed(DECISION))), "event 0: fields are not in canonical (sorted) order"),
    ("decision fields on a terminal event", [(0, EVENT_TIMELINE_END, DECISION, 0)], "event 0: unexpected field(s) ['boundary_ms', 'decided_at_ns', 'group_name', 'm_e_ns'] for a TIMELINE_END event"),
    ("terminal event without its field", [(0, EVENT_TIMELINE_END, (), 0)], "event 0: missing field(s) ['timeline_end_ns'] for a TIMELINE_END event"),
    ("terminal event extra field", [(0, EVENT_TIMELINE_END, (("extra", 1), ("timeline_end_ns", 5)), 0)], "event 0: unexpected field(s) ['extra'] for a TIMELINE_END event"),
    ("decided_at_ns is a bool", decision_with((DECISION[0], ("decided_at_ns", True), DECISION[2], DECISION[3])),
     "event 0: field 'decided_at_ns' must be an int or a str, not bool"),
    ("m_e_ns is a bool", decision_with((DECISION[0], DECISION[1], DECISION[2], ("m_e_ns", False))), "event 0: field 'm_e_ns' must be an int or a str, not bool"),
    ("boundary_ms is a str", decision_with((("boundary_ms", "1700"),) + DECISION[1:]), "event 0: field 'boundary_ms' must have type int, not str"),
    ("group_name is an int", decision_with(DECISION[:2] + (("group_name", 2),) + DECISION[3:]), "event 0: field 'group_name' must have type str, not int"),
    ("timeline_end_ns is a bool", [(0, EVENT_TIMELINE_END, (("timeline_end_ns", True),), 0)], "event 0: field 'timeline_end_ns' must be an int or a str, not bool"),
    ("timeline_end_ns is a str", [(0, EVENT_TIMELINE_END, (("timeline_end_ns", "5"),), 0)], "event 0: field 'timeline_end_ns' must have type int, not str"),
    ("float value", decision_with((DECISION[0], ("decided_at_ns", 5.0), DECISION[2], DECISION[3])), "event 0: field 'decided_at_ns' must be an int or a str, not float"),
    ("None value", decision_with((DECISION[0], ("decided_at_ns", None), DECISION[2], DECISION[3])), "event 0: field 'decided_at_ns' must be an int or a str, not NoneType"),
    ("non-str field name", decision_with(((1, 2),) + DECISION), "event 0: field names must be str, not int"),
    ("field is not a pair", decision_with((("boundary_ms",),) + DECISION[1:]), "event 0: every field must be a (name, value) pair"),
    ("field is a triple", decision_with((("boundary_ms", 1, 2),) + DECISION[1:]), "event 0: every field must be a (name, value) pair"),
    ("fields is a dict", decision_with({"a": 1}), "event 0: fields must be a tuple of (name, value) pairs, not dict"),
    ("fields is a str", decision_with("ab"), "event 0: fields must be a tuple of (name, value) pairs, not str"),
    ("index is a bool", [(0, EVENT_DECISION, DECISION, 0), (True, EVENT_TIMELINE_END, TL_END, 0)], "event 1: index must have type int, not bool"),
]


@pytest.mark.parametrize("name,specs,message", SCHEMA_CASES, ids=[c[0] for c in SCHEMA_CASES])
def test_a_hash_consistent_forgery_that_breaks_the_schema_is_rejected_with_the_exact_message(name, specs, message, run):
    records = run[0]
    events, head = forge(records, specs)
    with pytest.raises(EventLogError) as info:
        verify_event_log(events, head, records)
    assert str(info.value) == message
    result = audit_all(records, skips=run[1], event_log=events, event_log_head=head)
    assert not result.ok and message in text(result)


def test_a_boolean_records_before_is_not_an_integer(run):
    records = run[0]
    events, head = forge(records, [(0, EVENT_DECISION, DECISION, 0), (1, EVENT_TIMELINE_END, TL_END, True)])
    with pytest.raises(EventLogError, match=r"event 1: records_before must have type int, not bool"):
        verify_event_log(events, head, records)


@pytest.mark.parametrize("field,value,kind", [("entry_hash", b"x" * 64, "bytes"), ("prev_hash", 7, "int"), ("records_digest", ["a"], "list"),
                                              ("kind", b"DECISION", "bytes"), ("index", 0.0, "float")])
def test_non_primitive_scalars_of_an_event_are_refused(field, value, kind, run):
    records, _, events, head = run
    forged = (replace(events[0], **{field: value}),) + events[1:]
    with pytest.raises(EventLogError, match=rf"event 0: {field} must have type (int|str), not {kind}"):
        verify_event_log(forged, head, records)


def test_the_honest_writer_output_still_satisfies_the_schema(run):
    records, _, events, head = run
    assert verify_event_log(events, head, records).timeline_end is not None
    assert [tuple(n for n, _ in e.fields) for e in events] == [tuple(n for n, _ in DECISION), ("timeline_end_ns",)]


# ------------------------------------------------------------------------------------------------ F-02 snapshots
def test_mutable_event_fields_are_normalised_into_an_immutable_snapshot(run):
    records, _, events, head = run
    mutable = tuple(replace(e, fields=[list(pair) for pair in e.fields]) for e in events)       # hashes are unchanged
    verified = verify_event_log(mutable, head, records)
    snap = verified.events[0]
    assert snap is not mutable[0] and type(snap.fields) is tuple and all(type(p) is tuple for p in snap.fields)
    expected = snap.fields
    mutable[0].fields[1][1] = 123456                                                           # edit the caller's objects afterwards
    mutable[0].fields.append(["note", "x"])
    assert verified.events[0].fields == expected
    with pytest.raises(FrozenInstanceError):
        snap.fields = ()
    with pytest.raises(TypeError):
        snap.fields[0][1] = 0
    with pytest.raises(TypeError):
        verified.events[0] = snap


def test_the_audit_consumes_only_the_verified_snapshot_even_if_the_callers_event_fields_change_after_verification(monkeypatch, run):
    records, skips, events, head = run
    mutable = tuple(replace(e, fields=[list(pair) for pair in e.fields]) for e in events)
    real = audit_module.verify_event_log

    def hostile(event_log, head_digest, recs):
        verified = real(event_log, head_digest, recs)
        for event in mutable:                                                                   # after verification, before the checks that use it
            for pair in event.fields:
                pair[1] = 0 if isinstance(pair[1], int) else "zzz"
        return verified

    monkeypatch.setattr(audit_module, "verify_event_log", hostile)
    result = audit_all(records, skips=skips, event_log=mutable, event_log_head=head)
    assert all(pair[1] in (0, "zzz") for e in mutable for pair in e.fields)                    # control: the hostile edit really happened
    assert result.ok, text(result)


def test_the_outer_event_list_is_snapshotted_too(monkeypatch, run):
    records, skips, events, head = run
    live = list(events)
    real = audit_module.verify_event_log

    def hostile(event_log, head_digest, recs):
        live.clear()
        return real(event_log, head_digest, recs)

    monkeypatch.setattr(audit_module, "verify_event_log", hostile)
    assert audit_all(records, skips=skips, event_log=live, event_log_head=head).ok and live == []


def test_nothing_returned_by_verification_aliases_the_input(run):
    records, _, events, head = run
    verified = verify_event_log(list(events), head, records)
    assert all(v is not e for v, e in zip(verified.events, events)) and tuple(verified.events) == tuple(events)
