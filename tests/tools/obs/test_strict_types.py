"""Exact-type validation of every RequestRecord field (F-01) and of the manifest head digest (F-02). Offline, deterministic.

`type(x) is int` / `type(x) is str` is the rule, never isinstance: a bool is not an int, and int/str/sequence subclasses (whose
__eq__, __ne__, __hash__, __repr__, __iter__ or __getitem__ could be hostile) are refused BEFORE any comparison, hashing,
formatting or iteration touches them. Hostile objects count their calls so the tests can prove no hostile method ever ran."""
from dataclasses import FrozenInstanceError, dataclass, fields, replace

import pytest

from tests.fixtures.obs_fakes import audit_all, authenticated_manifest, recorded_events
from tests.tools.obs.test_deep_immutability import SNAPSHOT_FAILED, audit_hostile, with_record
from tests.tools.obs.test_provenance import skip_case
from tools.obs import audit as audit_module
from tools.obs.eventlog import EventLogError, verify_event_log
from tools.obs.pacer import RequestRecord

CALLS = {"count": 0}


def hostile(name):
    CALLS["count"] += 1


class EvilInt(int):
    def __eq__(self, other): hostile("eq"); return True
    def __ne__(self, other): hostile("ne"); return False
    def __hash__(self): hostile("hash"); return 0
    def __repr__(self): hostile("repr"); raise RuntimeError("hostile repr")
    __str__ = __repr__
    def __lt__(self, other): hostile("lt"); return False
    __gt__ = __le__ = __ge__ = __lt__


class EvilStr(str):
    def __eq__(self, other): hostile("eq"); return True
    def __ne__(self, other): hostile("ne"); return False
    def __hash__(self): hostile("hash"); return 0
    def __repr__(self): hostile("repr"); raise RuntimeError("hostile repr")
    def __str__(self): hostile("str"); raise RuntimeError("hostile str")
    def __len__(self): hostile("len"); return 64


@dataclass(frozen=True)
class EqRecord(RequestRecord):
    def __eq__(self, other): hostile("eq"); return True
    def __hash__(self): hostile("hash"); return 0


@pytest.fixture(autouse=True)
def reset_calls():
    CALLS["count"] = 0


@pytest.fixture
def run():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    return records, skips, events, head


INT_FIELDS = [("seq", False), ("start_ns", False), ("end_ns", False), ("status", True), ("boundary_ms", True)]
STR_FIELDS = [("role", False), ("path", False), ("error", True), ("group_name", True), ("group_kind", True)]


def expected_message(label, name, kind, optional):
    article = "an" if kind is int else "a"
    return f"{label}: {name} must be {article} {kind.__name__}{' or None' if optional else ''}, not "


def bad_values(kind, optional):
    other = "x" if kind is int else 5
    cases = [(other, type(other).__name__), (b"x", "bytes"), (1.5, "float"), ([1], "list")]
    if kind is int:
        cases += [(True, "bool"), (False, "bool"), (EvilInt(7), "EvilInt")]
    else:
        cases += [(EvilStr("x"), "EvilStr")]
    if not optional:
        cases.append((None, "NoneType"))
    return cases


ALL_CASES = [(name, kind, optional, value, tname) for fields_, kind in ((INT_FIELDS, int), (STR_FIELDS, str)) for name, optional in fields_
             for value, tname in bad_values(kind, optional)]


# ------------------------------------------------------------------------------------------------ F-01 every field, every unsupported type
@pytest.mark.parametrize("name,kind,optional,value,tname", ALL_CASES, ids=[f"{c[0]}-{c[4]}" for c in ALL_CASES])
def test_every_unsupported_field_type_is_a_controlled_audit_failure_and_no_hostile_method_runs(name, kind, optional, value, tname, run):
    records = run[0]
    result = audit_hostile(with_record(records, 0, **{name: value}), run)
    label = "record" if name == "seq" else f"record {records[0].seq}"
    expected = SNAPSHOT_FAILED + expected_message(label, name, kind, optional) + tname
    assert not result.ok and expected in [f.detail for f in result.failures]
    assert CALLS["count"] == 0, "a hostile comparison, hash, repr or str method ran on an unvalidated value"


@pytest.mark.parametrize("name,optional", [(n, o) for n, o in INT_FIELDS + STR_FIELDS if o])
def test_none_is_accepted_exactly_where_the_dataclass_allows_it(name, optional, run):
    records = run[0]
    frozen = audit_module._freeze_record(replace(records[0], **{name: None}))
    assert getattr(frozen, name) is None


@pytest.mark.parametrize("name", [n for n, o in INT_FIELDS + STR_FIELDS if not o])
def test_required_fields_never_accept_none(name, run):
    with pytest.raises(TypeError, match=rf"{name} must be an? (int|str), not NoneType"):
        audit_module._freeze_record(replace(run[0][0], **{name: None}))


def test_every_dataclass_scalar_field_is_covered_by_the_validator_table():
    scalar = {f.name for f in fields(RequestRecord)} - {"body", "headers"}
    assert scalar == {name for name, *_ in audit_module._RECORD_FIELDS} == {n for n, _ in INT_FIELDS + STR_FIELDS}


def test_a_hostile_request_record_subclass_is_refused_before_any_method_runs(run):
    sub = EqRecord(**{f.name: getattr(run[0][0], f.name) for f in fields(RequestRecord)})
    result = audit_hostile([sub] + list(run[0][1:]), run)
    assert not result.ok and f"{SNAPSHOT_FAILED}record must be a RequestRecord, not EqRecord" in [f.detail for f in result.failures]
    assert CALLS["count"] == 0


def test_the_frozen_copy_is_built_from_exact_primitives_and_equals_a_valid_original(run):
    for original in run[0]:
        frozen = audit_module._freeze_record(original)
        assert frozen is not original and frozen == original and type(frozen) is RequestRecord
        for name, kind, optional in audit_module._RECORD_FIELDS:
            value = getattr(frozen, name)
            assert (value is None and optional) or type(value) is kind, name
        assert type(frozen.body) is bytes and type(frozen.headers) is tuple


def test_attribute_changes_to_the_original_after_the_snapshot_never_reach_the_copy(run):
    original = run[0][0]
    frozen = audit_module._freeze_record(original)
    snapshot = {f.name: getattr(frozen, f.name) for f in fields(RequestRecord)}
    for name, value in (("seq", 999), ("role", "HACK"), ("path", "/x"), ("start_ns", -1), ("end_ns", -2), ("status", 500),
                        ("error", "boom"), ("group_name", "gX"), ("group_kind", "1h"), ("boundary_ms", 1), ("body", b"tampered"), ("headers", [["a", "b"]])):
        object.__setattr__(original, name, value)                       # bypasses the dataclass freeze, as hostile code could
    assert {f.name: getattr(frozen, f.name) for f in fields(RequestRecord)} == snapshot
    with pytest.raises(FrozenInstanceError):
        frozen.seq = 5


def test_mutating_the_original_records_during_the_audit_cannot_change_the_result(monkeypatch, run):
    records, skips, events, head = run
    live = list(records)
    baseline = audit_all(live, skips=skips, event_log=events, event_log_head=head)
    assert baseline.ok
    real = audit_module.verify_event_log

    def tamper(event_log, head_digest, recs):
        for r in live:
            object.__setattr__(r, "seq", -1)
            object.__setattr__(r, "role", "HACK")
            object.__setattr__(r, "start_ns", 10**30)
            object.__setattr__(r, "body", b"tampered")
        live.clear()
        return real(event_log, head_digest, recs)

    monkeypatch.setattr(audit_module, "verify_event_log", tamper)
    fresh, fresh_skips, fresh_events, fresh_head = (lambda c: (c[0], c[3], *recorded_events(c[0], c[3])))(skip_case())
    result = audit_all(fresh, skips=fresh_skips, event_log=fresh_events, event_log_head=fresh_head)
    assert result.ok and [f.detail for f in result.failures] == [f.detail for f in baseline.failures]


def test_a_sequence_subclass_of_records_is_iterated_exactly_once(run):
    records, skips, events, head = run

    class OnceList(list):
        iterations = 0
        def __iter__(self):
            type(self).iterations += 1
            return super().__iter__()

    manifest = authenticated_manifest(list(records), events, head)               # built from a plain list: the helper must not iterate the subclass
    live = OnceList(records)
    result = audit_module.audit_pace(live, skips=skips, event_log=events, manifest=manifest, jsonl_count=len(records),
                                     wrapper_count=len(records), manifest_count=len(records))
    assert result.ok and OnceList.iterations == 1


# ------------------------------------------------------------------------------------------------ F-02 head digest
GOOD = "0123456789abcdef" * 4


@pytest.mark.parametrize("value,why", [
    (GOOD.upper(), "uppercase"), (GOOD[:-1], "63 chars"), (GOOD + "0", "65 chars"), ("", "empty"), ("g" * 64, "non-hex"),
    (GOOD[:-1] + "G", "one non-hex char"), (GOOD + "\n", "trailing newline"), (" " + GOOD[1:], "leading space"), (GOOD[:-1] + "\u0663", "unicode digit"),
    ("0x" + GOOD[2:], "0x prefix"), (GOOD.encode(), "bytes"), (None, "None"), (123, "int"), (["a"] * 64, "list of 64"),
    (bytearray(GOOD, "ascii"), "bytearray"), (True, "bool"),
], ids=["uppercase", "63 chars", "65 chars", "empty", "non-hex", "one non-hex char", "trailing newline", "leading space", "unicode digit",
        "0x prefix", "bytes", "None", "int", "list", "bytearray", "bool"])
def test_a_malformed_head_digest_is_rejected_with_the_exact_message(value, why, run):
    records, _, events, _ = run
    with pytest.raises(EventLogError) as info:
        verify_event_log(events, value, records)
    assert str(info.value) == "the manifest head digest is missing or malformed"


def test_a_hostile_str_subclass_head_digest_is_rejected_before_any_comparison(run):
    records, _, events, head = run
    evil = EvilStr(head)                                                # the CORRECT digest, wrapped in a hostile str
    with pytest.raises(EventLogError) as info:
        verify_event_log(events, evil, records)
    assert str(info.value) == "the manifest head digest is missing or malformed" and CALLS["count"] == 0


def test_the_uppercase_form_of_the_real_head_is_malformed_not_a_chain_mismatch(run):
    records, _, events, head = run
    with pytest.raises(EventLogError, match="^the manifest head digest is missing or malformed$"):
        verify_event_log(events, head.upper(), records)


def test_a_well_formed_but_wrong_head_is_a_chain_mismatch_and_the_right_one_passes(run):
    records, _, events, head = run
    flipped = head[:-1] + ("0" if head[-1] != "0" else "1")
    with pytest.raises(EventLogError, match="the chain head does not match the manifest digest"):
        verify_event_log(events, flipped, records)
    assert verify_event_log(events, head, records).timeline_end is not None


def test_the_comparison_with_the_head_never_runs_hostile_code_even_if_events_carry_str_subclasses(run):
    records, _, events, head = run
    evil_event = replace(events[-1], entry_hash=EvilStr(events[-1].entry_hash))
    with pytest.raises(EventLogError, match=r"event 1: entry_hash must have type str, not EvilStr"):
        verify_event_log(events[:-1] + (evil_event,), head, records)
    assert CALLS["count"] == 0


# ------------------------------------------------------------------------------------------------ F-02 hostile sequences
def hostile_sequences(events):
    class IterList(list):
        iterations = 0
        def __iter__(self):
            type(self).iterations += 1
            return iter(())                                              # claims to be empty when iterated
    class ItemList(list):
        def __getitem__(self, index): hostile("getitem"); raise RuntimeError("hostile getitem")
        def __len__(self): hostile("len"); return 0
    class IterTuple(tuple):
        def __iter__(self): hostile("iter"); return iter(())
    return [("list subclass with hostile __iter__", IterList(events)), ("list subclass with hostile __getitem__/__len__", ItemList(events)),
            ("tuple subclass with hostile __iter__", IterTuple(events))]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_event_sequence_subclasses_are_refused_by_verify_event_log_without_being_iterated(index, run):
    records, _, events, head = run
    label, hostile_events = hostile_sequences(events)[index]
    with pytest.raises(EventLogError) as info:
        verify_event_log(hostile_events, head, records)
    assert str(info.value) == "the event log is missing or not a sequence of LogEvent entries", label
    assert CALLS["count"] == 0 and getattr(type(hostile_events), "iterations", 0) == 0


@pytest.mark.parametrize("index", [0, 1, 2])
def test_event_sequence_subclasses_are_refused_at_the_audit_entry_too(index, run):
    records, skips, events, head = run
    label, hostile_events = hostile_sequences(events)[index]
    manifest = authenticated_manifest(records, events, head)
    result = audit_module.audit_pace(records, skips=skips, event_log=hostile_events, manifest=manifest, jsonl_count=len(records),
                                     wrapper_count=len(records), manifest_count=len(records))
    assert not result.ok
    assert "input snapshot failed for event_log: TypeError: event_log must be a built-in list or tuple of log events" in [f.detail for f in result.failures], label
    assert CALLS["count"] == 0 and getattr(type(hostile_events), "iterations", 0) == 0


def test_a_plain_list_or_tuple_of_events_is_accepted(run):
    records, skips, events, head = run
    assert verify_event_log(list(events), head, records).timeline_end is not None
    assert verify_event_log(tuple(events), head, records).timeline_end is not None
