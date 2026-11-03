"""Evidence-bound provenance of decided_at_ns and the terminal timeline_end_ns (re-audit remediation).

Timestamps are trusted only when they match events of a hash-chained log that verifies against the manifest head digest and
against the recorded requests. Every test here is deterministic and offline."""
import hashlib
import json
from dataclasses import replace

import pytest

from tests.fixtures.obs_fakes import audit_all, recorded_events, verified_log_for
from tests.tools.obs.test_audit import evidence_case, rec, seq_of
from tools.obs.audit import audit_pace, validate_decision_evidence
from tools.obs.eventlog import (EVENT_DECISION, EVENT_TIMELINE_END, GENESIS, EventLogError, EventLogWriter, LogEvent, VerifiedEventLog,
                                records_digest, verify_event_log)
from tools.obs.params import MS, S
from tools.obs.pacer import OBS02_PROFILE


def skip_case(**kw):
    records, decision, boundary = evidence_case("g2", **kw)
    return records, decision, boundary, {(boundary, "g2"): decision}


def failures_text(result):
    return " | ".join(f.detail for f in result.failures)


# ---- API: bare scalars are no longer accepted ----
def test_audit_pace_has_no_bare_timeline_end_parameter():
    records, decision, boundary, skips = skip_case()
    with pytest.raises(TypeError):
        audit_pace(records, jsonl_count=len(records), wrapper_count=len(records), manifest_count=len(records), skips=skips, timeline_end_ns=10**15)


def test_validate_decision_evidence_rejects_a_missing_or_duck_typed_log():
    records, decision, boundary, _ = skip_case()
    previous = records[-1]

    class Duck:                                         # looks like a log, was never verified
        timeline_end = None

        def decision_event(self, *a):
            return None

    for fake in (None, Duck(), [], "log"):
        problems = validate_decision_evidence(decision, records, previous_record=previous, profile=OBS02_PROFILE, verified_log=fake,
                                              boundary_ms=boundary, group_name="g2")
        assert any("no verified event log was supplied" in p for p in problems), fake


def test_a_verified_log_cannot_be_forged_by_direct_construction():
    with pytest.raises(EventLogError, match="only be produced by verify_event_log"):
        VerifiedEventLog(())
    with pytest.raises(EventLogError):
        VerifiedEventLog((), object())


# ---- honest baseline ----
def test_an_honestly_recorded_terminal_skip_passes_the_full_audit():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips, timeline_end_ns=decision.decided_at_ns + 5 * S)
    assert [e.kind for e in events] == [EVENT_DECISION, EVENT_TIMELINE_END]
    assert audit_all(records, skips=skips, event_log=events, event_log_head=head).ok


# ---- fabricated timestamps: arithmetically consistent but unrecorded ----
def test_a_consistent_decision_without_any_log_is_rejected():
    records, decision, boundary, skips = skip_case()
    result = audit_pace(records, jsonl_count=len(records), wrapper_count=len(records), manifest_count=len(records), skips=skips)
    assert not result.ok and "no verified event log was supplied" in failures_text(result)


def test_a_consistent_decision_absent_from_a_valid_log_is_rejected():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, {}, timeline_end_ns=10**15)             # valid log, but it recorded no decision
    result = audit_all(records, skips=skips, event_log=events, event_log_head=head)
    assert not result.ok and "no recorded DECISION event" in failures_text(result) and "unrecorded" in failures_text(result)


def test_a_fabricated_but_arithmetically_consistent_decision_time_is_rejected():
    """decided before the pacer allowed a start: m_e = earliest start for ANY decided_at in [last_end, earliest]. A different
    decided_at passes every arithmetic rule, but only the recorded one is evidence."""
    last_end = evidence_case("g2")[0][-1].end_ns
    earliest = last_end + 600 * MS
    records, honest, boundary = evidence_case("g2", m_e_ns=earliest, decided_at_ns=last_end + 100 * MS)
    skips = {(boundary, "g2"): honest}
    events, head = recorded_events(records, skips)
    assert audit_all(records, skips=skips, event_log=events, event_log_head=head).ok
    fabricated = replace(honest, decided_at_ns=last_end + 200 * MS)                 # still <= m_e, still max(decided, earliest) == m_e
    arithmetic_only = validate_decision_evidence(fabricated, records, previous_record=records[-1], profile=OBS02_PROFILE,
                                                 verified_log=verified_log_for(records, {(boundary, "g2"): fabricated}), boundary_ms=boundary,
                                                 group_name="g2")
    assert arithmetic_only == []                                                      # consistent against ITS OWN (self-recorded) log ...
    result = audit_all(records, skips={(boundary, "g2"): fabricated}, event_log=events, event_log_head=head)
    assert not result.ok                                                              # ... but not against the log of the real run
    assert f"decided_at_ns {fabricated.decided_at_ns} does not match the recorded decision event ({honest.decided_at_ns})" in failures_text(result)


def test_a_fabricated_m_e_that_equals_a_valid_recomputation_but_is_not_recorded_is_rejected():
    records, honest, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    other = evidence_case("g2", m_e_ns=400 * S)[1]                                    # internally consistent, different m_e / decided_at
    result = audit_all(records, skips={(boundary, "g2"): replace(other, limit_ns=honest.limit_ns)}, event_log=events, event_log_head=head)
    assert not result.ok


def test_a_fabricated_timeline_end_is_rejected_even_when_consistent_with_the_decision():
    records, decision, boundary, skips = skip_case(m_e_ns=400 * S)
    real_events, real_head = recorded_events(records, skips, timeline_end_ns=10**15)
    # the run honestly ended at 200 s, i.e. BEFORE the decision instant: the recorded bound exposes the inflated decision
    short_events, short_head = recorded_events(records, skips, timeline_end_ns=200 * S)
    result = audit_all(records, skips=skips, event_log=short_events, event_log_head=short_head)
    assert not result.ok and "later than the audited timeline end" in failures_text(result)
    # a forger substituting a larger end-of-run value needs a new entry hash; the manifest head still names the real chain
    forged = recorded_events(records, skips, timeline_end_ns=500 * S)[0]
    result = audit_all(records, skips=skips, event_log=forged, event_log_head=short_head)
    assert not result.ok and "event log rejected" in failures_text(result) and "manifest digest" in failures_text(result)
    assert audit_all(records, skips=skips, event_log=real_events, event_log_head=real_head).ok


# ---- tampered log entries ----
def tamper(events, position, **changes):
    event = events[position]
    return events[:position] + (replace(event, **changes),) + events[position + 1:]


@pytest.fixture
def honest_run():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips)
    return records, skips, events, head


def test_a_tampered_field_is_rejected(honest_run):
    records, skips, events, head = honest_run
    fields = tuple((k, v + 1 if k == "decided_at_ns" else v) for k, v in events[0].fields)
    result = audit_all(records, skips=skips, event_log=tamper(events, 0, fields=fields), event_log_head=head)
    assert not result.ok and "entry hash does not match its content" in failures_text(result)


def test_a_tampered_entry_rehashed_by_the_forger_breaks_the_chain_and_the_manifest_digest(honest_run):
    records, skips, events, head = honest_run
    writer = EventLogWriter()
    for event in events:                                                                # forger replays the log with a shifted decision time
        if event.kind == EVENT_DECISION:
            writer.append_decision(boundary_ms=event.get("boundary_ms"), group_name=event.get("group_name"),
                                   decided_at_ns=event.get("decided_at_ns") + 1, m_e_ns=event.get("m_e_ns"), records=records[: event.records_before])
        else:
            writer.append_timeline_end(timeline_end_ns=event.get("timeline_end_ns"), records=records)
    assert writer.head_digest != head
    result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=head)
    assert not result.ok and "manifest digest" in failures_text(result)


def test_dropping_inserting_or_reordering_events_is_rejected(honest_run):
    records, skips, events, head = honest_run
    for mutated in (events[:1], events[1:], events + events[:1], (events[1], events[0])):
        with pytest.raises(EventLogError):
            verify_event_log(mutated, head, records)


def test_a_log_from_a_different_run_is_rejected_by_the_record_binding(honest_run):
    records, skips, events, head = honest_run
    other_records = [replace(r, end_ns=r.end_ns + 1) if r.seq == 1 else r for r in records]
    with pytest.raises(EventLogError, match="records digest does not match"):
        verify_event_log(events, head, other_records)
    assert not audit_all(other_records, skips=skips, event_log=events, event_log_head=head).ok


@pytest.mark.parametrize("head", [None, "", "abc", 7, "0" * 63])
def test_a_missing_or_malformed_manifest_digest_fails_closed(honest_run, head):
    records, skips, events, _ = honest_run
    with pytest.raises(EventLogError, match="manifest head digest"):
        verify_event_log(events, head, records)
    assert not audit_all(records, skips=skips, event_log=events, event_log_head=head).ok


def test_an_event_log_without_a_manifest_digest_or_a_digest_without_a_log_is_rejected(honest_run):
    records, skips, events, head = honest_run
    assert not audit_all(records, skips=skips, event_log=events).ok
    assert not audit_all(records, skips=skips, event_log_head=head).ok


def test_non_event_entries_are_rejected(honest_run):
    records, skips, events, head = honest_run
    with pytest.raises(EventLogError):
        verify_event_log([{"kind": "DECISION"}], head, records)
    with pytest.raises(EventLogError):
        verify_event_log(None, head, records)


# ---- missing / misplaced terminal event ----
def test_a_terminal_skip_without_a_timeline_end_event_is_unbounded_and_rejected():
    records, decision, boundary, skips = skip_case()
    events, head = recorded_events(records, skips, timeline_end_ns=None)
    result = audit_all(records, skips=skips, event_log=events, event_log_head=head)
    assert not result.ok and "no recorded TIMELINE_END event bounds the run" in failures_text(result)


def test_a_truncated_log_that_loses_its_terminal_event_is_rejected(honest_run):
    records, skips, events, head = honest_run
    result = audit_all(records, skips=skips, event_log=events[:-1], event_log_head=head)
    assert not result.ok and "manifest digest" in failures_text(result)


def test_the_timeline_end_must_be_final_and_cover_every_record():
    records, decision, boundary, skips = skip_case()
    writer = EventLogWriter()
    writer.append_timeline_end(timeline_end_ns=10**15, records=records)
    with pytest.raises(EventLogError, match="nothing may be appended"):
        writer.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=1, m_e_ns=1, records=records)
    early = EventLogWriter()                                                           # TIMELINE_END logged before the last record existed
    early.append_timeline_end(timeline_end_ns=10**15, records=records[:-1])
    result = audit_all(records, event_log=early.events, event_log_head=early.head_digest)
    assert not result.ok and f"TIMELINE_END was logged after {len(records) - 1} records but {len(records)} exist" in failures_text(result)
    backwards = EventLogWriter()                                                       # a decision after all records, then an earlier end
    backwards.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns, records=records)
    backwards.append_timeline_end(timeline_end_ns=10**15, records=records[:-1])
    with pytest.raises(EventLogError, match="non-decreasing record count"):
        verify_event_log(backwards.events, backwards.head_digest, records)


def test_a_timeline_end_before_the_last_completion_is_rejected_by_the_audit():
    records = seq_of([0, 600 * MS, 1200 * MS])
    events, head = recorded_events(records, None, timeline_end_ns=records[-1].end_ns - 1)
    result = audit_all(records, event_log=events, event_log_head=head)
    assert not result.ok and "precedes the last record's completion" in failures_text(result)


# ---- mismatched decision events ----
def test_a_decision_event_logged_for_another_group_or_boundary_does_not_bind_this_decision():
    records, decision, boundary, skips = skip_case()
    for group, b in (("g3", boundary), ("g2", boundary + 1)):
        writer = EventLogWriter()
        writer.append_decision(boundary_ms=b, group_name=group, decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns, records=records)
        writer.append_timeline_end(timeline_end_ns=10**15, records=records)
        result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=writer.head_digest)
        assert not result.ok and "no recorded DECISION event" in failures_text(result)


def test_a_decision_event_with_a_different_m_e_or_decision_time_is_rejected():
    records, decision, boundary, skips = skip_case()
    for changes, fragment in (({"decided_at_ns": decision.decided_at_ns - 1}, "does not match the recorded decision event"),
                              ({"m_e_ns": decision.m_e_ns + 1}, "m_e_ns")):
        values = {"decided_at_ns": decision.decided_at_ns, "m_e_ns": decision.m_e_ns, **changes}
        writer = EventLogWriter()
        writer.append_decision(boundary_ms=boundary, group_name="g2", records=records, **values)
        writer.append_timeline_end(timeline_end_ns=10**15, records=records)
        result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=writer.head_digest)
        assert not result.ok and fragment in failures_text(result)


def test_a_decision_logged_at_the_wrong_point_in_the_record_stream_is_rejected():
    records, decision, boundary, skips = skip_case()
    writer = EventLogWriter()
    writer.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns,
                           records=records[:-1])                                       # recorded before the preceding request completed
    writer.append_timeline_end(timeline_end_ns=10**15, records=records)
    result = audit_all(records, skips=skips, event_log=writer.events, event_log_head=writer.head_digest)
    assert not result.ok and "not right after record" in failures_text(result)


def test_duplicate_decision_events_for_one_group_are_rejected():
    records, decision, boundary, skips = skip_case()
    writer = EventLogWriter()
    for _ in range(2):
        writer.append_decision(boundary_ms=boundary, group_name="g2", decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns, records=records)
    with pytest.raises(EventLogError, match="duplicate decision"):
        verify_event_log(writer.events, writer.head_digest, records)


# ---- the hash construction itself (independent recomputation) ----
def test_the_chain_hash_is_the_documented_sha256_of_canonical_json():
    records = seq_of([0, 600 * MS])
    writer = EventLogWriter()
    event = writer.append_timeline_end(timeline_end_ns=123, records=records)
    manual_records = hashlib.sha256()
    for r in records:
        line = json.dumps([r.seq, r.role, r.path, r.start_ns, r.end_ns, r.status, r.error, r.group_name, r.group_kind, r.boundary_ms,
                           hashlib.sha256(bytes(r.body)).hexdigest(), []], separators=(",", ":"), sort_keys=True)
        manual_records.update(line.encode() + b"\n")
    assert event.records_digest == manual_records.hexdigest() == records_digest(records)
    payload = json.dumps([GENESIS, 0, "TIMELINE_END", [["timeline_end_ns", 123]], 2, manual_records.hexdigest()], separators=(",", ":"), sort_keys=True)
    assert event.entry_hash == hashlib.sha256(payload.encode()).hexdigest() == writer.head_digest
    assert event.prev_hash == GENESIS and isinstance(event, LogEvent)


def test_a_body_change_in_any_record_changes_the_digest():
    records = seq_of([0, 600 * MS])
    changed = [replace(records[0], body=b"x"), records[1]]
    assert records_digest(records) != records_digest(changed)
    assert records_digest(records[:1]) != records_digest(records)
