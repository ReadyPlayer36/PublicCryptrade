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
def test_expected_boundaries_failing_during_the_copy_is_a_controlled_failure(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    assert_controlled(call(list(records), expected_boundaries=ExplodingList([1, 2, 3], exc)), "expected_boundaries", exc)


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


# ---- Fix 12 (F11-01): event_log accepts exactly the built-in list and tuple, the types verify_event_log accepts ----
from collections.abc import Sequence

TYPE_MSG = "built-in list or tuple"


class Probe:
    """Records every protocol call a hostile container receives; the boundary must reject it WITHOUT making any of them."""

    def __init__(self):
        self.calls = []


def probed_candidates(events):
    probe = Probe()

    class LenRaises(Sequence):
        def __len__(self):
            probe.calls.append("__len__")
            raise RuntimeError("len blew up")

        def __getitem__(self, index):
            probe.calls.append("__getitem__")
            return list(events)[index]

    class HostileIter(Sequence):
        def __len__(self):
            probe.calls.append("__len__")
            return len(events)

        def __iter__(self):
            probe.calls.append("__iter__")
            raise ValueError("iter blew up")

        def __getitem__(self, index):
            probe.calls.append("__getitem__")
            return list(events)[index]

    class Duck:
        def __len__(self):
            probe.calls.append("__len__")
            return 0

        def __getitem__(self, index):
            probe.calls.append("__getitem__")
            raise IndexError(index)

    class ListSub(list):
        def __iter__(self):
            probe.calls.append("__iter__")
            raise RuntimeError("list subclass iter")

        def __len__(self):
            probe.calls.append("__len__")
            raise RuntimeError("list subclass len")

    class TupleSub(tuple):
        def __iter__(self):
            probe.calls.append("__iter__")
            raise RuntimeError("tuple subclass iter")

    def gen():
        probe.calls.append("generator")
        yield from events

    return probe, {
        "sequence_len_raises": LenRaises(), "sequence_hostile_iter": HostileIter(), "duck_typed": Duck(),
        "list_subclass": ListSub(events), "tuple_subclass": TupleSub(events), "str": "not a log", "bytes": b"not a log",
        "dict": {"a": 1}, "set": {1, 2}, "frozenset": frozenset({1}), "int": 7, "float": 1.5, "object": object(),
        "iterator": iter(events), "generator": gen(), "range": range(3),
    }


CANDIDATE_IDS = ["sequence_len_raises", "sequence_hostile_iter", "duck_typed", "list_subclass", "tuple_subclass", "str", "bytes", "dict",
                 "set", "frozenset", "int", "float", "object", "iterator", "generator", "range"]


@pytest.mark.parametrize("kind", CANDIDATE_IDS)
def test_every_non_builtin_event_log_is_rejected_at_the_boundary_without_running_its_code(run, kind):
    run_dir, pin, records, events, skips, manifest = run
    probe, candidates = probed_candidates(events)
    result = call(list(records), event_log=candidates[kind], manifest=manifest)
    assert_controlled(result, "event_log", TypeError())
    assert TYPE_MSG in result.failures[0].detail
    assert probe.calls == []                                                             # nothing of the caller's was executed


@pytest.mark.parametrize("container", [list, tuple], ids=["list", "tuple"])
def test_builtin_list_and_tuple_event_logs_are_accepted(run, container):
    run_dir, pin, records, events, skips, manifest = run
    n = len(records)
    result = audit_pace(list(records), jsonl_count=n, wrapper_count=n, manifest_count=n, skips=dict(skips),
                        event_log=container(events), manifest=manifest)
    assert result.ok and all("input snapshot failed" not in f.detail for f in result.failures)


def test_the_boundary_policy_matches_what_verify_event_log_accepts(run):
    """verify_event_log accepts exactly list/tuple (it rejects everything else), so the audit boundary is no wider than it."""
    from tools.obs.eventlog import EventLogError, verify_event_log
    run_dir, pin, records, events, skips, manifest = run
    head = manifest.event_log_head
    verify_event_log(list(events), head, records)
    verify_event_log(tuple(events), head, records)
    _, candidates = probed_candidates(events)
    for kind in ("sequence_len_raises", "duck_typed", "dict", "set", "iterator", "generator"):
        with pytest.raises(EventLogError):
            verify_event_log(candidates[kind], head, records)


def test_none_event_log_is_still_allowed_and_fails_through_the_manifest_checks_not_the_boundary(run):
    run_dir, pin, records, events, skips, manifest = run
    result = call(list(records), manifest=manifest)
    assert not result.ok and all("input snapshot failed" not in f.detail for f in result.failures)


# ---- Fix 12 (F11-02): BaseException policy and hostile exception formatting ----
from tools.obs.audit import _MAX_FAILURE_TEXT, _safe_exception_text


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(3), GeneratorExit()], ids=lambda e: type(e).__name__)
def test_non_exception_base_exceptions_propagate_from_every_snapshot_input(run, exc):
    run_dir, pin, records, events, skips, manifest = run
    with pytest.raises(type(exc)):
        call(ExplodingList(records, exc))
    with pytest.raises(type(exc)):
        call(list(records), skips=ExplodingMapping({(1, "g"): 1}, exc))
    with pytest.raises(type(exc)):
        call(list(records), expected_boundaries=ExplodingList([1, 2], exc))


def test_a_base_exception_raised_while_formatting_an_ordinary_exception_propagates(run):
    class InterruptingStr(Exception):
        def __str__(self):
            raise KeyboardInterrupt()

    run_dir, pin, records, events, skips, manifest = run
    with pytest.raises(KeyboardInterrupt):
        call(ExplodingList(records, InterruptingStr("x")))


class StrRaisesRuntime(Exception):
    def __str__(self):
        raise RuntimeError("__str__ exploded")


class StrReturnsInt(Exception):
    def __str__(self):
        return 42


class StrReturnsNone(Exception):
    def __str__(self):
        return None


class StrReturnsHuge(Exception):
    def __str__(self):
        return "x" * 10_000


class HostileStr(str):
    def __format__(self, spec):
        raise RuntimeError("__format__ exploded")

    def __getitem__(self, item):
        raise RuntimeError("__getitem__ exploded")

    def __iter__(self):
        raise RuntimeError("__iter__ exploded")

    def __len__(self):
        raise RuntimeError("__len__ exploded")


class StrReturnsHostileSubclass(Exception):
    def __str__(self):
        return HostileStr("sub-class message")


class NameRaisesMeta(type):
    @property
    def __name__(cls):
        raise RuntimeError("__name__ exploded")


class NameNonStrMeta(type):
    @property
    def __name__(cls):
        return 12345


class NameHostileStrMeta(type):
    @property
    def __name__(cls):
        return HostileStr("HostileName")


class NameRaisesError(Exception, metaclass=NameRaisesMeta):
    pass


class NameNonStrError(Exception, metaclass=NameNonStrMeta):
    pass


class NameHostileStrError(Exception, metaclass=NameHostileStrMeta):
    pass


HOSTILE = [(StrRaisesRuntime("a"), "<message unavailable>"), (StrReturnsInt("a"), "<message unavailable>"),
           (StrReturnsNone("a"), "<message unavailable>"), (StrReturnsHuge("a"), "x" * 50),
           (StrReturnsHostileSubclass("a"), "sub-class message"), (NameRaisesError("m"), "m"), (NameNonStrError("m"), "m"),
           (NameHostileStrError("m"), "m")]
HOSTILE_IDS = ["str_raises_runtime", "str_returns_int", "str_returns_none", "str_huge", "str_returns_hostile_subclass", "name_raises",
               "name_non_str", "name_hostile_str"]


@pytest.mark.parametrize("exc,fragment", HOSTILE, ids=HOSTILE_IDS)
def test_hostile_exceptions_are_formatted_safely_and_capped(exc, fragment):
    text = _safe_exception_text(exc)
    assert type(text) is str and len(text) <= _MAX_FAILURE_TEXT == 300
    assert fragment in text


@pytest.mark.parametrize("exc,fragment", HOSTILE, ids=HOSTILE_IDS)
def test_hostile_exceptions_cannot_escape_the_snapshot_boundary(run, exc, fragment):
    run_dir, pin, records, events, skips, manifest = run
    result = call(ExplodingList(records, exc))
    assert isinstance(result, AuditResult) and not result.ok and result.checks() == {"a"}
    detail = result.failures[0].detail
    assert type(detail) is str and "input snapshot failed for records" in detail and len(detail) < 400


def test_fallback_kind_is_used_when_the_class_name_cannot_be_read():
    assert _safe_exception_text(NameRaisesError("m")).startswith("exception: ")
    assert _safe_exception_text(NameNonStrError("m")).startswith("12345: ")                # str(12345) is a legitimate plain text


def test_messages_over_300_characters_are_truncated_and_exactly_300_is_kept():
    long = _safe_exception_text(ValueError("y" * 5000))
    assert len(long) == 300 and long.startswith("ValueError: yyy")
    prefix = "ValueError: "
    exact = _safe_exception_text(ValueError("z" * (300 - len(prefix))))
    assert len(exact) == 300 and exact.endswith("z")
    assert len(_safe_exception_text(ValueError("z" * (300 - len(prefix) + 1)))) == 300


def test_control_characters_in_messages_are_neutralised():
    text = _safe_exception_text(ValueError("line1\nline2\x00\x1b[31mred"))
    assert "\n" not in text and "\x00" not in text and "\x1b" not in text and "line1?line2" in text


def test_a_very_long_class_name_is_capped_too():
    big = type("E" * 5000, (Exception,), {})
    assert len(_safe_exception_text(big("m"))) <= 300
