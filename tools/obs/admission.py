"""PACE-7: group admission. A group is skipped iff even its earliest possible server time is already past the window."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from tools.obs.estimator import OffsetEstimator, SyncInadequate
from tools.obs.params import MS


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    m_e_ns: int
    theta_lo: Fraction
    theta_hi: Fraction
    lower_server_ns: Fraction        # m_e + theta_lo
    upper_server_ns: Fraction        # m_e + theta_hi (diagnostic only; never decides)
    limit_ns: int                    # T + o + tol
    reason: str


def decide_admission(estimator: OffsetEstimator, *, m_e_ns: int, boundary_ms: int, offset_ms: int, tol_ms: int) -> AdmissionDecision:
    """SKIP (MISSED-WINDOW) iff m_e + theta_lo > T + o + tol (strict, exact arithmetic). Equality is admitted, a merely
    possibly-late group (only theta_hi past the limit) is admitted and later judged by the measured S1."""
    estimate = estimator.estimate(m_e_ns)
    if estimate is None:
        raise SyncInadequate("no offset estimate at the admission instant")
    limit_ns = (boundary_ms + offset_ms + tol_ms) * MS
    lower, upper = estimate.server_bounds(m_e_ns)
    admitted = not (lower > limit_ns)
    return AdmissionDecision(admitted, m_e_ns, estimate.lo, estimate.hi, lower, upper, limit_ns,
                             "ADMITTED" if admitted else "MISSED-WINDOW")
