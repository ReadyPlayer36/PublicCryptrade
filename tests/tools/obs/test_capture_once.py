"""Capture-once snapshots (reviewer: TOCTOU in _freeze_event). Offline and deterministic: no threads, no sleeps.

The window being closed is "attribute read for validation" -> "attribute read again for reconstruction". Concurrency cannot be
scheduled deterministically, so the tests instrument `__getattribute__` of the (class-level patchable) dataclasses: they COUNT
every read and, the instant an attribute has been read once, REPLACE it on the live object with a hostile value (object.__setattr__
bypasses the dataclass freeze, exactly as a racing writer would). A snapshot taken correctly (one read, validate the capture,
rebuild from the capture) equals the honest first-read value; any second read would surface the hostile value."""
from collections import Counter
from dataclasses import fields as dc_fields

import pytest

from tests.fixtures.obs_fakes import authenticated_manifest, recorded_events
from tests.tools.obs.test_provenance import skip_case
from tools.obs import audit as audit_module
from tools.obs.eventlog import EventLogError, LogEvent, _freeze_event, verify_event_log
from tools.obs.pacer import RequestRecord

EVENT_ATTRS = ("index", "kind", "fields", "records_before", "records_digest", "prev_hash", "entry_hash")
RECORD_ATTRS = tuple(f.name for f in dc_fields(RequestRecord))


class Evil(str):
    def __eq__(self, other): raise RuntimeError("hostile eq")
    def __hash__(self): raise RuntimeError("hostile hash")


EVENT_HOSTILE = {"index": True, "kind": b"DECISION", "fields": [["note", "x"], ["boundary_ms", 1]], "records_before": True,
                 "records_digest": Evil("0" * 64), "prev_hash": 7, "entry_hash": None}
RECORD_HOSTILE = {"seq": True, "role": Evil("HACK"), "path": 5, "start_ns": -1, "end_ns": 1.5, "status": True, "error": b"boom",
                  "group_name": Evil("gX"), "group_kind": [1], "boundary_ms": True, "body": "tampered", "headers": "oops"}


@pytest.fixture
def run():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    return records, skips, events, head


def instrument(monkeypatch, cls, names, targets, on_read):
    """Count reads of `names` on the instances in `targets` (by id); call on_read(obj, name, nth) AFTER each read returns."""
    reads = Counter()
    ids = {id(t) for t in targets}
    real = object.__getattribute__

    def hook(self, name):
        value = real(self, name)
        if name in names and id(self) in ids:
            reads[name] += 1
            on_read(self, name, reads[name])
        return value

    monkeypatch.setattr(cls, "__getattribute__", hook)
    return reads


def honest(obj, names):
    return {n: object.__getattribute__(obj, n) for n in names}


# ------------------------------------------------------------------------------------------------ one read per attribute
@pytest.mark.parametrize("position", [0, 1])
def test_freeze_event_reads_every_attribute_of_the_event_exactly_once(position, monkeypatch, run):
    event = run[2][position]
    reads = instrument(monkeypatch, LogEvent, EVENT_ATTRS, [event], lambda *a: None)
    snapshot = _freeze_event(event, position)
    assert dict(reads) == {name: 1 for name in EVENT_ATTRS}
    assert snapshot is not event


def test_verify_event_log_reads_every_original_event_attribute_exactly_once(monkeypatch, run):
    records, _, events, head = run
    reads = instrument(monkeypatch, LogEvent, EVENT_ATTRS, events, lambda *a: None)
    verified = verify_event_log(events, head, records)
    assert dict(reads) == {name: len(events) for name in EVENT_ATTRS}                    # one read per attribute per original event
    assert len(verified.events) == len(events)


def test_freeze_record_reads_every_attribute_of_the_record_exactly_once(monkeypatch, run):
    record = run[0][0]
    reads = instrument(monkeypatch, RequestRecord, RECORD_ATTRS, [record], lambda *a: None)
    audit_module._freeze_record(record)
    assert dict(reads) == {name: 1 for name in RECORD_ATTRS}


# ------------------------------------------------------------------------------------------------ mutation right after the capture
@pytest.mark.parametrize("position", [0, 1])
@pytest.mark.parametrize("attr", EVENT_ATTRS)
def test_an_event_attribute_changed_right_after_its_capture_never_reaches_the_snapshot(attr, position, monkeypatch, run):
    event = run[2][position]
    expected = honest(event, EVENT_ATTRS)
    expected["fields"] = tuple(tuple(pair) for pair in expected["fields"])

    def flip(obj, name, nth):
        if name == attr and nth == 1:
            object.__setattr__(obj, name, EVENT_HOSTILE[name])                         # the racing writer strikes after the first read

    instrument(monkeypatch, LogEvent, EVENT_ATTRS, [event], flip)
    snapshot = _freeze_event(event, position)
    assert object.__getattribute__(event, attr) is EVENT_HOSTILE[attr]                  # control: the hostile value really was installed
    for name in EVENT_ATTRS:
        assert object.__getattribute__(snapshot, name) == expected[name], name
    assert type(snapshot.index) is int and type(snapshot.records_before) is int and type(snapshot.fields) is tuple


@pytest.mark.parametrize("attr", RECORD_ATTRS)
def test_a_record_attribute_changed_right_after_its_capture_never_reaches_the_snapshot(attr, monkeypatch, run):
    record = run[0][0]
    expected = honest(record, RECORD_ATTRS)
    expected["headers"] = tuple(tuple(h) for h in expected["headers"])

    def flip(obj, name, nth):
        if name == attr and nth == 1:
            object.__setattr__(obj, name, RECORD_HOSTILE[name])

    instrument(monkeypatch, RequestRecord, RECORD_ATTRS, [record], flip)
    snapshot = audit_module._freeze_record(record)
    assert object.__getattribute__(record, attr) is RECORD_HOSTILE[attr]
    for name in RECORD_ATTRS:
        assert object.__getattribute__(snapshot, name) == expected[name], name


# ------------------------------------------------------------------------------------------------ mutation between capture and validation
def test_every_other_attribute_replaced_after_the_first_capture_is_validated_as_captured_never_reread(monkeypatch, run):
    """The first read (index) triggers a flip of ALL the other attributes. They are captured AFTER the flip, so the hostile values
    are what is captured; validation must reject them (never rebuild from a second, different read)."""
    event = run[2][0]

    def flip_all(obj, name, nth):
        if name == "index" and nth == 1:
            for other in EVENT_ATTRS:
                if other != "index":
                    object.__setattr__(obj, other, EVENT_HOSTILE[other])

    instrument(monkeypatch, LogEvent, EVENT_ATTRS, [event], flip_all)
    with pytest.raises(EventLogError, match=r"^event 0: records_before must have type int, not bool$"):
        _freeze_event(event, 0)


def test_valid_looking_replacements_after_the_first_capture_are_caught_by_the_chain_not_mixed_into_a_snapshot(monkeypatch, run):
    records, _, events, head = run

    def flip_all(obj, name, nth):
        if name == "index" and nth == 1:
            object.__setattr__(obj, "prev_hash", "f" * 64)                              # a perfectly well-typed but different value
            object.__setattr__(obj, "entry_hash", "e" * 64)

    instrument(monkeypatch, LogEvent, EVENT_ATTRS, [events[0]], flip_all)
    with pytest.raises(EventLogError):
        verify_event_log(events, head, records)


def test_the_fields_container_is_copied_once_so_later_edits_to_the_callers_lists_cannot_reach_the_snapshot(run):
    event = run[2][0]
    mutable = LogEvent(event.index, event.kind, [list(pair) for pair in event.fields], event.records_before, event.records_digest,
                       event.prev_hash, event.entry_hash)
    snapshot = _freeze_event(mutable, 0)
    expected = snapshot.fields
    for pair in mutable.fields:
        pair[1] = 0 if isinstance(pair[1], int) else "zzz"
    mutable.fields.append(["note", "x"])
    mutable.fields.clear()
    assert snapshot.fields == expected and type(snapshot.fields) is tuple and all(type(p) is tuple for p in snapshot.fields)


# ------------------------------------------------------------------------------------------------ end to end through the audit
def test_hostile_replacement_of_every_event_and_record_attribute_during_the_audit_cannot_change_the_result(monkeypatch, run):
    records, skips, events, head = run
    manifest = authenticated_manifest(list(records), events, head)                      # built BEFORE any instrumentation
    flipped = Counter()

    def flip_event(obj, name, nth):
        if nth == 1:
            flipped[("event", name)] += 1
            object.__setattr__(obj, name, EVENT_HOSTILE[name])

    def flip_record(obj, name, nth):
        if nth == 1:
            flipped[("record", name)] += 1
            object.__setattr__(obj, name, RECORD_HOSTILE[name])

    ev_reads = instrument(monkeypatch, LogEvent, EVENT_ATTRS, events, flip_event)
    rec_reads = instrument(monkeypatch, RequestRecord, RECORD_ATTRS, records, flip_record)
    result = audit_module.audit_pace(records, skips=skips, event_log=events, manifest=manifest, jsonl_count=len(records),
                                     wrapper_count=len(records), manifest_count=len(records))
    assert result.ok, [f.detail for f in result.failures]
    assert all(v == len(events) for v in ev_reads.values()) and set(ev_reads) == set(EVENT_ATTRS)         # one read per event attribute
    assert all(v == len(records) for v in rec_reads.values()) and set(rec_reads) == set(RECORD_ATTRS)     # one read per record attribute
    assert len(flipped) == len(EVENT_ATTRS) + len(RECORD_ATTRS)                                           # control: every attribute was attacked
