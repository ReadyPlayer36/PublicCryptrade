"""PACE-5 audit checks (a)-(g), hardened to fail closed: abort handling, group metadata, verified skips, required counters."""
from dataclasses import replace
from fractions import Fraction as F

import pytest

from tests.fixtures.obs_fakes import audit_all
from tools.obs.admission import AdmissionDecision
from tools.obs.audit import GROUP_WINDOWS_MS, abort_condition_seq, audit_pace, validate_missed_window_decision
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


def decision_for(boundary, group, *, m_e_ns=100 * S, excess=F(1), width=F(100 * MS), **over):
    """A fully consistent MISSED-WINDOW decision: lower = m_e + theta_lo = limit + excess (strictly past the window)."""
    offset_ms, tol_ms = GROUP_WINDOWS_MS[group]
    limit = (boundary + offset_ms + tol_ms) * MS
    theta_lo = limit + excess - m_e_ns
    theta_hi = theta_lo + width
    values = dict(admitted=False, m_e_ns=m_e_ns, theta_lo=theta_lo, theta_hi=theta_hi, lower_server_ns=m_e_ns + theta_lo,
                  upper_server_ns=m_e_ns + theta_hi, limit_ns=limit, reason="MISSED-WINDOW")
    values.update(over)
    return AdmissionDecision(**values)


def missed_window_decision(boundary=1000, group="g2", **over):
    return decision_for(boundary, group, **over)


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
    skips = {(1000, name): decision_for(1000, name) for name in ("g2", "g3", "ref")}
    assert audit_all(records, skips=skips).ok
    only_first = {(1000, "g2"): decision_for(1000, "g2")}
    assert "f" in checks(records, skips=only_first)                                      # g3 and ref are still unverified
    middle_gap = renumber(boundary_records(1000, 0, names=("resync", "g0", "g2", "g3", "ref")))
    sent_after_skip = audit_all(middle_gap, skips={(1000, "g1"): decision_for(1000, "g1")})
    assert [f.detail for f in sent_after_skip.failures if "was sent after" in f.detail]   # g2.. were sent although g1 was skipped
    assert len(sent_after_skip.failures) == 1
    assert audit_all(renumber(boundary_records(1000, 0, names=("resync", "g0", "g1", "g2", "g3", "ref")))).ok


def validate(decision, *, boundary=1000, group="g2", previous_end=50 * S):
    return validate_missed_window_decision(decision, boundary_ms=boundary, group_name=group, previous_end_ns=previous_end)


@pytest.mark.parametrize("group", ["g0", "g1", "g2", "g3", "ref"])
def test_a_consistent_decision_validates_for_every_group_window(group):
    assert validate(decision_for(1000, group), group=group) == []
    assert validate(decision_for(1_700_000_100_000, group, m_e_ns=1_700_000_100_000 * MS), boundary=1_700_000_100_000, group=group,
                    previous_end=10) == []


def test_group_windows_are_the_protocol_values():
    assert GROUP_WINDOWS_MS == {"g0": (0, 2500), "g1": (2000, 2500), "g2": (10_000, 2500), "g3": (60_000, 5000), "ref": (180_000, 5000)}


def test_the_strict_skip_inequality_equality_is_not_a_skip():
    exact = decision_for(1000, "g2", excess=F(0))                                   # lower == limit: admitted, NOT skipped
    assert any("strict skip inequality" in p for p in validate(exact))
    one_ns = decision_for(1000, "g2", excess=F(1))
    assert validate(one_ns) == []                                                   # 1 ns past the limit is a skip
    below = decision_for(1000, "g2", excess=F(-1))
    assert any("strict skip inequality" in p for p in validate(below))
    fractional = decision_for(1000, "g2", excess=F(1, 10_000))                      # a fraction of a nanosecond past the limit is still past
    assert validate(fractional) == []


@pytest.mark.parametrize("field,delta", [("lower_server_ns", 1), ("lower_server_ns", -1), ("upper_server_ns", 1), ("upper_server_ns", -1)])
def test_derived_server_bounds_must_equal_m_e_plus_theta_exactly(field, delta):
    good = decision_for(1000, "g2")
    bad = replace(good, **{field: getattr(good, field) + delta})
    problems = validate(bad)
    assert any(field.split("_")[0] in p and "!= m_e_ns +" in p for p in problems), problems


def test_a_lower_bound_inflated_to_pass_the_inequality_is_caught_by_the_sum_check():
    good = decision_for(1000, "g2", excess=F(-5))                                   # truly NOT past the limit
    forged = replace(good, lower_server_ns=good.limit_ns + 1)                       # claims it is past the limit
    problems = validate(forged)
    assert any("lower_server_ns != m_e_ns + theta_lo" in p for p in problems)
    assert validate(replace(forged, theta_lo=forged.lower_server_ns - forged.m_e_ns, theta_hi=forged.lower_server_ns - forged.m_e_ns + 5,
                            upper_server_ns=forged.lower_server_ns + 5)) == []      # a fully consistent forgery is by construction a valid skip


def test_limit_must_be_recomputed_from_the_boundary_and_the_group_window():
    good = decision_for(1000, "g2")
    assert any("limit_ns != (T + o + tol)" in p for p in validate(replace(good, limit_ns=good.limit_ns + 1)))
    assert any("limit_ns != (T + o + tol)" in p for p in validate(good, boundary=1001))                 # decision belongs to another boundary
    assert any("limit_ns != (T + o + tol)" in p for p in validate(good, group="g1"))                    # decision belongs to another group
    loose = decision_for(1000, "g3")                                                                     # g3 has the wider 5 s tolerance
    assert any("limit_ns != (T + o + tol)" in p for p in validate(loose, group="g2"))
    assert any("no admission window" in p for p in validate(good, group="resync"))


@pytest.mark.parametrize("field,value", [("m_e_ns", 100.0 * S), ("m_e_ns", True), ("m_e_ns", "100"), ("theta_lo", 1.5), ("theta_lo", None),
                                         ("theta_lo", True), ("theta_hi", "x"), ("theta_hi", False), ("lower_server_ns", float("inf")),
                                         ("lower_server_ns", True), ("upper_server_ns", object()), ("upper_server_ns", True),
                                         ("limit_ns", 3.5e9), ("limit_ns", True)])
def test_non_exact_or_mistyped_numbers_are_rejected(field, value):
    problems = validate(replace(decision_for(1000, "g2"), **{field: value}))
    assert f"{field} is not an exact number" in problems


def test_negative_or_non_integer_m_e_and_a_non_integer_limit_are_rejected():
    negative = decision_for(1000, "g2", m_e_ns=-5)                                  # internally consistent, but a negative instant
    assert any("m_e_ns must be a non-negative integer" in p for p in validate(negative, previous_end=-10))
    fractional_m_e = replace(decision_for(1000, "g2"), m_e_ns=F(200, 3))
    assert any("non-negative integer" in p for p in validate(fractional_m_e))
    base = decision_for(1000, "g2")
    assert any("limit_ns must be an integer" in p for p in validate(replace(base, limit_ns=F(base.limit_ns) + F(1, 2))))


def test_theta_lo_must_not_exceed_theta_hi():
    good = decision_for(1000, "g2", width=F(0))
    assert validate(good) == []                                                     # a point estimate is fine
    inverted = replace(good, theta_hi=good.theta_lo - 1, upper_server_ns=good.upper_server_ns - 1)
    assert any("theta_lo exceeds theta_hi" in p for p in validate(inverted))


@pytest.mark.parametrize("over,expected", [({"admitted": True}, "admitted must be exactly False"), ({"admitted": 0}, "admitted must be exactly False"),
                                           ({"admitted": None}, "admitted must be exactly False"), ({"reason": "ADMITTED"}, "reason must be"),
                                           ({"reason": "missed-window"}, "reason must be")])
def test_admitted_flag_and_reason_must_be_exact(over, expected):
    assert any(expected in p for p in validate(replace(decision_for(1000, "g2"), **over)))


@pytest.mark.parametrize("bad", ["MISSED-WINDOW", None, {"admitted": False}, 5, object()])
def test_only_a_genuine_admission_decision_object_is_accepted(bad):
    assert validate(bad) == ["not an AdmissionDecision"]


def test_a_subclass_cannot_smuggle_in_a_decision():
    class Forged(AdmissionDecision):
        pass
    good = decision_for(1000, "g2")
    forged = Forged(**{f: getattr(good, f) for f in good.__dataclass_fields__})
    assert validate(forged) == ["not an AdmissionDecision"]


def test_m_e_must_not_precede_the_completion_of_the_preceding_request():
    good = decision_for(1000, "g2", m_e_ns=100 * S)
    assert validate(good, previous_end=100 * S) == []                               # equal is allowed
    assert any("earlier than the completion" in p for p in validate(good, previous_end=100 * S + 1))
    assert any("no preceding request" in p for p in validate(good, previous_end=None))


def test_audit_rejects_every_malformed_decision_and_accepts_the_consistent_one():
    records = renumber(boundary_records(1000, 0, names=("resync", "g0", "g1")))
    # boundary_records: resync at 0..., g0 at 12 s, g1 at 24 s: the preceding request ends at 24 s + 1.2 s; m_e = 100 s is later.
    ok = {(1000, name): decision_for(1000, name) for name in ("g2", "g3", "ref")}
    assert audit_all(records, skips=ok).ok
    for name in ("g2", "g3", "ref"):
        for mutate in (lambda d: replace(d, lower_server_ns=d.lower_server_ns + 1), lambda d: replace(d, limit_ns=d.limit_ns + 1),
                       lambda d: replace(d, theta_lo=d.theta_hi + 1), lambda d: replace(d, admitted=True), lambda d: replace(d, m_e_ns=1)):
            skips = dict(ok)
            skips[(1000, name)] = mutate(ok[(1000, name)])
            result = audit_all(records, skips=skips)
            assert any("not a consistent MISSED-WINDOW decision" in f.detail for f in result.failures), (name, mutate)


def test_audit_uses_the_completion_of_the_preceding_group_as_the_lower_limit_for_m_e():
    records = renumber(boundary_records(1000, 0, names=("resync", "g0", "g1")))
    last_end = records[-1].end_ns
    early = decision_for(1000, "g2", m_e_ns=last_end - 1)
    late = decision_for(1000, "g2", m_e_ns=last_end)
    rest = {(1000, "g3"): decision_for(1000, "g3"), (1000, "ref"): decision_for(1000, "ref")}
    assert any("earlier than the completion" in f.detail for f in audit_all(records, skips={**rest, (1000, "g2"): early}).failures)
    assert audit_all(records, skips={**rest, (1000, "g2"): late}).ok


def test_skip_evidence_for_unknown_boundaries_or_groups_is_refused():
    records = renumber(boundary_records(1000, 0))
    for key in ((5000, "g2"), (1000, "resync"), (1000, "zz"), ("1000", "g2")):
        result = audit_all(records, skips={key: decision_for(1000, "g2")})
        assert any("unknown boundary or group" in f.detail for f in result.failures), key


def test_a_decision_produced_by_the_real_admission_function_passes_the_audit():
    from tools.obs.admission import decide_admission
    from tools.obs.estimator import OffsetEstimator, TimeSample
    boundary = 1_700_000_100_000
    estimator = OffsetEstimator()
    estimator.add(TimeSample(0, 200 * MS, 1_700_000_002_710))                      # GV-5 sample
    m_e = 100_000_000_001                                                          # 1 ns past the GV-5 boundary: MISSED-WINDOW
    decision = decide_admission(estimator, m_e_ns=m_e, boundary_ms=boundary, offset_ms=0, tol_ms=2500)
    assert decision.admitted is False and validate(decision, boundary=boundary, group="g0", previous_end=0) == []
    forged_on_the_limit = decide_admission(estimator, m_e_ns=100_000_000_000, boundary_ms=boundary, offset_ms=0, tol_ms=2500)
    assert forged_on_the_limit.admitted is True                                    # exactly on the limit is admitted, so it can never be skip evidence
    assert any("admitted must be exactly False" in p for p in validate(forged_on_the_limit, boundary=boundary, group="g0", previous_end=0))


def test_f_skip_evidence_for_a_group_that_was_actually_sent_is_inconsistent():
    records = renumber(boundary_records(1000, 0))
    assert "f" in checks(records, skips={(1000, "g1"): decision_for(1000, "g1")})


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
