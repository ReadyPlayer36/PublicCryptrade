"""Fix 10: building the input snapshots runs caller-controlled code. If a container is mutated (or otherwise fails) while it is
being copied, audit_pace returns a controlled failure instead of letting the exception escape."""
from collections.abc import Mapping

import pytest

from tests.tools.obs.test_manifest_trust_and_types import run  # noqa: F401  (fixture)
from tools.obs.audit import AuditResult, audit_pace

EXCEPTIONS = [RuntimeError("container changed size during iteration"), ValueError("bad"), TypeError("bad"), KeyError("k"),
              IndexError("i"), AttributeError("a")]


class ExplodingList(list):
    """A sequence that is 'mutated by someone else' while it is copied: yields one item, then fails."""

    def __init__(self, items, exc):
        super().__init__(items)
        self._exc = exc

    def __iter__(self):
        iterator = super().__iter__()
        yield next(iterator)
        raise self._exc


class ExplodingMapping(Mapping):
    """A mapping whose key iteration fails part-way (the dict-changed-size case), via the Mapping protocol dict() uses."""

    def __init__(self, data, exc):
        self._data, self._exc = dict(data), exc

    def __iter__(self):
        for key in self._data:
            yield key
            raise self._exc

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)


class VanishingMapping(ExplodingMapping):
    """A mapping whose entry disappears between listing the keys and reading the value (KeyError from __getitem__)."""

    def __iter__(self):
        yield from self._data

    def __getitem__(self, key):
        raise KeyError(key)


def call(records, **kwargs):
    n = len(records)
    return audit_pace(records, jsonl_count=n, wrapper_count=n, manifest_count=n, **kwargs)


def assert_controlled(result, name, exc=None):
    assert isinstance(result, AuditResult) and not result.ok
    assert result.checks() == {"a"} and len(result.failures) == 1
    detail = result.failures[0].detail
    assert f"input snapshot failed for {name}" in detail
    if exc is not None:
        assert type(exc).__name__ in detail


@pytest.mark.parametrize("exc", EXCEPTIONS, ids=lambda e: type(e).__name__)
def test_a_records_container_failing_during_the_copy_is_a_controlled_failure(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    assert_controlled(call(ExplodingList(records, exc)), "records", exc)


@pytest.mark.parametrize("exc", EXCEPTIONS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("name", ["skips", "boundary_skips"])
def test_a_mapping_failing_during_the_copy_is_a_controlled_failure(run, name, exc):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), **{name: ExplodingMapping(skips or {(1, "g"): 1}, exc)})
    assert_controlled(result, name, exc)


@pytest.mark.parametrize("name", ["skips", "boundary_skips"])
def test_a_mapping_entry_vanishing_between_listing_and_reading_is_a_controlled_failure(run, name):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), **{name: VanishingMapping({(1, "g"): 1}, KeyError("x"))})
    assert_controlled(result, name, KeyError("x"))


@pytest.mark.parametrize("exc", EXCEPTIONS[:3], ids=lambda e: type(e).__name__)
def test_expected_boundaries_and_event_log_failing_during_the_copy_are_controlled_failures(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    assert_controlled(call(list(records), expected_boundaries=ExplodingList([1, 2, 3], exc)), "expected_boundaries", exc)
    assert_controlled(call(list(records), event_log=ExplodingList(events, exc), manifest=manifest), "event_log", exc)


def test_a_generator_that_raises_part_way_is_a_controlled_failure(run):
    run_dir, pin, records, events, skips, manifest = run

    def failing():
        yield records[0]
        raise RuntimeError("generator mutated underneath us")

    result = audit_pace(failing(), jsonl_count=1, wrapper_count=1, manifest_count=1)
    assert_controlled(result, "records", RuntimeError("x"))


def test_a_container_that_mutates_itself_while_being_copied_is_a_controlled_failure(run):
    run_dir, pin, records, events, skips, manifest = run

    class SelfMutating(list):
        def __iter__(self):
            yield self[0]
            self.clear()                                                                 # shrinks mid-iteration ...
            raise RuntimeError("list changed size during iteration")                     # ... and the copier notices

    assert_controlled(call(SelfMutating(records)), "records")


def test_interrupts_are_not_swallowed_by_the_snapshot_boundary(run):
    run_dir, pin, records, events, skips, manifest = run
    with pytest.raises(KeyboardInterrupt):
        call(ExplodingList(records, KeyboardInterrupt()))


def test_ordinary_inputs_still_audit_normally_and_no_controlled_failure_appears(run):
    run_dir, pin, records, events, skips, manifest = run
    n = len(records)
    result = audit_pace(list(records), jsonl_count=n, wrapper_count=n, manifest_count=n, skips=dict(skips), event_log=list(events), manifest=manifest)
    assert result.ok and all("input snapshot failed" not in f.detail for f in result.failures)


# ---- Fix 11: event_log must be fully snapshotted inside the boundary; hostile exceptions cannot escape it ----
from collections.abc import Sequence


class LenRaises(Sequence):
    """A real Sequence whose __len__ fails (e.g. the underlying store changed): the audit must never call it outside the guard."""

    def __init__(self, items, exc):
        self._items, self._exc = list(items), exc

    def __len__(self):
        raise self._exc

    def __getitem__(self, index):
        return self._items[index]


class DuckLenRaises:
    """Sequence-like by duck typing only (not a registered Sequence), with a failing __len__."""

    def __len__(self):
        raise RuntimeError("len blew up")

    def __getitem__(self, index):
        raise IndexError(index)


@pytest.mark.parametrize("exc", [e for e in EXCEPTIONS if not isinstance(e, TypeError)], ids=lambda e: type(e).__name__)
def test_an_event_log_whose_len_raises_is_a_controlled_failure_with_a_valid_manifest(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), event_log=LenRaises(events, exc), manifest=manifest)
    assert_controlled(result, "event_log", exc)


def test_a_len_typeerror_is_treated_by_tuple_as_no_length_hint_so_the_copy_succeeds_and_is_audited_normally(run):
    """CPython's tuple() swallows a TypeError from __len__ (length-hint semantics) and copies by iteration. The snapshot is then a
    complete, valid log, so the audit proceeds on it (not a snapshot failure) and, being honest, passes."""
    run_dir, pin, records, events, skips, manifest = run
    n = len(records)
    result = audit_pace(list(records), jsonl_count=n, wrapper_count=n, manifest_count=n, skips=dict(skips),
                        event_log=LenRaises(events, TypeError("no len")), manifest=manifest)
    assert result.ok and all("input snapshot failed" not in f.detail for f in result.failures)


def test_a_duck_typed_event_log_is_rejected_at_the_boundary_not_probed_with_len(run):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), event_log=DuckLenRaises(), manifest=manifest)
    assert_controlled(result, "event_log", TypeError())
    assert "must be a sequence" in result.failures[0].detail


@pytest.mark.parametrize("bad", [{"a": 1}, {1, 2}, 7, 1.5, object(), iter(())], ids=["dict", "set", "int", "float", "object", "iterator"])
def test_unsupported_event_log_types_are_rejected_at_the_boundary(run, bad):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), event_log=bad, manifest=manifest)
    assert_controlled(result, "event_log", TypeError())


def test_a_string_event_log_is_snapshotted_then_rejected_by_verification_without_raising(run):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), event_log="not a log", manifest=manifest)
    assert not result.ok and "event log rejected" in result.failures[0].detail


def test_any_registered_sequence_event_log_is_converted_to_a_tuple_and_audits_normally(run):
    run_dir, pin, records, events, skips, manifest = run
    n = len(records)
    class Plain(Sequence):
        def __len__(self):
            return len(events)

        def __getitem__(self, index):
            return events[index]

    result = audit_pace(list(records), jsonl_count=n, wrapper_count=n, manifest_count=n, skips=dict(skips), event_log=Plain(), manifest=manifest)
    assert result.ok


# hostile exceptions: stringification must not escape the normalisation boundary
class StrRaises(Exception):
    def __str__(self):
        raise RuntimeError("__str__ exploded")


class StrReturnsInt(Exception):
    def __str__(self):
        return 42


class StrReturnsHuge(Exception):
    def __str__(self):
        return "x" * 10_000


class NameMeta(type):
    @property
    def __name__(cls):
        raise RuntimeError("__name__ exploded")


class BrokenNameError(Exception, metaclass=NameMeta):
    pass


@pytest.mark.parametrize("exc", [StrRaises("a"), StrReturnsInt("a"), StrReturnsHuge("a"), BrokenNameError("a")],
                         ids=["str_raises", "str_returns_int", "str_huge", "name_raises"])
def test_a_hostile_exception_cannot_escape_the_snapshot_boundary(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    result = call(ExplodingList(records, exc))
    assert isinstance(result, AuditResult) and not result.ok and result.checks() == {"a"}
    detail = result.failures[0].detail
    assert "input snapshot failed for records" in detail and len(detail) < 400
