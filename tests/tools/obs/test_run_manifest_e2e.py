"""End to end: persist records + hash-chained event log + run manifest, reload from disk, authenticate against an out-of-band
pinned digest, and prove that tampering, substitution and head-digest edits fail closed. Offline and deterministic."""
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fixtures.obs_fakes import recorded_events
from tests.tools.obs.test_audit import evidence_case
from tools.obs import runstore
from tools.obs.audit import audit_pace, audit_run
from tools.obs.eventlog import EVENT_DECISION, EventLogWriter
from tools.obs.runstore import AuthenticatedManifest, ManifestError, load_manifest, load_run, write_run
from tools.obs.params import S


def build_run(tmp_path: Path, name="run", with_decision=True, timeline_end_ns=10**15):
    records, decision, boundary = evidence_case("g2")
    skips = {(boundary, "g2"): decision}
    events, _ = recorded_events(records, skips if with_decision else {}, timeline_end_ns)
    run_dir = tmp_path / name
    pin = write_run(run_dir, records, events)
    return run_dir, pin, records, events, skips


def audit(run_dir, pin, skips, records):
    return audit_run(run_dir, pinned_manifest_sha256=pin, wrapper_count=len(records), skips=skips)


def text(result):
    return " | ".join(f.detail for f in result.failures)


def rewrite_manifest(run_dir, **changes):
    """A forger edits manifest fields and RE-COMPUTES the self-digest; returns the new file's SHA-256."""
    path = run_dir / runstore.MANIFEST_FILE
    data = json.loads(path.read_text())
    data.update(changes)
    data["manifest_digest"] = runstore._manifest_self_digest(data)
    raw = (runstore._canonical(data) + "\n").encode()
    path.write_bytes(raw)
    return runstore._sha256(raw)


# ---- the honest workflow ----
def test_a_complete_run_round_trips_through_disk_and_passes_the_audit(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    assert sorted(p.name for p in run_dir.iterdir()) == ["events.jsonl", "manifest.json", "records.jsonl"]
    loaded = load_run(run_dir, pinned_manifest_sha256=pin)
    assert list(loaded.records) == records and list(loaded.events) == list(events)            # bodies, headers, fields all preserved
    assert loaded.manifest.manifest_sha256 == pin and loaded.manifest.event_log_head == events[-1].entry_hash
    result = audit(run_dir, pin, skips, records)
    assert result.ok, text(result)
    assert any(e.kind == EVENT_DECISION for e in loaded.events)


def test_the_head_digest_comes_only_from_the_authenticated_manifest(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    with pytest.raises(TypeError):                                                            # no scalar head parameter exists any more
        audit_pace(records, event_log=events, event_log_head=events[-1].entry_hash)
    result = audit_pace(records, jsonl_count=len(records), wrapper_count=len(records), manifest_count=len(records), skips=skips, event_log=events)
    assert not result.ok and "no authenticated run manifest was supplied" in text(result)
    with pytest.raises(ManifestError, match="only be produced by load_manifest"):
        AuthenticatedManifest(len(records), "0" * 64, "0" * 64, len(events), "0" * 64, events[-1].entry_hash, "0" * 64)


def test_run_artifacts_are_written_once_and_an_inconsistent_run_is_not_persisted(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    with pytest.raises(ManifestError, match="already exists"):
        write_run(run_dir, records, events)
    tampered = [replace(records[0], end_ns=records[0].end_ns + 1)] + records[1:]
    with pytest.raises(ManifestError, match="refusing to persist an inconsistent run"):
        write_run(tmp_path / "other", tampered, events)


# ---- manifest missing / malformed ----
def test_a_missing_manifest_or_artifact_fails_closed(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    for name in (runstore.MANIFEST_FILE, runstore.RECORDS_FILE, runstore.EVENTS_FILE):
        broken = tmp_path / f"missing-{name}"
        shutil.copytree(run_dir, broken)
        (broken / name).unlink()
        result = audit(broken, pin, skips, records)
        assert not result.ok and "run rejected" in text(result) and "missing or unreadable" in text(result), name
    assert not audit(tmp_path / "no-such-dir", pin, skips, records).ok


@pytest.mark.parametrize("pin", [None, "", "abc", 7, "G" * 64, "A" * 64, "0" * 63])
def test_a_missing_or_malformed_pinned_digest_fails_closed(tmp_path, pin):
    run_dir, good, records, events, skips = build_run(tmp_path)
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "pinned manifest SHA-256 is missing or malformed" in text(result)


def test_a_wrong_pin_fails_closed(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    result = audit(run_dir, "0" * 64, skips, records)
    assert not result.ok and "does not match the pinned SHA-256" in text(result)


@pytest.mark.parametrize("mutate,fragment", [
    (lambda raw: b"not json\n", "not valid JSON"),
    (lambda raw: b"[]\n", "unexpected or missing keys"),
    (lambda raw: raw[:-1].rstrip(b"}") + b',"format":"x"}\n', "duplicate JSON key"),
    (lambda raw: raw[:-1].rstrip(b"}") + b',"extra":1}\n', "unexpected or missing keys"),
    (lambda raw: raw.replace(b"obs-run-manifest/1", b"obs-run-manifest/2"), "unsupported manifest format"),
    (lambda raw: raw[: len(raw) // 2], "not valid JSON"),
    (lambda raw: b"\xff\xfe", "not valid JSON"),
])
def test_a_malformed_manifest_is_rejected_even_with_a_matching_pin(tmp_path, mutate, fragment):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    path = run_dir / runstore.MANIFEST_FILE
    mutated = mutate(path.read_bytes())
    path.write_bytes(mutated)
    with pytest.raises(ManifestError, match=fragment):
        load_manifest(path, pinned_sha256=runstore._sha256(mutated))                          # attacker re-pins: structure still rejected


# ---- tampering with the persisted manifest ----
def test_editing_the_manifest_without_the_pin_is_detected(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    path = run_dir / runstore.MANIFEST_FILE
    path.write_bytes(path.read_bytes().replace(b'"record_count":', b'"record_count": ', 1))   # even a whitespace edit changes the bytes
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "does not match the pinned SHA-256" in text(result)


def test_editing_a_manifest_field_breaks_the_self_digest_even_if_the_forger_re_pins(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    path = run_dir / runstore.MANIFEST_FILE
    data = json.loads(path.read_text())
    data["event_log_head"] = "1" * 64                                                          # forger swaps the head, forgets the self-digest
    raw = (runstore._canonical(data) + "\n").encode()
    path.write_bytes(raw)
    with pytest.raises(ManifestError, match="self-digest does not verify"):
        load_manifest(path, pinned_sha256=runstore._sha256(raw))


def test_a_fully_re_digested_forged_manifest_is_rejected_by_the_original_pin(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    new_pin = rewrite_manifest(run_dir, event_log_head="1" * 64)                               # consistent forgery, new pin chosen by the forger
    assert new_pin != pin
    assert not audit(run_dir, pin, skips, records).ok                                          # the independently recorded pin wins
    forged = audit(run_dir, new_pin, skips, records)                                           # (even a forger-chosen pin cannot make the log fit)
    assert not forged.ok and "manifest" in text(forged)


def test_altering_the_head_digest_to_fit_a_substituted_log_is_rejected(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    forged = EventLogWriter()                                                                  # a different, internally valid log with a later decision time
    for event in events:
        if event.kind == EVENT_DECISION:
            forged.append_decision(boundary_ms=event.get("boundary_ms"), group_name=event.get("group_name"), decided_at_ns=event.get("decided_at_ns") + 1,
                                   m_e_ns=event.get("m_e_ns"), records=records[: event.records_before])
        else:
            forged.append_timeline_end(timeline_end_ns=event.get("timeline_end_ns"), records=records)
    forged_dir = tmp_path / "forged"
    forged_pin = write_run(forged_dir, records, forged.events)                                 # internally consistent run + manifest + pin
    own = audit(forged_dir, forged_pin, skips, records)                                        # authenticates against its own pin, but the forged time still mismatches the decision
    assert not own.ok and "does not match the recorded decision event" in text(own)
    assert not audit(forged_dir, pin, skips, records).ok                                       # ... never against the pin of the real run
    swapped = tmp_path / "swapped"
    shutil.copytree(run_dir, swapped)
    shutil.copy(forged_dir / runstore.EVENTS_FILE, swapped / runstore.EVENTS_FILE)             # logs substituted inside the real run directory
    result = audit(swapped, pin, skips, records)
    assert not result.ok and "events.jsonl does not match the manifest digest" in text(result)
    new_pin = rewrite_manifest(swapped, event_log_head=forged.head_digest, events_file_sha256=runstore._sha256((swapped / runstore.EVENTS_FILE).read_bytes()))
    assert not audit(swapped, pin, skips, records).ok                                          # re-pinned by the forger, rejected by the real pin
    assert new_pin != pin


# ---- tampering with persisted evidence ----
@pytest.mark.parametrize("name", [runstore.RECORDS_FILE, runstore.EVENTS_FILE])
def test_any_byte_change_in_a_persisted_file_is_detected(tmp_path, name):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    path = run_dir / name
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "does not match the manifest digest" in text(result)


def test_a_records_file_from_another_run_is_rejected(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    other_dir, other_pin, _, _, _ = build_run(tmp_path, name="other", timeline_end_ns=5 * 10**14)
    shutil.copy(other_dir / runstore.EVENTS_FILE, run_dir / runstore.EVENTS_FILE)
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "events.jsonl does not match the manifest digest" in text(result)


def test_a_truncated_jsonl_file_is_rejected_even_when_re_pinned(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    path = run_dir / runstore.EVENTS_FILE
    raw = path.read_bytes()
    path.write_bytes(raw[:-1])
    new_pin = rewrite_manifest(run_dir, events_file_sha256=runstore._sha256(raw[:-1]))
    result = audit(run_dir, new_pin, skips, records)
    assert not result.ok and "truncated" in text(result)


def test_dropping_the_terminal_event_from_a_persisted_run_is_rejected(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    lines = (run_dir / runstore.EVENTS_FILE).read_bytes().splitlines(keepends=True)
    (run_dir / runstore.EVENTS_FILE).write_bytes(b"".join(lines[:-1]))
    new_pin = rewrite_manifest(run_dir, events_file_sha256=runstore._sha256(b"".join(lines[:-1])), event_count=len(lines) - 1)
    result = audit(run_dir, new_pin, skips, records)
    assert not result.ok and "manifest digest" in text(result)                                 # head still names the full chain


def test_a_persisted_run_without_a_recorded_decision_cannot_justify_a_skip(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path, name="nodecision", with_decision=False)
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "no recorded DECISION event" in text(result)


def test_a_persisted_run_without_a_timeline_end_cannot_bound_a_terminal_skip(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path, name="noend", timeline_end_ns=None)
    result = audit(run_dir, pin, skips, records)
    assert not result.ok and "no recorded TIMELINE_END event bounds the run" in text(result)


def test_record_count_and_digest_in_the_manifest_must_match_the_records_audited(tmp_path):
    run_dir, pin, records, events, skips = build_run(tmp_path)
    manifest = load_manifest(run_dir / runstore.MANIFEST_FILE, pinned_sha256=pin)
    result = audit_pace(records[:-1], jsonl_count=len(records) - 1, wrapper_count=len(records) - 1, manifest_count=len(records) - 1,
                        event_log=events, manifest=manifest)
    assert not result.ok and "do not match the authenticated manifest" in text(result)
