"""Deterministic provenance regressions: tampered log entries, missing terminal events and mismatched decision timestamps.

Complements test_provenance.py. Every test is offline and deterministic (no clock, no randomness, no I/O beyond the
manifest loader's temp file). Honest controls prove each rejection is caused by the tampering, not by the fixture."""
from dataclasses import replace

import pytest

from tests.fixtures.obs_fakes import audit_all, recorded_events
from tests.tools.obs.test_audit import boundary_records, renumber
from tests.tools.obs.test_provenance import skip_case, tamper
from tools.obs.eventlog import EVENT_DECISION, EVENT_TIMELINE_END, EventLogWriter, _entry_hash

BOUNDARY = 1_700_000_100_000
MISSING_TERMINAL = "the event log has no TIMELINE_END event: the end of the run is unrecorded (missing terminal event)"


def text(result):
    return " | ".join(f.detail for f in result.failures)


@pytest.fixture
def clean_run():
    return renumber(boundary_records(BOUNDARY, 20_000_000_000))


@pytest.fixture
def skip_run():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    return records, decision, boundary, skips, events, head


def rehash(event, **changes):
    """What a careful forger does: change a field AND recompute that entry's own hash."""
    changed = replace(event, **changes)
    return replace(changed, entry_hash=_entry_hash(changed.prev_hash, changed.index, changed.kind, changed.fields,
                                                   changed.records_before, changed.records_digest))


# ------------------------------------------------------------------------------------------------ controls
def test_honest_runs_pass_so_every_rejection_below_is_caused_by_the_tampering(clean_run, skip_run):
    events, head = recorded_events(clean_run, None)
    assert audit_all(clean_run, event_log=events, event_log_head=head).ok
    records, _, _, skips, sk_events, sk_head = skip_run
    assert audit_all(records, skips=skips, event_log=sk_events, event_log_head=sk_head).ok


# ------------------------------------------------------------------------------------------------ missing terminal events
def test_a_clean_run_without_a_timeline_end_event_is_rejected_with_the_exact_message(clean_run):
    events, head = recorded_events(clean_run, None, timeline_end_ns=None)
    assert events == ()
    result = audit_all(clean_run, event_log=events, event_log_head=head)
    assert not result.ok and [f.detail for f in result.failures] == [MISSING_TERMINAL]


def test_a_self_consistent_log_truncated_before_its_terminal_event_is_rejected(skip_run):
    records, _, _, skips, events, _ = skip_run
    assert [e.kind for e in events] == [EVENT_DECISION, EVENT_TIMELINE_END]
    prefix = events[:1]                                            # the forger also re-points the manifest head at the prefix
    result = audit_all(records, skips=skips, event_log=prefix, event_log_head=prefix[0].entry_hash)
    assert not result.ok and MISSING_TERMINAL in text(result)


def test_a_truncated_log_with_the_original_head_is_rejected_by_the_chain_head(skip_run):
    records, _, _, skips, events, head = skip_run
    result = audit_all(records, skips=skips, event_log=events[:-1], event_log_head=head)
    assert not result.ok and "manifest digest" in text(result)


def test_a_timeline_end_that_does_not_cover_every_record_is_rejected(clean_run):
    writer = EventLogWriter()
    writer.append_timeline_end(timeline_end_ns=10**15, records=clean_run[:-1])    # logged before the last record completed
    result = audit_all(clean_run, event_log=writer.events, event_log_head=writer.head_digest)
    assert not result.ok and f"TIMELINE_END was logged after {len(clean_run) - 1} records but {len(clean_run)} exist" in text(result)


def test_nothing_can_be_appended_after_the_terminal_event():
    writer = EventLogWriter()
    writer.append_timeline_end(timeline_end_ns=1, records=[])
    with pytest.raises(Exception, match="the timeline has ended; nothing may be appended"):
        writer.append_timeline_end(timeline_end_ns=2, records=[])


# ------------------------------------------------------------------------------------------------ unexplained decisions
def test_a_decision_event_for_a_group_that_was_actually_sent_is_rejected(clean_run):
    writer = EventLogWriter()
    writer.append_decision(boundary_ms=BOUNDARY, group_name="g2", decided_at_ns=clean_run[0].end_ns, m_e_ns=clean_run[0].end_ns,
                           records=clean_run[:1])
    writer.append_timeline_end(timeline_end_ns=10**15, records=clean_run)
    result = audit_all(clean_run, event_log=writer.events, event_log_head=writer.head_digest)
    assert not result.ok
    assert [f.detail for f in result.failures] == [f"DECISION event for ({BOUNDARY}, 'g2') matches no audited skip: "
                                                    "an unexplained decision timestamp is never accepted"]


def test_an_extra_decision_event_next_to_an_honest_skip_is_rejected(skip_run):
    records, decision, boundary, skips, _, _ = skip_run
    writer = EventLogWriter()
    writer.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns, records=records)
    writer.append_decision(boundary_ms=boundary, group_name="g3", decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns, records=records)
    writer.append_timeline_end(timeline_end_ns=10**15, records=records)
    result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=writer.head_digest)
    assert not result.ok and f"DECISION event for ({boundary}, 'g3') matches no audited skip" in text(result)


# ------------------------------------------------------------------------------------------------ tampered entries, exhaustive
def _tamper_cases():
    records, decision, boundary, skips = skip_case()
    events, _ = recorded_events(records, skips)
    cases = []
    for position, event in enumerate(events):
        for index, (key, value) in enumerate(event.fields):
            if isinstance(value, int):
                cases.append((position, "field", index, key, value + 1))
                cases.append((position, "field", index, key, value - 1))
            else:
                cases.append((position, "field", index, key, value + "x"))
        cases.append((position, "records_before", None, "records_before", event.records_before + 1))
        cases.append((position, "records_digest", None, "records_digest", "f" * 64))
        cases.append((position, "kind", None, "kind", EVENT_TIMELINE_END if event.kind == EVENT_DECISION else EVENT_DECISION))
    return cases


@pytest.mark.parametrize("position,what,index,key,value", _tamper_cases(), ids=lambda v: str(v)[:24])
def test_every_single_field_edit_of_every_event_is_rejected_with_and_without_rehashing(position, what, index, key, value, skip_run):
    records, _, _, skips, events, head = skip_run
    event = events[position]
    if what == "field":
        fields = list(event.fields)
        fields[index] = (key, value)
        change = {"fields": tuple(fields)}
    else:
        change = {key: value}
    naive = tamper(events, position, **change)                      # edit only: the entry hash no longer matches its content
    assert not audit_all(records, skips=skips, event_log=naive, event_log_head=head).ok
    forged = events[:position] + (rehash(event, **change),) + events[position + 1:]
    result = audit_all(records, skips=skips, event_log=forged, event_log_head=head)     # entry rehashed: chain or head breaks
    assert not result.ok
    refreshed = list(forged)
    for later in range(position + 1, len(refreshed)):                # forger rehashes the WHOLE tail too, but cannot fix the manifest head
        refreshed[later] = rehash(refreshed[later], prev_hash=refreshed[later - 1].entry_hash)
    assert not audit_all(records, skips=skips, event_log=tuple(refreshed), event_log_head=head).ok


def test_a_fully_rechained_forgery_is_accepted_only_if_the_head_is_also_rewritten_which_the_audit_then_cannot_see(skip_run):
    """Stated limit (eventlog.py docstring): whoever controls records, log AND manifest head together can forge a consistent
    triple. The defence is the out-of-band manifest pin. Even then the forged TIMELINE_END is checked against the records."""
    records, _, _, skips, events, _ = skip_run
    forged = list(events)
    forged[-1] = rehash(events[-1], fields=(("timeline_end_ns", records[-1].end_ns - 1),))
    result = audit_all(records, skips=skips, event_log=tuple(forged), event_log_head=forged[-1].entry_hash)
    assert not result.ok and "precedes the last record's completion" in text(result)


# ------------------------------------------------------------------------------------------------ mismatched decision timestamps
@pytest.mark.parametrize("field", ["decided_at_ns", "m_e_ns"])
@pytest.mark.parametrize("delta", [-1_000_000_000, -1, 1, 1_000_000_000])
def test_a_decision_whose_timestamps_differ_from_the_logged_event_is_rejected(field, delta, skip_run):
    records, decision, boundary, skips, events, head = skip_run
    forged = replace(decision, **{field: getattr(decision, field) + delta})
    result = audit_all(records, skips={(boundary, "g2"): forged}, event_log=events, event_log_head=head)
    assert not result.ok


def test_a_decision_with_no_logged_event_is_rejected_even_if_consistent(skip_run):
    records, decision, boundary, skips, _, _ = skip_run
    events, head = recorded_events(records, None)                   # honest log of a run in which no skip was decided
    result = audit_all(records, skips=skips, event_log=events, event_log_head=head)
    assert not result.ok and f"no recorded DECISION event for ({boundary}, g2)" in text(result)


def test_a_decision_logged_with_other_timestamps_than_it_claims_names_the_mismatch(skip_run):
    records, decision, boundary, skips, _, _ = skip_run
    writer = EventLogWriter()
    writer.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=decision.decided_at_ns - 1, m_e_ns=decision.m_e_ns,
                           records=records[:records[-1].seq])
    writer.append_timeline_end(timeline_end_ns=10**15, records=records)
    result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=writer.head_digest)
    assert not result.ok
    assert f"decided_at_ns {decision.decided_at_ns} does not match the recorded decision event ({decision.decided_at_ns - 1})" in text(result)


# ------------------------------------------------------------------------------------------------ forgeries that are hash-consistent
def forge_chain(records, specs):
    """A forger who recomputes EVERY hash. specs: (index, kind, fields, records_before). Returns (events, head)."""
    from tools.obs.eventlog import GENESIS, LogEvent, records_digest
    events, prev = [], GENESIS
    for index, kind, fields, before in specs:
        fields = tuple(sorted(fields))
        digest = records_digest(records[:before])
        entry = _entry_hash(prev, index, kind, fields, before, digest)
        events.append(LogEvent(index, kind, fields, before, digest, prev, entry))
        prev = entry
    return tuple(events), prev


def test_a_schema_valid_edit_of_an_early_entry_breaks_the_link_to_the_next_entry(skip_run):
    from tools.obs.eventlog import EventLogError, verify_event_log
    records, _, _, _, events, head = skip_run
    fields = dict(events[0].fields)
    fields["m_e_ns"] += 1                                                  # a value no schema rule can object to
    edited = rehash(events[0], fields=tuple(sorted(fields.items())))       # only this entry rehashed
    forged = (edited,) + events[1:]
    assert forged[-1].entry_hash == head                                   # the head digest alone cannot see this edit
    with pytest.raises(EventLogError, match=r"event 1: prev_hash does not link to the previous entry"):
        verify_event_log(forged, head, records)
    assert not audit_all(records, skips=skip_run[3], event_log=forged, event_log_head=head).ok


def test_a_consistent_chain_with_a_terminal_event_in_the_middle_is_rejected(skip_run):
    from tools.obs.eventlog import EventLogError, verify_event_log
    records = skip_run[0]
    events, head = forge_chain(records, [(0, EVENT_TIMELINE_END, (("timeline_end_ns", 5),), len(records)),
                                         (1, EVENT_TIMELINE_END, (("timeline_end_ns", 10**15),), len(records))])
    with pytest.raises(EventLogError, match=r"event 0: TIMELINE_END must be the final event"):
        verify_event_log(events, head, records)


def test_a_consistent_chain_with_a_non_sequential_index_is_rejected(skip_run):
    from tools.obs.eventlog import EventLogError, verify_event_log
    records = skip_run[0]
    events, head = forge_chain(records, [(0, EVENT_DECISION, (("boundary_ms", 1), ("decided_at_ns", 1), ("group_name", "g2"), ("m_e_ns", 1)), 1),
                                         (2, EVENT_TIMELINE_END, (("timeline_end_ns", 10**15),), len(records))])
    with pytest.raises(EventLogError, match=r"event 1: index 2 breaks the sequence"):
        verify_event_log(events, head, records)


def test_the_forgery_helper_produces_an_acceptable_log_when_nothing_is_wrong(skip_run):
    from tools.obs.eventlog import verify_event_log
    records = skip_run[0]
    events, head = forge_chain(records, [(0, EVENT_TIMELINE_END, (("timeline_end_ns", 10**15),), len(records))])
    assert verify_event_log(events, head, records).timeline_end is not None      # control: the helper is not itself invalid
