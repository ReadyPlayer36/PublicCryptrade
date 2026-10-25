"""PACE-5 audit checks (a)-(g) and the window boundary conditions (open left, closed right), GV-8 and GV-9."""
from dataclasses import replace

import pytest

from tools.obs.audit import audit_pace
from tools.obs.pacer import OBS01_PROFILE, RequestRecord
from tools.obs.params import MS, S
from tools.obs.transport import CONNECT_ERROR, DEADLINE


def rec(seq, start, end=None, *, status=200, error=None, role="T", group=None, kind=None, boundary=None):
    return RequestRecord(seq=seq, role=role, path="/api/v3/time", start_ns=start, end_ns=start if end is None else end,
                         status=status, error=error, group_name=group, group_kind=kind, boundary_ms=boundary)


def seq_of(starts, **kw):
    return [rec(i + 1, s, **kw) for i, s in enumerate(starts)]


def checks(records, **kw):
    return audit_pace(records, **kw).checks()


def test_a_clean_sequence_passes():
    assert audit_pace(seq_of([k * 600 * MS for k in range(10)])).ok
    assert audit_pace([]).ok


# ---- (a) integrity ----
def test_a_sequence_must_be_contiguous_from_one():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert "a" in checks([records[0], replace(records[2], seq=3)])               # gap
    assert "a" in checks([replace(records[0], seq=2), records[1]])               # does not start at 1
    assert "a" in checks([records[0], replace(records[1], seq=1)])               # duplicate seq


def test_a_timestamps_must_be_plain_integers_and_not_regress():
    records = seq_of([0, 600 * MS])
    assert "a" in checks([records[0], replace(records[1], start_ns=600.0 * MS)])
    assert "a" in checks([records[0], replace(records[1], start_ns=True)])
    assert "a" in checks([replace(records[0], end_ns=-1)])                        # end before start
    assert "a" in checks([rec(1, 900 * MS), rec(2, 100 * MS)])                    # start times must be non-decreasing


def test_a_no_record_may_follow_an_abort():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert "a" in checks(records, abort_seq=2)
    assert audit_pace(records, abort_seq=3).ok


# ---- (b) completion ordering and non-overlap ----
def test_b_a_request_may_not_start_before_the_previous_completed():
    records = [rec(1, 0, 900 * MS), rec(2, 700 * MS, 800 * MS)]                   # overlaps (and completes before the first)
    assert "b" in checks(records)
    assert audit_pace([rec(1, 0, 600 * MS), rec(2, 600 * MS, 700 * MS)]).ok               # end == next start is allowed


def test_b_completions_must_follow_start_order():
    records = [rec(1, 0, 5 * S), rec(2, 700 * MS, 800 * MS)]
    assert "b" in checks(records)


# ---- (c) spacing ----
def test_c_spacing_is_an_exact_integer_comparison():
    assert audit_pace(seq_of([0, 600_000_000])).ok
    assert "c" in checks(seq_of([0, 599_999_999]))
    assert "c" in checks(seq_of([0, 600 * MS, 700 * MS]))


# ---- (d) rolling caps with open-left / closed-right windows ----
def test_d_one_second_cap_boundaries_gv8_ii():
    assert "d" not in checks(seq_of([0, 600 * MS, 1_000_000_000]))                # the start at 0 is outside (0, 1 s]
    assert "c" in checks(seq_of([0, 600 * MS, 1_000_000_000]))                    # (but the 400 ms spacing fails check c)
    assert "d" in checks(seq_of([0, 600 * MS, 999_999_999]))                      # one ns earlier: inside the window


def test_d_sixty_second_cap_boundaries_gv8_i():
    one_per_second = [k * S for k in range(61)]                                    # the 61st start at exactly 60 s
    assert audit_pace(seq_of(one_per_second)).ok                                   # window (0, 60 s] holds 60 starts
    too_many = [k * S for k in range(60)] + [59_999_999_999]                       # 61 starts within (-1 ns, 59.999999999 s]
    assert checks(seq_of(too_many)) == {"d"}


def test_d_obs01_profile_caps_are_one_per_two_seconds_and_thirty_per_minute():
    assert audit_pace(seq_of([0, 2 * S, 4 * S]), profile=OBS01_PROFILE).ok
    assert checks(seq_of([0, 1_999_999_999]), profile=OBS01_PROFILE) == {"c", "d"}
    assert audit_pace(seq_of([k * 2 * S for k in range(31)]), profile=OBS01_PROFILE).ok       # 31st at exactly 60 s
    thirty_one_in_window = [k * 2 * S for k in range(30)] + [59_999_999_999]
    assert "d" in checks(seq_of(thirty_one_in_window), profile=OBS01_PROFILE)


# ---- (e) durations ----
def test_e_durations_backstop_gv9():
    assert "e" in checks([rec(1, 0, 18_000_000_001)])
    assert audit_pace([rec(1, 0, 18_000_000_000)]).ok
    assert audit_pace([rec(1, 0, 16_900 * MS)]).ok                                 # completes at 16.9 s, unaffected
    assert audit_pace([rec(1, 0, 17 * S, status=None, error=DEADLINE)]).ok        # watchdog cancellation at the deadline
    assert audit_pace([rec(1, 0, 17_800 * MS, status=None, error=DEADLINE)]).ok
    assert "e" in checks([rec(1, 0, 16_999_999_999, status=None, error=DEADLINE)])  # a deadline outcome cannot be earlier than 17 s
    assert "e" in checks([rec(1, 0, 18_000_000_001, status=None, error=DEADLINE)])


# ---- (f) group integrity ----
ROLES_4TF = ("S1", "K4h", "K1h", "K15m", "K5m", "S2")


def group(seq0, start0, name, roles, kind, boundary, gap=600 * MS, last_status=200):
    out = []
    for i, role in enumerate(roles):
        out.append(rec(seq0 + i, start0 + i * gap, role=role, group=name, kind=kind, boundary=boundary,
                       status=last_status if i == len(roles) - 1 else 200))
    return out


def renumber(records):
    return [replace(r, seq=i + 1) for i, r in enumerate(records)]


def test_f_valid_groups_in_order_pass():
    records = group(1, 0, "g0", ROLES_4TF, "4tf", 1000) + group(7, 10 * S, "g1", ROLES_4TF, "4tf", 1000)
    records += group(13, 20 * S, "g0", ("S1", "K5m", "S2"), "5m", 2000)
    assert audit_pace(renumber(records)).ok
    resync = [rec(i + 1, i * 1 * S, role="T", group="resync", boundary=3000) for i in range(3)]
    assert audit_pace(resync).ok


def test_f_a_foreign_request_inside_a_group_is_detected():
    records = group(1, 0, "g0", ROLES_4TF, "4tf", 1000)
    foreign = rec(99, 0, role="T")
    broken = renumber(records[:3] + [foreign] + records[3:])
    broken = [replace(r, start_ns=i * 600 * MS, end_ns=i * 600 * MS) for i, r in enumerate(broken)]
    assert "f" in checks(broken)


def test_f_wrong_role_order_or_missing_roles_are_detected_unless_the_group_was_aborted():
    roles = ("S1", "K1h", "K4h", "K15m", "K5m", "S2")
    assert "f" in checks(renumber(group(1, 0, "g0", roles, "4tf", 1000)))
    short = group(1, 0, "g0", ROLES_4TF[:3], "4tf", 1000)
    assert "f" in checks(renumber(short))                                           # truncated group without a failure
    aborted = group(1, 0, "g0", ROLES_4TF[:3], "4tf", 1000, last_status=None)
    aborted[-1] = replace(aborted[-1], status=None, error=CONNECT_ERROR)
    assert audit_pace(renumber(aborted)).ok                                         # a prefix ending in a failed request
    assert "f" in checks(renumber(group(1, 0, "g0", ("S1", "K5m", "S2"), "4tf", 1000)))
    assert "f" in checks(renumber(group(1, 0, "g0", ("S1", "K5m", "S2"), None, 1000)))


def test_f_groups_within_a_boundary_and_boundaries_must_be_in_order():
    five = ("S1", "K5m", "S2")
    wrong = group(1, 0, "g1", five, "5m", 1000) + group(4, 10 * S, "g0", five, "5m", 1000)
    assert "f" in checks(renumber(wrong))
    skipped_group_is_fine = group(1, 0, "g0", five, "5m", 1000) + group(4, 10 * S, "g2", five, "5m", 1000)
    assert audit_pace(renumber(skipped_group_is_fine)).ok                          # MISSED-WINDOW boundaries skip groups
    backwards = group(1, 0, "g0", five, "5m", 2000) + group(4, 10 * S, "g0", five, "5m", 1000)
    assert "f" in checks(renumber(backwards))
    again = group(1, 0, "g0", five, "5m", 1000) + group(4, 10 * S, "g1", five, "5m", 1000) + group(7, 20 * S, "g0", five, "5m", 1000)
    assert "f" in checks(renumber(again))


def test_f_resync_group_must_contain_only_time_calls():
    bad = [rec(1, 0, role="S1", group="resync", boundary=1), rec(2, S, role="T", group="resync", boundary=1), rec(3, 2 * S, role="T", group="resync", boundary=1)]
    assert "f" in checks(bad)
    assert "f" in checks([rec(1, 0, role="T", group="resync", boundary=1)])         # fewer than 3 without a failure
    assert audit_pace([rec(i + 1, i * S, role="T", group="resync", boundary=1) for i in range(7)]).ok
    assert "f" in checks([rec(i + 1, i * S, role="T", group="resync", boundary=1) for i in range(8)])


# ---- (g) egress counters ----
def test_g_all_counters_must_equal_the_number_of_records():
    records = seq_of([0, 600 * MS, 1200 * MS])
    assert audit_pace(records, jsonl_count=3, wrapper_count=3, manifest_count=3).ok
    for kw in ({"jsonl_count": 2}, {"wrapper_count": 4}, {"manifest_count": 0}):
        assert "g" in checks(records, **kw)


def test_failures_are_reported_with_the_check_letter_and_sequence_number():
    result = audit_pace(seq_of([0, 100 * MS]))
    assert not result.ok and result.failures[0].check == "c" and result.failures[0].seq == 2
