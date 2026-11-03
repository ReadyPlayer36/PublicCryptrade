"""Fix 9: audit_pace freezes the caller's records (and skips / boundaries) once, at entry. A list mutated while the audit runs
- between the digest check and later decisions, or during traversal - cannot change what the audit decides."""
import dataclasses

import pytest

from tests.tools.obs.test_manifest_trust_and_types import audit_with, run  # noqa: F401  (run is a fixture)
from tests.tools.obs.test_run_manifest_e2e import text
from tools.obs import audit as audit_module
from tools.obs.audit import audit_pace


def junk_record(template):
    return dataclasses.replace(template, seq=10**6, start_ns=1, end_ns=2, status=500)


MUTATIONS = {
    "clear": lambda live: live.clear(),
    "append_junk": lambda live: live.append(junk_record(live[0])),
    "reverse": lambda live: live.reverse(),
    "delete_first": lambda live: live.pop(0),
    "tamper_last_end": lambda live: live.__setitem__(-1, dataclasses.replace(live[-1], end_ns=live[-1].end_ns + 10**9, status=500)),
    "replace_with_empty": lambda live: live.__setitem__(slice(None), []),
}
# points inside audit_pace that run AFTER it began; each wrapper lets the real call finish, then mutates the caller's list
HOOKS = ["validate_and_snapshot_manifest", "records_digest", "verify_event_log", "abort_condition_seq"]


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
@pytest.mark.parametrize("hook", HOOKS)
def test_a_list_mutated_after_the_audit_began_cannot_change_the_outcome(run, monkeypatch, hook, mutation):
    run_dir, pin, records, events, skips, manifest = run
    baseline = audit_with(list(records), events, skips, manifest)
    assert baseline.ok
    live = list(records)
    real = getattr(audit_module, hook)
    fired = []

    def hooked(*args, **kwargs):
        result = real(*args, **kwargs)
        if not fired:
            MUTATIONS[mutation](live)                                                    # the caller's list changes mid-audit
            fired.append(True)
        return result

    monkeypatch.setattr(audit_module, hook, hooked)
    result = audit_with(live, events, skips, manifest)
    assert fired, f"{hook} was never reached"
    assert live != list(records)                                                         # the mutation really happened
    assert result.ok and result.failures == baseline.failures


def test_the_snapshot_preserves_a_failing_verdict_too(run, monkeypatch):
    """A run that FAILS must keep failing identically when the list is 'repaired' mid-audit to look clean."""
    run_dir, pin, records, events, skips, manifest = run
    bad = list(records)
    bad[1] = dataclasses.replace(bad[1], start_ns=bad[0].start_ns)                       # a pacing / ordering violation
    before = audit_pace(list(bad), jsonl_count=len(bad), wrapper_count=len(bad), manifest_count=len(bad))
    assert not before.ok
    live = list(bad)
    real = audit_module.abort_condition_seq

    def repair_then_continue(snapshot):
        out = real(snapshot)
        live[:] = list(records)                                                          # the live list is now the CLEAN original
        return out

    monkeypatch.setattr(audit_module, "abort_condition_seq", repair_then_continue)
    after = audit_pace(live, jsonl_count=len(bad), wrapper_count=len(bad), manifest_count=len(bad))
    assert not after.ok and after.failures == before.failures


def test_mutating_the_list_before_the_audit_is_still_caught_by_the_digest(run):
    run_dir, pin, records, events, skips, manifest = run
    live = list(records)
    live[0] = dataclasses.replace(live[0], end_ns=live[0].end_ns + 1)
    result = audit_with(live, events, skips, manifest)
    assert not result.ok and "records do not match the authenticated manifest" in text(result)


def test_skips_and_boundary_mappings_are_frozen_at_entry_too(run, monkeypatch):
    run_dir, pin, records, events, skips, manifest = run
    live_skips = dict(skips)
    real = audit_module.records_digest

    def digest_then_clear(rows):
        out = real(rows)
        live_skips.clear()                                                               # the decisions vanish from the caller's dict mid-audit
        return out

    monkeypatch.setattr(audit_module, "records_digest", digest_then_clear)
    result = audit_with(list(records), events, live_skips, manifest)
    assert result.ok and live_skips == {}


def test_a_generator_of_records_is_consumed_exactly_once(run):
    run_dir, pin, records, events, skips, manifest = run
    n = len(records)
    result = audit_pace(iter(list(records)), jsonl_count=n, wrapper_count=n, manifest_count=n, skips=skips, event_log=events, manifest=manifest)
    assert result.ok
