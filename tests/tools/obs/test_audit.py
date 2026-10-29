"""PACE-5 audit checks (a)-(g), hardened to fail closed: abort handling, group metadata, verified skips, required counters."""
import json
from dataclasses import replace
from fractions import Fraction as F

import pytest

from tests.fixtures.obs_fakes import audit_all
from tools.obs.admission import AdmissionDecision, decide_admission
from tools.obs.estimator import OffsetEstimator, TimeSample
from tools.obs.audit import (GROUP_WINDOWS_MS, abort_condition_seq, audit_pace, server_time_from_body, time_samples_before,
                             validate_decision_evidence, validate_missed_window_decision)
from tools.obs.pacer import OBS01_PROFILE, RequestRecord
from tools.obs.params import KLINES_PATH, MS, S, TIME_PATH
from tools.obs.transport import CANCEL_FAILED, CONNECT_ERROR, DEADLINE

ROLES_4TF = ("S1", "K4h", "K1h", "K15m", "K5m", "S2")
ROLES_5M = ("S1", "K5m", "S2")
PATH = {"T": TIME_PATH, "S1": TIME_PATH, "S2": TIME_PATH, "K4h": KLINES_PATH, "K1h": KLINES_PATH, "K15m": KLINES_PATH, "K5m": KLINES_PATH,
        "SWEEP": KLINES_PATH, "PREREG": KLINES_PATH, "PROBE": KLINES_PATH}


THETA_NS = 1_700_000_000_000 * MS                      # test world: server time = monotonic + THETA


def time_body(t_ns, server_ms=None):
    """A recorded /api/v3/time body consistent with the test world at monotonic time t."""
    return json.dumps({"serverTime": (t_ns + THETA_NS) // MS if server_ms is None else server_ms}).encode()


def rec(seq, start, end=None, *, status=200, error=None, role="PROBE", group=None, kind=None, boundary=None, path=None, body=None):
    if body is None:
        body = time_body(start) if role in ("T", "S1", "S2") else b"[]"
    return RequestRecord(seq=seq, role=role, path=path or PATH.get(role, TIME_PATH), start_ns=start, end_ns=start if end is None else end,
                         status=status, error=error, group_name=group, group_kind=kind, boundary_ms=boundary, body=body)


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
                  upper_server_ns=m_e_ns + theta_hi, limit_ns=limit, reason="MISSED-WINDOW", decided_at_ns=m_e_ns)
    values.update(over)
    return AdmissionDecision(**values)


def missed_window_decision(boundary=1000, group="g2", **over):
    return decision_for(boundary, group, **over)


def evidence_case(group_name, m_e_ns=300 * S, names=("resync", "g0", "g1"), next_boundary_at=None, decided_at_ns=None):
    """Records with real /time bodies plus the HONEST decision the estimator produces from them at m_e (a genuine MISSED-WINDOW)."""
    def build(boundary):
        recs = boundary_records(boundary, 0, names=names)
        if next_boundary_at is not None:
            recs += boundary_records(boundary + 600_000, next_boundary_at, names=("resync",))
        return renumber(recs)

    samples, _ = time_samples_before(build(0), m_e_ns)
    estimator = OffsetEstimator()
    for sample in samples:
        estimator.add(sample)
    estimate = estimator.estimate(m_e_ns)
    offset_ms, tol_ms = GROUP_WINDOWS_MS[group_name]
    boundary = int((m_e_ns + estimate.lo) // MS) - offset_ms - tol_ms - 5               # the group window closed 5 ms before the earliest server time
    decision = decide_admission(estimator, m_e_ns=m_e_ns, boundary_ms=boundary, offset_ms=offset_ms, tol_ms=tol_ms, decided_at_ns=decided_at_ns)
    assert decision.admitted is False
    return build(boundary), decision, boundary


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


def test_f_a_missed_window_skip_is_verified_by_the_evidence_and_covers_the_rest_of_the_boundary():
    records, decision, boundary = evidence_case("g2")
    assert audit_all(records, skips={(boundary, "g2"): decision}).ok                   # g2 skipped; g3 and ref were never sent
    assert "f" in checks(records)                                                      # without the evidence the missing groups are refused
    # a genuine g1 skip decision (made at 20 s, between g0 and the next recorded request) while g2.. were nevertheless sent
    names = ("resync", "g0", "g2", "g3", "ref")
    m_e = 20 * S
    estimator = _estimator_of(renumber(boundary_records(0, 0, names=names)), m_e)
    boundary_g1 = int((m_e + estimator.estimate(m_e).lo) // MS) - 2000 - 2500 - 5
    sent_later = renumber(boundary_records(boundary_g1, 0, names=names))
    skip_g1 = decide_admission(estimator, m_e_ns=m_e, boundary_ms=boundary_g1, offset_ms=2000, tol_ms=2500)
    assert skip_g1.admitted is False
    result = audit_all(sent_later, skips={(boundary_g1, "g1"): skip_g1})
    assert [f.detail for f in result.failures if "was sent after" in f.detail]          # g2.. were sent although g1 was skipped


def _estimator_of(records, m_e_ns):
    estimator = OffsetEstimator()
    for sample in time_samples_before(records, m_e_ns)[0]:
        estimator.add(sample)
    return estimator


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
    records, honest, boundary = evidence_case("g2")
    key = (boundary, "g2")
    assert audit_all(records, skips={key: honest}).ok
    for mutate in (lambda d: replace(d, lower_server_ns=d.lower_server_ns + 1), lambda d: replace(d, limit_ns=d.limit_ns + 1),
                   lambda d: replace(d, theta_lo=d.theta_hi + 1), lambda d: replace(d, admitted=True), lambda d: replace(d, m_e_ns=1)):
        result = audit_all(records, skips={key: mutate(honest)})
        assert any("not a consistent MISSED-WINDOW decision" in f.detail for f in result.failures), mutate


def test_audit_uses_the_completion_of_the_preceding_group_as_the_lower_limit_for_m_e():
    last_end = evidence_case("g2")[0][-1].end_ns
    for m_e, ok in ((last_end - 1, False), (last_end + 600 * MS - 1, False), (last_end + 600 * MS, True)):
        records, decision, boundary = evidence_case("g2", m_e_ns=m_e)              # a genuine decision at exactly this m_e
        result = audit_all(records, skips={(boundary, "g2"): decision})
        assert (not result.failures) is ok, (m_e, [f.detail for f in result.failures])
        if m_e < last_end:
            assert any("earlier than the completion of the preceding request" in f.detail for f in result.failures)   # the arithmetic check itself


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


# ---- evidence-tied validation (re-audit finding 3) ----
def forge(decision, delta_ns, *, lo=True, hi=True):
    """A decision that is arithmetically SELF-CONSISTENT but whose theta is not what the recorded evidence produces."""
    theta_lo = decision.theta_lo + (delta_ns if lo else 0)
    theta_hi = decision.theta_hi + (delta_ns if hi else 0)
    return replace(decision, theta_lo=theta_lo, theta_hi=theta_hi, lower_server_ns=decision.m_e_ns + theta_lo,
                   upper_server_ns=decision.m_e_ns + theta_hi)


def audit_problems(records, boundary, group, decision):
    result = audit_all(records, skips={(boundary, group): decision})
    return [f.detail for f in result.failures if f.check == "f"]


def direct(decision, records, previous, *, boundary=0, group="g2", timeline_end_ns=10**15, profile=None):
    """validate_decision_evidence with an HONEST recorder's verified log (decision logged right after `previous`)."""
    from tools.obs.eventlog import EventLogWriter, verify_event_log
    from tools.obs.pacer import OBS02_PROFILE
    writer = EventLogWriter()
    writer.append_decision(boundary_ms=boundary, group_name=group, decided_at_ns=decision.decided_at_ns, m_e_ns=decision.m_e_ns,
                           records=records[: previous.seq])
    if timeline_end_ns is not None:
        writer.append_timeline_end(timeline_end_ns=timeline_end_ns, records=records)
    log = verify_event_log(writer.events, writer.head_digest, records)
    return validate_decision_evidence(decision, records, previous_record=previous, profile=profile or OBS02_PROFILE, verified_log=log,
                                      boundary_ms=boundary, group_name=group)


CASES = [("g0", ("resync",)), ("g1", ("resync", "g0")), ("g2", ("resync", "g0", "g1")), ("g3", ("resync", "g0", "g1", "g2")),
         ("ref", ("resync", "g0", "g1", "g2", "g3"))]


@pytest.mark.parametrize("group,names", CASES)
def test_an_honest_decision_matches_the_recorded_evidence_for_every_group(group, names):
    records, decision, boundary = evidence_case(group, names=names)
    assert validate(decision, boundary=boundary, group=group, previous_end=records[-1].end_ns) == []
    assert audit_problems(records, boundary, group, decision) == []
    assert audit_all(records, skips={(boundary, group): decision}).ok


@pytest.mark.parametrize("delta_ns", [1, -1, 1000, -1_000_000, 123_456_789])
def test_a_self_consistent_decision_with_fabricated_theta_is_rejected(delta_ns):
    records, honest, boundary = evidence_case("g2")
    forged = forge(honest, delta_ns)
    assert validate(forged, boundary=boundary, group="g2", previous_end=records[-1].end_ns) == []      # passes every internal check ...
    problems = audit_problems(records, boundary, "g2", forged)
    assert any("theta_lo" in p and "does not match the evidence" in p for p in problems)               # ... but not the evidence
    assert any("theta_hi" in p and "does not match the evidence" in p for p in problems)


def test_each_theta_bound_is_checked_separately():
    records, honest, boundary = evidence_case("g2")
    only_lo = audit_problems(records, boundary, "g2", forge(honest, 1, hi=False))
    assert any("theta_lo" in p for p in only_lo) and not any("theta_hi" in p for p in only_lo)
    only_hi = audit_problems(records, boundary, "g2", forge(honest, 1, lo=False))
    assert any("theta_hi" in p for p in only_hi) and not any("theta_lo" in p for p in only_hi)


def test_a_decision_computed_from_a_subset_of_the_recorded_samples_is_rejected():
    records, honest, boundary = evidence_case("g2")
    samples, _ = time_samples_before(records, honest.m_e_ns)
    assert len(samples) > 3
    subset = OffsetEstimator()
    subset.add(samples[0])                                                         # ignores most of the evidence
    partial = decide_admission(subset, m_e_ns=honest.m_e_ns, boundary_ms=boundary, offset_ms=10_000, tol_ms=2500)
    assert partial.admitted is False and (partial.theta_lo, partial.theta_hi) != (honest.theta_lo, honest.theta_hi)
    assert any("does not match the evidence" in p for p in audit_problems(records, boundary, "g2", partial))


def test_a_decision_that_uses_a_sample_which_was_never_recorded_is_rejected():
    records, honest, boundary = evidence_case("g2")
    samples, _ = time_samples_before(records, honest.m_e_ns)
    phantom = OffsetEstimator()
    for sample in samples:
        phantom.add(sample)
    phantom.add(TimeSample(299 * S, 299 * S, (299 * S + THETA_NS) // MS))                   # a perfectly plausible, but unrecorded, /time call
    claimed = decide_admission(phantom, m_e_ns=honest.m_e_ns, boundary_ms=boundary, offset_ms=10_000, tol_ms=2500)
    assert (claimed.theta_lo, claimed.theta_hi) != (honest.theta_lo, honest.theta_hi)
    assert any("does not match the evidence" in p for p in audit_problems(records, boundary, "g2", claimed))


def test_altered_recorded_responses_no_longer_support_the_decision():
    records, honest, boundary = evidence_case("g2")
    shifted = [replace(r, body=time_body(r.start_ns, server_ms=json.loads(r.body)["serverTime"] + 50)) if r.path == TIME_PATH else r for r in records]
    problems = audit_problems(shifted, boundary, "g2", honest)
    assert any("theta_lo" in p and "does not match the evidence" in p for p in problems)
    contradicting = [replace(r, body=time_body(r.start_ns, server_ms=json.loads(r.body)["serverTime"] + 10_000)) if r.seq == 1 else r for r in records]
    assert any("no offset estimate" in p for p in audit_problems(contradicting, boundary, "g2", honest))     # a contradicting response: empty intersection


@pytest.mark.parametrize("bad_body", [b"", b"not json", b"[]", b'{"time": 5}', b'{"serverTime": "5"}', b'{"serverTime": true}', b'{"serverTime": -1}',
                                      b'{"serverTime": 1.5}', b"\xff\xfe"])
def test_a_time_response_without_a_usable_server_time_fails_closed(bad_body):
    records, honest, boundary = evidence_case("g2")
    broken = [replace(r, body=bad_body) if r.seq == 2 else r for r in records]
    assert records[1].path == TIME_PATH
    assert any("/time record seq 2 has no usable serverTime body" in p for p in audit_problems(broken, boundary, "g2", honest))


def test_the_retention_rule_is_applied_by_the_audit_not_taken_from_the_decision():
    records, _, boundary = evidence_case("g2")
    unlimited = OffsetEstimator(retention_ns=10**18)
    for sample in time_samples_before(records, 700 * S)[0]:
        unlimited.add(sample)
    claimed = decide_admission(unlimited, m_e_ns=700 * S, boundary_ms=boundary, offset_ms=10_000, tol_ms=2500)        # claims samples older than 600 s
    assert claimed.admitted is False
    assert any("no offset estimate" in p for p in audit_problems(records, boundary, "g2", claimed))                  # every sample has aged out


def test_samples_after_m_e_do_not_influence_the_audit():
    records, honest, boundary = evidence_case("g2")
    late = records + [rec(len(records) + 1, 400 * S, role="T", group="resync", boundary=boundary + 600_000, body=time_body(400 * S, server_ms=5))]
    assert not any("does not match" in p or "no offset estimate" in p for p in audit_problems(late, boundary, "g2", honest))


def test_m_e_may_not_be_later_than_the_start_of_the_next_recorded_request():
    records, decision, boundary = evidence_case("g2", m_e_ns=300 * S, next_boundary_at=200 * S)
    problems = audit_problems(records, boundary, "g2", decision)
    assert any("decided_at_ns" in p and "later than the start of the next recorded request" in p for p in problems)
    records, decision, boundary = evidence_case("g2", m_e_ns=300 * S, next_boundary_at=300 * S)
    assert not any("later than the start" in p for p in audit_problems(records, boundary, "g2", decision))           # equal is allowed


def handmade_records(extra_old_offset_ms=0):
    """/time(0) then 59 klines probes spaced 0.6 s: a full 60-request minute."""
    records = [RequestRecord(1, "T", TIME_PATH, 0, 0, 200, None, "sync", None, None, time_body(0, server_ms=THETA_NS // MS + extra_old_offset_ms))]
    for k in range(1, 60):
        records.append(RequestRecord(k + 1, "PROBE", KLINES_PATH, k * 600 * MS, k * 600 * MS, 200, None, None, None, None, b"[]"))
    return records


def decision_at(records, m_e_ns, boundary_ms=0, group="g0"):
    estimator = OffsetEstimator()
    for sample in time_samples_before(records, m_e_ns)[0]:
        estimator.add(sample)
    offset_ms, tol_ms = GROUP_WINDOWS_MS[group]
    return decide_admission(estimator, m_e_ns=m_e_ns, boundary_ms=boundary_ms, offset_ms=offset_ms, tol_ms=tol_ms)


def test_m_e_may_not_precede_the_rolling_cap_release_recomputed_from_the_records():
    from tools.obs.pacer import OBS02_PROFILE
    records = handmade_records()
    previous = records[-1]                                                           # start 35.4 s; 60 starts within 60 s
    early = decision_at(records, 36 * S)                                             # completion and spacing (36.0 s) are satisfied ...
    problems = direct(early, records, previous)
    assert any("earlier than the earliest start the pacer rules allow" in p and "(60000000000)" in p for p in problems)    # ... the 60 s cap is not
    released = decision_at(records, 60 * S)
    assert not any("earlier than the earliest" in p for p in direct(released, records, previous))
    just_before = decision_at(records, 60 * S - 1)
    assert any("earlier than the earliest" in p for p in direct(just_before, records, previous))


def test_the_completion_of_a_long_preceding_request_bounds_m_e_in_the_evidence_check():
    from tools.obs.pacer import OBS02_PROFILE
    first = RequestRecord(1, "T", TIME_PATH, 0, 10 * MS, 200, None, "sync", None, None, time_body(5 * MS))
    previous = RequestRecord(2, "PROBE", KLINES_PATH, 1 * S, 6 * S, 200, None, None, None, None, b"[]")      # lasted 5 s: start + 0.6 s < end
    records = [first, previous]
    early = decision_at(records, 3 * S)                                              # after start + spacing (1.6 s), before the completion (6 s)
    problems = direct(early, records, previous)
    assert any("earlier than the earliest start the pacer rules allow" in p and f"({6 * S})" in p for p in problems)
    on_time = decision_at(records, 6 * S)
    assert not any("earlier than the earliest" in p for p in direct(on_time, records, previous))


def test_the_fallback_window_rule_of_the_estimator_is_reproduced_by_the_audit():
    from tools.obs.pacer import OBS02_PROFILE
    old = RequestRecord(1, "T", TIME_PATH, 0, 10 * MS, 200, None, "sync", None, None, time_body(5 * MS))
    recent_start = 100 * S
    recent = RequestRecord(2, "T", TIME_PATH, recent_start, recent_start + 10 * MS, 200, None, "sync", None, None,
                           time_body(recent_start + 5 * MS, server_ms=(recent_start + 5 * MS + THETA_NS) // MS + 900_000))     # contradicts the old sample
    previous = RequestRecord(3, "PROBE", KLINES_PATH, 150 * S, 150 * S, 200, None, None, None, None, b"[]")
    records = [old, recent, previous]
    m_e = 151 * S
    estimator = OffsetEstimator()
    for sample in time_samples_before(records, m_e)[0]:
        estimator.add(sample)
    assert estimator.estimate(m_e).used_fallback and estimator.estimate(m_e, allow_fallback=False) is None
    honest = decide_admission(estimator, m_e_ns=m_e, boundary_ms=0, offset_ms=0, tol_ms=2500)
    assert honest.admitted is False
    assert direct(honest, records, previous, timeline_end_ns=200 * S) == []
    only_old = OffsetEstimator()
    only_old.add(time_samples_before(records, m_e)[0][0])
    wrong = decide_admission(only_old, m_e_ns=m_e, boundary_ms=0, offset_ms=0, tol_ms=2500)
    assert any("does not match the evidence" in p for p in direct(wrong, records, previous, timeline_end_ns=200 * S))


# ---- evidence extraction helpers ----
@pytest.mark.parametrize("body,expected", [(b'{"serverTime": 1700000000123}', 1700000000123), (bytearray(b'{"serverTime": 0}'), 0), (b'{"serverTime":1,"x":2}', 1),
                                           (b"", None), (b"{}", None), (b"[1]", None), (b'{"serverTime": null}', None), (b'{"serverTime": 1.0}', None),
                                           (b'{"serverTime": false}', None), (b'{"serverTime": "1"}', None), (b'{"serverTime": -5}', None),
                                           ("not bytes", None), (None, None), (b"\x00\xff", None)])
def test_server_time_from_body(body, expected):
    assert server_time_from_body(body) == expected


def test_time_samples_are_taken_only_from_completed_200_time_responses_before_m_e():
    ok = RequestRecord(1, "T", TIME_PATH, 0, 5 * MS, 200, None, "sync", None, None, time_body(0))
    on_time = RequestRecord(2, "T", TIME_PATH, 10 * MS, 20 * MS, 200, None, "sync", None, None, time_body(10 * MS))
    after = RequestRecord(3, "T", TIME_PATH, 30 * MS, 40 * MS, 200, None, "sync", None, None, time_body(30 * MS))
    failed = RequestRecord(4, "T", TIME_PATH, 12 * MS, 18 * MS, None, "TIMEOUT", "sync", None, None, b"")
    refused = RequestRecord(6, "T", TIME_PATH, 13 * MS, 15 * MS, 429, None, "sync", None, None, time_body(13 * MS))      # a valid-looking body, but not a 200
    klines = RequestRecord(5, "PROBE", KLINES_PATH, 0, 1, 200, None, None, None, None, time_body(0))
    samples, problems = time_samples_before([ok, on_time, after, failed, refused, klines], 20 * MS)
    assert problems == [] and [(x.a_ns, x.b_ns) for x in samples] == [(0, 5 * MS), (10 * MS, 20 * MS)]        # end == m_e is included
    assert [(x.a_ns, x.b_ns) for x in time_samples_before([ok, on_time, after], 19_999_999)[0]] == [(0, 5 * MS)]
    assert time_samples_before([replace(ok, body=b"x")], 20 * MS) == ([], ["/time record seq 1 has no usable serverTime body"])


def test_a_time_record_that_cannot_form_a_sample_is_reported_not_crashed_on():
    backwards = RequestRecord(1, "T", TIME_PATH, 10 * MS, 5 * MS, 200, None, "sync", None, None, time_body(10 * MS))      # ends before it starts
    samples, problems = time_samples_before([backwards], 20 * MS)
    assert samples == [] and problems == ["/time record seq 1 cannot form an estimator sample"]



# ---- terminal skips and the decision-time bound (re-audit finding 2) ----
def terminal_problems(records, boundary, decision, **kw):
    result = audit_all(records, skips={(boundary, "g2"): decision}, **kw)
    return [f.detail for f in result.failures if f.check in ("f", "a")]


def test_a_terminal_skip_without_an_audited_timeline_bound_is_rejected():
    records, decision, boundary = evidence_case("g2")                               # nothing was sent after the skip: it is terminal
    unbounded = terminal_problems(records, boundary, decision, timeline_end_ns=None)
    assert any("no recorded TIMELINE_END event" in p and "unbounded" in p for p in unbounded)
    assert terminal_problems(records, boundary, decision, timeline_end_ns=decision.decided_at_ns) == []      # a bound, even a tight one, suffices
    assert audit_all(records, skips={(boundary, "g2"): decision}, timeline_end_ns=decision.decided_at_ns).ok


def test_the_decision_timestamp_must_not_exceed_the_audited_timeline_end():
    records, decision, boundary = evidence_case("g2")
    decided = decision.decided_at_ns
    assert terminal_problems(records, boundary, decision, timeline_end_ns=decided + 1) == []
    problems = terminal_problems(records, boundary, decision, timeline_end_ns=decided - 1)
    assert any("later than the audited timeline end" in p for p in problems)
    assert any("timeline_end_ns" in p and "precedes the last record" in p for p in terminal_problems(records, boundary, decision, timeline_end_ns=records[-1].end_ns - 1))


@pytest.mark.parametrize("bad", [1.5e9, True, "300", -5])
def test_the_timeline_end_itself_must_be_a_plain_integer_not_before_the_last_record(bad):
    records, decision, boundary = evidence_case("g2")
    result = audit_all(records, skips={(boundary, "g2"): decision}, timeline_end_ns=bad)
    assert not result.ok                                                               # an unusable bound is never accepted as a bound
    assert any(f.check == "a" and "event log rejected" in f.detail for f in result.failures) or any("unbounded" in f.detail for f in result.failures)


def test_an_inflated_decision_time_cannot_hide_behind_a_consistent_theta():
    # Honest theta for a decision "taken" at 400 s (inside the 600 s retention window, so the evidence supports it), while the audited
    # run ended at 200 s: arithmetic and evidence-theta are consistent, but the decision time is beyond the end of the run.
    records, decision, boundary = evidence_case("g2", m_e_ns=400 * S)
    problems = terminal_problems(records, boundary, decision, timeline_end_ns=200 * S)
    assert any("later than the audited timeline end" in p for p in problems)
    assert terminal_problems(records, boundary, decision, timeline_end_ns=400 * S) == []                       # the same decision is fine once the run lasted that long


def test_m_e_is_tied_exactly_to_the_decision_time_and_the_pacer_rules():
    # previous request: S2 of g1 at 25.2 s (zero duration): earliest pacer start = 25.8 s
    last_end = evidence_case("g2")[0][-1].end_ns
    earliest = last_end + 600 * MS
    base = dict(timeline_end_ns=500 * S)
    for decided, m_e, ok, fragment in (
        (last_end + 100 * MS, earliest, True, None),                                 # decided before the pacer allows a start: m_e = earliest
        (last_end + 100 * MS, earliest - 1, False, "earlier than the earliest start"),
        (last_end + 100 * MS, earliest + 1, False, "later than max(decided_at_ns, earliest pacer start)"),
        (300 * S, 300 * S, True, None),                                              # decided long after: m_e = decided
        (100 * S, 300 * S, False, "later than max(decided_at_ns, earliest pacer start)"),    # claims a later m_e than its own decision time implies
        (last_end, earliest, True, None),                                            # decided exactly at the completion: allowed
        (last_end - 1, earliest, False, "precedes the completion of the preceding request"),
    ):
        records, decision, boundary = evidence_case("g2", m_e_ns=m_e, decided_at_ns=decided)
        problems = terminal_problems(records, boundary, decision, **base)
        assert (problems == []) is ok, (decided, m_e, problems)
        if fragment:
            assert any(fragment in p for p in problems), (decided, m_e, problems)


def test_a_non_terminal_skip_is_bounded_by_the_next_recorded_request_not_by_the_timeline():
    records, decision, boundary = evidence_case("g2", m_e_ns=150 * S, next_boundary_at=200 * S)
    bound_problems = [p for p in audit_problems(records, boundary, "g2", decision) if "later than" in p or "unbounded" in p]
    assert bound_problems == []                                                      # decided at 150 s < the next request at 200 s
    late_records, late_decision, late_boundary = evidence_case("g2", m_e_ns=250 * S, next_boundary_at=200 * S)
    assert any("later than the start of the next recorded request" in p for p in audit_problems(late_records, late_boundary, "g2", late_decision))
    assert not any("audited timeline" in p for p in audit_problems(late_records, late_boundary, "g2", late_decision))     # the generous timeline is irrelevant here


@pytest.mark.parametrize("field,value,fragment", [("decided_at_ns", None, "decision timestamp"), ("decided_at_ns", 300.0 * S, "decision timestamp"),
                                                  ("decided_at_ns", True, "decision timestamp"), ("decided_at_ns", -1, "decision timestamp"),
                                                  ("decided_at_ns", 300 * S + 1, "later than m_e_ns")])
def test_the_recorded_decision_timestamp_must_be_a_valid_integer_not_after_m_e(field, value, fragment):
    records, honest, boundary = evidence_case("g2")
    bad = replace(honest, **{field: value})
    assert any(fragment in p for p in validate(bad, boundary=boundary, group="g2", previous_end=records[-1].end_ns))
    assert any("not a consistent MISSED-WINDOW decision" in p for p in audit_problems(records, boundary, "g2", bad))


def test_a_decision_without_a_recorded_timestamp_cannot_be_used_as_skip_evidence():
    records, honest, boundary = evidence_case("g2")
    legacy = AdmissionDecision(honest.admitted, honest.m_e_ns, honest.theta_lo, honest.theta_hi, honest.lower_server_ns,
                               honest.upper_server_ns, honest.limit_ns, honest.reason)               # no decided_at_ns at all
    assert legacy.decided_at_ns is None
    assert any("decision timestamp" in p for p in audit_problems(records, boundary, "g2", legacy))


def test_validate_decision_evidence_rejects_an_m_e_that_precedes_the_decision_time_when_called_directly():
    from tools.obs.pacer import OBS02_PROFILE
    records, honest, boundary = evidence_case("g2")
    previous = records[-1]
    inverted = replace(honest, decided_at_ns=honest.m_e_ns + 1)                      # never reaches the evidence check through the audit
    problems = direct(inverted, records, previous, timeline_end_ns=10**15)
    assert any("precedes decided_at_ns" in p for p in problems)
    assert not any("precedes decided_at_ns" in p for p in direct(honest, records, previous, timeline_end_ns=10**15))


def test_a_timeline_end_equal_to_the_last_completion_is_a_valid_bound_by_itself():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert audit_all(records, timeline_end_ns=records[-1].end_ns).ok
    assert "a" in checks(records, timeline_end_ns=records[-1].end_ns - 1)
