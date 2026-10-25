"""PACE-5 audit checks (a)-(g), hardened to fail closed: abort handling, group metadata, verified skips, required counters."""
from dataclasses import replace
from fractions import Fraction as F

import pytest

from tests.fixtures.obs_fakes import audit_all
from tools.obs.admission import AdmissionDecision
from tools.obs.audit import audit_pace, abort_condition_seq
from tools.obs.pacer import OBS01_PROFILE, RequestRecord
from tools.obs.params import KLINES_PATH, MS, S, TIME_PATH
from tools.obs.transport import CANCEL_FAILED, CONNECT_ERROR, DEADLINE

ROLES_4TF = ("S1", "K4h", "K1h", "K15m", "K5m", "S2")
ROLES_5M = ("S1", "K5m", "S2")
PATH = {"T": TIME_PATH, "S1": TIME_PATH, "S2": TIME_PATH, "K4h": KLINES_PATH, "K1h": KLINES_PATH, "K15m": KLINES_PATH, "K5m": KLINES_PATH,
        "SWEEP": KLINES_PATH, "PREREG": KLINES_PATH, "PROBE": KLINES_PATH}


def rec(seq, start, end=None, *, status=200, error=None, role="PROBE", group=None, kind=None, boundary=None, path=None):
    return RequestRecord(seq=seq, role=role, path=path or PATH.get(role, TIME_PATH), start_ns=start, end_ns=start if end is None else end,
                         status=status, error=error, group_name=group, group_kind=kind, boundary_ms=boundary)


def seq_of(starts, **kw):
    return [rec(i + 1, s, **kw) for i, s in enumerate(starts)]


def checks(records, **kw):
    return audit_all(records, **kw).checks()


def renumber(records):
    return [replace(r, seq=i + 1) for i, r in enumerate(records)]


def group(name, roles, kind, boundary, t0, gap=600 * MS):
    return [rec(1, t0 + i * gap, role=role, group=name, kind=kind, boundary=boundary) for i, role in enumerate(roles)]


def boundary_records(boundary, t0, names=("resync", "g0", "g1", "g2", "g3", "ref"), kind="5m", roles=ROLES_5M):
    """One boundary with the given groups; each group starts 12 s after the previous one (caps never bind)."""
    out = []
    for i, name in enumerate(names):
        if name == "resync":
            out += group("resync", ("T", "T", "T"), None, boundary, t0 + i * 12 * S)
        else:
            out += group(name, roles, kind, boundary, t0 + i * 12 * S)
    return out


def missed_window_decision(**over):
    values = dict(admitted=False, m_e_ns=100 * S, theta_lo=F(1), theta_hi=F(2), lower_server_ns=F(1_000_000_001), upper_server_ns=F(1_000_000_002),
                  limit_ns=1_000_000_000, reason="MISSED-WINDOW")
    values.update(over)
    return AdmissionDecision(**values)


# ---- clean runs ----
def test_a_clean_sequence_passes():
    assert audit_all(seq_of([k * 600 * MS for k in range(10)])).ok
    assert audit_all([]).ok


def test_a_complete_boundary_with_all_groups_passes():
    records = renumber(boundary_records(1000, 0) + boundary_records(2000, 300 * S))
    assert audit_all(records).ok


# ---- (a) integrity ----
def test_a_sequence_must_be_contiguous_from_one():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert "a" in checks([records[0], replace(records[2], seq=3)])
    assert "a" in checks([replace(records[0], seq=2), records[1]])
    assert "a" in checks([records[0], replace(records[1], seq=1)])


def test_a_timestamps_must_be_plain_integers_and_not_regress():
    records = seq_of([0, 600 * MS])
    assert "a" in checks([records[0], replace(records[1], start_ns=600.0 * MS)])
    assert "a" in checks([records[0], replace(records[1], start_ns=True)])
    assert "a" in checks([replace(records[0], end_ns=-1)])
    assert "a" in checks([rec(1, 900 * MS), rec(2, 100 * MS)])


@pytest.mark.parametrize("status", [301, 302, 403, 418, 429, 500, 503, 204])
def test_a_nothing_may_follow_a_non_200_response_even_without_an_abort_record(status):
    records = [rec(1, 0), rec(2, 600 * MS, status=status), rec(3, 1200 * MS)]
    result = audit_all(records)
    assert "a" in result.checks()                                                   # the records alone show the violation
    assert any("after the abort condition" in f.detail for f in result.failures)
    assert "a" in checks(records, abort_seq=3)                                       # a later abort position does not excuse it


@pytest.mark.parametrize("status", [302, 403, 418, 429, 500])
def test_a_a_final_non_200_response_needs_the_matching_recorded_abort_position(status):
    records = [rec(1, 0), rec(2, 600 * MS, status=status)]
    assert audit_all(records, abort_seq=2).ok
    assert "a" in checks(records)                                                    # abort condition but no abort recorded
    assert "a" in checks(records, abort_seq=1)
    assert "a" in checks(records, abort_seq=3)


def test_a_three_consecutive_requests_without_a_response_must_end_the_run():
    failed = [rec(i + 1, i * 600 * MS, status=None, error=CONNECT_ERROR) for i in range(3)]
    assert abort_condition_seq(failed) == 3
    assert audit_all(failed, abort_seq=3).ok
    assert "a" in checks(failed + [rec(4, 1800 * MS)], abort_seq=3)
    assert "a" in checks(failed + [rec(4, 1800 * MS)])
    two = failed[:2] + [rec(3, 1200 * MS), rec(4, 1800 * MS)]                       # a response in between resets the streak
    assert abort_condition_seq(two) is None and audit_all(two).ok


def test_a_a_failed_cancellation_must_end_the_run():
    records = [rec(1, 0, 18 * S, status=None, error=CANCEL_FAILED)]
    assert abort_condition_seq(records) == 1 and audit_all(records, abort_seq=1).ok
    assert "a" in checks(records + [rec(2, 19 * S)], abort_seq=1)
    assert "a" in checks(records)


def test_a_an_explicit_abort_position_must_equal_the_number_of_records():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert audit_all(records, abort_seq=3).ok
    assert "a" in checks(records, abort_seq=2)
    assert "a" in checks(records, abort_seq=4)


# ---- (b) completion ordering and non-overlap, (c) spacing ----
def test_b_a_request_may_not_start_before_the_previous_completed():
    assert "b" in checks([rec(1, 0, 900 * MS), rec(2, 700 * MS, 800 * MS)])
    assert audit_all([rec(1, 0, 600 * MS), rec(2, 600 * MS, 700 * MS)]).ok            # end == next start is allowed
    assert "b" in checks([rec(1, 0, 5 * S), rec(2, 700 * MS, 800 * MS)])


def test_c_spacing_is_an_exact_integer_comparison():
    assert audit_all(seq_of([0, 600_000_000])).ok
    assert "c" in checks(seq_of([0, 599_999_999]))
    assert "c" in checks(seq_of([0, 600 * MS, 700 * MS]))


# ---- (d) rolling caps with open-left / closed-right windows ----
def test_d_one_second_cap_boundaries_gv8_ii():
    assert "d" not in checks(seq_of([0, 600 * MS, 1_000_000_000]))
    assert "c" in checks(seq_of([0, 600 * MS, 1_000_000_000]))
    assert "d" in checks(seq_of([0, 600 * MS, 999_999_999]))


def test_d_sixty_second_cap_boundaries_gv8_i():
    assert audit_all(seq_of([k * S for k in range(61)])).ok
    assert checks(seq_of([k * S for k in range(60)] + [59_999_999_999])) == {"d"}


def test_d_obs01_profile_caps_are_one_per_two_seconds_and_thirty_per_minute():
    assert audit_all(seq_of([0, 2 * S, 4 * S]), profile=OBS01_PROFILE).ok
    assert checks(seq_of([0, 1_999_999_999]), profile=OBS01_PROFILE) == {"c", "d"}
    assert audit_all(seq_of([k * 2 * S for k in range(31)]), profile=OBS01_PROFILE).ok
    assert "d" in checks(seq_of([k * 2 * S for k in range(30)] + [59_999_999_999]), profile=OBS01_PROFILE)


# ---- (e) durations ----
def test_e_durations_backstop_gv9():
    assert "e" in checks([rec(1, 0, 18_000_000_001)])
    assert audit_all([rec(1, 0, 18_000_000_000)]).ok
    assert audit_all([rec(1, 0, 16_900 * MS)]).ok
    assert audit_all([rec(1, 0, 17 * S, status=None, error=DEADLINE)]).ok
    assert audit_all([rec(1, 0, 17_800 * MS, status=None, error=DEADLINE)]).ok
    assert "e" in checks([rec(1, 0, 16_999_999_999, status=None, error=DEADLINE)])
    assert "e" in checks([rec(1, 0, 18_000_000_001, status=None, error=DEADLINE)])


def test_e_a_failed_cancellation_lasts_between_the_deadline_and_deadline_plus_two_seconds():
    for end, ok in ((16_999_999_999, False), (17 * S, True), (18_500 * MS, True), (19 * S, True), (19 * S + 1, False)):
        result = audit_all([rec(1, 0, end, status=None, error=CANCEL_FAILED)], abort_seq=1)
        assert ("e" not in result.checks()) is ok, end


# ---- (f) group metadata ----
def test_f_valid_groups_in_order_pass():
    records = renumber(group("resync", ("T",) * 3, None, 1000, 0) + group("g0", ROLES_4TF, "4tf", 1000, 12 * S) + group("g1", ROLES_4TF, "4tf", 1000, 24 * S))
    assert "f" in checks(records)                                                    # g2, g3 and ref are missing without any verification
    full = renumber(boundary_records(1000, 0, kind="4tf", roles=ROLES_4TF))
    assert audit_all(full).ok


def test_f_unknown_group_names_roles_and_kinds_are_refused():
    base = boundary_records(1000, 0)
    unknown = audit_all(renumber([replace(r, group_name="gX") if r.group_name == "g1" else r for r in base]))      # unknown group
    assert any("unknown group name 'gX'" in f.detail for f in unknown.failures)
    assert "f" in checks(renumber([replace(r, role="X") if r.role == "S1" else r for r in base]))                   # unknown role
    assert "f" in checks(renumber([replace(r, group_kind="1h") if r.group_name == "g0" else r for r in base]))      # unknown kind
    assert "f" in checks(renumber([replace(r, group_kind=None) if r.group_name == "g0" else r for r in base]))      # missing kind
    assert "f" in checks(renumber([replace(r, boundary_ms=None) if r.group_name == "g0" else r for r in base]))     # missing boundary
    assert "f" in checks(renumber([replace(r, boundary_ms=True) if r.group_name == "g0" else r for r in base]))
    assert "f" in checks(renumber([replace(r, group_kind="5m") if r.group_name == "resync" else r for r in base]))   # resync has no kind


def test_f_role_and_path_must_agree():
    base = boundary_records(1000, 0)
    assert "f" in checks(renumber([replace(r, path=KLINES_PATH) if r.role == "S1" else r for r in base]))
    assert "f" in checks(renumber([replace(r, path=TIME_PATH) if r.role == "K5m" else r for r in base]))


def test_f_ungrouped_records_need_an_allowed_role_and_no_kind():
    ok = [rec(1, 0, role="SWEEP"), rec(2, 600 * MS, role="PREREG"), rec(3, 1200 * MS, role="PROBE")]
    assert audit_all(ok).ok
    assert "f" in checks([rec(1, 0, role="S1")])                                     # a group role without a group
    assert "f" in checks([rec(1, 0, role="SWEEP", kind="5m")])


def test_f_sync_group_rules():
    sync = [rec(i + 1, i * S, role="T", group="sync") for i in range(10)]
    assert audit_all(sync).ok
    assert "f" in checks(sync[:9])                                                   # fewer than 10 without a failed last call
    assert "f" in checks([replace(r, boundary_ms=1000) for r in sync])
    assert "f" in checks([replace(r, group_kind="5m") for r in sync])
    late = renumber(boundary_records(1000, 0) + [replace(r, start_ns=r.start_ns + 1000 * S) for r in sync])
    assert "f" in checks(late)                                                       # sync must come first


def test_f_a_foreign_request_inside_a_group_is_detected():
    records = group("g0", ROLES_4TF, "4tf", 1000, 0)
    broken = renumber(records[:3] + [rec(99, 0, role="SWEEP")] + records[3:])
    broken = [replace(r, start_ns=i * 600 * MS, end_ns=i * 600 * MS) for i, r in enumerate(broken)]
    assert "f" in checks(broken)


def test_f_wrong_role_order_missing_roles_and_mixed_kinds():
    roles = ("S1", "K1h", "K4h", "K15m", "K5m", "S2")
    assert "f" in checks(renumber(group("g0", roles, "4tf", 1000, 0)))
    short = group("g0", ROLES_4TF[:3], "4tf", 1000, 0)
    assert "f" in checks(renumber(short))                                            # truncated without a failure
    failed = renumber(short)
    failed[-1] = replace(failed[-1], status=None, error=CONNECT_ERROR)
    assert not [f for f in audit_all(failed).failures if "differ from" in f.detail]   # a prefix ending in a failed request is accepted
    assert "f" in checks(renumber(group("g0", ROLES_5M, "4tf", 1000, 0)))
    mixed = group("g0", ROLES_5M, "5m", 1000, 0)
    mixed[1] = replace(mixed[1], group_kind="4tf")
    assert "f" in checks(renumber(mixed))


def test_f_groups_within_a_boundary_and_boundaries_must_be_in_order():
    wrong = group("resync", ("T",) * 3, None, 1000, 0) + group("g1", ROLES_5M, "5m", 1000, 12 * S) + group("g0", ROLES_5M, "5m", 1000, 24 * S)
    assert "f" in checks(renumber(wrong))
    backwards = boundary_records(2000, 0) + boundary_records(1000, 300 * S)
    assert "f" in checks(renumber(backwards))
    again = boundary_records(1000, 0, names=("resync", "g0", "g1")) + group("g0", ROLES_5M, "5m", 1000, 100 * S)
    assert "f" in checks(renumber(again))


def test_f_resync_group_must_contain_only_time_calls_and_three_to_seven():
    assert "f" in checks([rec(1, 0, role="S1", group="resync", boundary=1), rec(2, S, role="T", group="resync", boundary=1), rec(3, 2 * S, role="T", group="resync", boundary=1)])
    assert "f" in checks([rec(1, 0, role="T", group="resync", boundary=1)])
    seven = audit_all([rec(i + 1, i * S, role="T", group="resync", boundary=1) for i in range(7)])
    assert not [f for f in seven.failures if "resync group" in f.detail]            # 3 to 7 calls are accepted
    assert "f" in checks([rec(i + 1, i * S, role="T", group="resync", boundary=1) for i in range(8)])


# ---- (f) verified skipped groups ----
def test_f_a_missing_group_without_evidence_is_refused():
    gap = boundary_records(1000, 0, names=("resync", "g0", "g2", "g3", "ref"))
    result = audit_all(renumber(gap))
    assert "f" in result.checks() and any("without verified skip evidence" in f.detail for f in result.failures)


def test_f_a_missed_window_skip_is_verified_by_a_consistent_decision_and_no_later_groups():
    records = renumber(boundary_records(1000, 0, names=("resync", "g0", "g1")))
    skips = {(1000, name): missed_window_decision() for name in ("g2", "g3", "ref")}
    assert audit_all(records, skips=skips).ok
    only_first = {(1000, "g2"): missed_window_decision()}
    assert "f" in checks(records, skips=only_first)                                      # g3 and ref are still unverified
    middle_gap = renumber(boundary_records(1000, 0, names=("resync", "g0", "g2", "g3", "ref")))
    sent_after_skip = audit_all(middle_gap, skips={(1000, "g1"): missed_window_decision()})
    assert [f.detail for f in sent_after_skip.failures if "was sent after" in f.detail]   # g2.. were sent although g1 was skipped
    assert len(sent_after_skip.failures) == 1
    assert audit_all(renumber(boundary_records(1000, 0, names=("resync", "g0", "g1", "g2", "g3", "ref")))).ok


@pytest.mark.parametrize("bad", [missed_window_decision(admitted=True), missed_window_decision(reason="ADMITTED"),
                                 missed_window_decision(lower_server_ns=F(1_000_000_000)), missed_window_decision(lower_server_ns=F(999_999_999)),
                                 "MISSED-WINDOW", None])
def test_f_skip_evidence_must_be_a_consistent_missed_window_decision(bad):
    records = renumber(boundary_records(1000, 0, names=("resync", "g0", "g1")))
    skips = {(1000, name): bad for name in ("g2", "g3", "ref")}
    result = audit_all(records, skips=skips)
    assert "f" in result.checks()


def test_f_skip_evidence_for_a_group_that_was_actually_sent_is_inconsistent():
    records = renumber(boundary_records(1000, 0))
    assert "f" in checks(records, skips={(1000, "g1"): missed_window_decision()})


def test_f_trailing_groups_may_be_absent_after_a_failed_group_or_at_the_end_of_an_aborted_run():
    failed = boundary_records(1000, 0, names=("resync", "g0", "g1"))
    failed[-1] = replace(failed[-1], status=None, error=CONNECT_ERROR)                  # g1's last request failed: boundary invalid
    assert audit_all(renumber(failed)).ok
    aborted = renumber(boundary_records(1000, 0, names=("resync", "g0", "g1")))
    assert "f" in checks(aborted)                                                       # healthy records, groups missing, no abort: refused
    assert audit_all(aborted, abort_seq=len(aborted)).ok                                # the run was stopped by the owner at that point
    nonok = boundary_records(1000, 0, names=("resync", "g0"))
    nonok[-1] = replace(nonok[-1], status=403)
    nonok = renumber(nonok)
    assert audit_all(nonok, abort_seq=len(nonok)).ok


def test_f_a_boundary_with_groups_needs_its_resync_group():
    records = renumber(boundary_records(1000, 0, names=("g0", "g1", "g2", "g3", "ref")))
    assert "f" in checks(records)


def test_f_expected_boundaries_must_be_present_or_verifiably_skipped():
    records = renumber(boundary_records(1000, 0))
    assert audit_all(records, expected_boundaries=[1000]).ok
    assert "f" in checks(records, expected_boundaries=[1000, 2000])                       # 2000 has neither records nor a skip reason
    assert audit_all(records, expected_boundaries=[1000, 2000], boundary_skips={2000: "SYNC-SKIPPED"}).ok
    assert "f" in checks(records, expected_boundaries=[1000, 2000], boundary_skips={2000: "WHATEVER"})
    assert "f" in checks(records, expected_boundaries=[1000], boundary_skips={1000: "SYNC-SKIPPED"})   # skipped yet sent
    assert "f" in checks(records, expected_boundaries=[2000], boundary_skips={2000: "SYNC-SKIPPED"})    # 1000 was sent but unexpected


# ---- (g) egress counters: all three are required ----
def test_g_all_counters_must_be_supplied_and_equal_the_number_of_records():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert audit_pace(records, jsonl_count=3, wrapper_count=3, manifest_count=3).ok
    assert audit_pace(records).checks() == {"g"} and len(audit_pace(records).failures) == 3         # none supplied
    for kw in ({"jsonl_count": None}, {"wrapper_count": None}, {"manifest_count": None}):
        base = dict(jsonl_count=3, wrapper_count=3, manifest_count=3)
        base.update(kw)
        result = audit_pace(records, **base)
        assert result.checks() == {"g"} and "was not supplied" in result.failures[0].detail
    for kw in ({"jsonl_count": 2}, {"wrapper_count": 4}, {"manifest_count": 0}, {"manifest_count": "3"}, {"wrapper_count": 3.0}, {"jsonl_count": True}):
        assert "g" in checks(records, **kw)


def test_failures_are_reported_with_the_check_letter_and_sequence_number():
    result = audit_all(seq_of([0, 100 * MS]))
    assert not result.ok and result.failures[0].check == "c" and result.failures[0].seq == 2
