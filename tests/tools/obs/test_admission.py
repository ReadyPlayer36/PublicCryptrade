"""PACE-7 group admission: strict-boundary decisions in exact arithmetic (GV-5)."""
import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from tools.obs.admission import decide_admission
from tools.obs.estimator import OffsetEstimator, SyncInadequate, TimeSample
from tools.obs.params import MS, S

G = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "obs_estimator_vectors.json").read_text())["gv5"]


def estimator_from_vector() -> OffsetEstimator:
    estimator = OffsetEstimator()
    estimator.add(TimeSample(int(F(G["a"]) * MS), int(F(G["b"]) * MS), int(F(G["s"]))))
    return estimator


def decide(m_e_ns, **kw):
    params = dict(boundary_ms=int(F(G["T"])), offset_ms=int(F(G["o"])), tol_ms=int(F(G["tol"])))
    params.update(kw)
    return decide_admission(estimator_from_vector(), m_e_ns=m_e_ns, **params)


M_E = int(F(G["m_e"]) * MS)


def test_gv5_exactly_on_the_limit_is_admitted():
    decision = decide(M_E)
    assert decision.admitted and decision.reason == "ADMITTED"
    assert decision.lower_server_ns == decision.limit_ns == int(F(G["limit"]) * MS)
    assert decision.lower_server_ns == F(G["lower_at_m_e"]) * MS


def test_gv5_infeasible_by_one_nanosecond_is_skipped():
    decision = decide(M_E + 1)
    assert not decision.admitted and decision.reason == "MISSED-WINDOW"
    assert decision.lower_server_ns - decision.limit_ns == F(G["lower_at_m_e_plus_1ns"]) * MS - F(G["limit"]) * MS
    assert 0 < decision.lower_server_ns - decision.limit_ns < 1                   # 0.9999 ns past the limit


def test_gv5_one_nanosecond_before_the_limit_is_admitted():
    assert decide(M_E - 1).admitted


def test_only_theta_lo_decides_a_possibly_late_group_is_admitted_and_left_to_v1():
    decision = decide(M_E)
    assert decision.upper_server_ns - decision.limit_ns == F(G["upper_minus_limit"]) * MS      # theta_hi puts it 221 ms past the limit
    assert decision.upper_server_ns > decision.limit_ns and decision.admitted


def test_tolerance_and_offset_move_the_limit_exactly():
    assert not decide(M_E, tol_ms=int(F(G["tol"])) - 1).admitted                  # a 1 ms tighter window makes it infeasible
    assert decide(M_E, offset_ms=1).admitted                                      # a 1 ms later nominal offset makes room
    assert decide(M_E + 5_000_000_000, tol_ms=int(F(G["tol"])) + 5_000).admitted           # 5 s later but 5 s more tolerance


def test_decision_carries_the_evidence_fields():
    decision = decide(M_E)
    assert decision.m_e_ns == M_E and decision.theta_lo <= decision.theta_hi
    assert decision.upper_server_ns - decision.lower_server_ns == decision.theta_hi - decision.theta_lo


def test_no_usable_estimate_raises_instead_of_guessing():
    with pytest.raises(SyncInadequate):
        decide_admission(OffsetEstimator(), m_e_ns=5 * S, boundary_ms=1_700_000_100_000, offset_ms=0, tol_ms=2500)
    estimator = OffsetEstimator()
    estimator.add(TimeSample(0, 100 * MS, 1_700_000_000_100))
    with pytest.raises(SyncInadequate):                                           # the only sample is older than the retention window
        decide_admission(estimator, m_e_ns=700 * S, boundary_ms=1_700_000_100_000, offset_ms=0, tol_ms=2500)


def test_the_decision_records_the_instant_it_was_taken():
    explicit = decide(M_E + 1, decided_at_ns=M_E - 7)
    assert explicit.decided_at_ns == M_E - 7 and explicit.m_e_ns == M_E + 1
    assert decide(M_E + 1).decided_at_ns == M_E + 1                               # by default the decision is taken at m_e itself
    assert decide(M_E, decided_at_ns=M_E).decided_at_ns == M_E


def test_a_decision_cannot_be_taken_after_the_earliest_start_it_is_about():
    with pytest.raises(ValueError):
        decide(M_E, decided_at_ns=M_E + 1)
