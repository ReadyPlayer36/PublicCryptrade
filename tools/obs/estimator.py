"""Server-time to local-monotonic offset estimator (protocol v0.5, sections 5.2-5.4).

Model: server_time = mono + theta, |theta(m2) - theta(m1)| <= DELTA |m2 - m1|. A `/time` call with monotonic start
a, end b and integer server timestamp s (ms, truncated) bounds theta at a later time t >= b to
    [ s - b - DELTA (t - a) ,  s + 1 ms - a + DELTA (t - a) ].
All decisions use exact rational arithmetic (fractions.Fraction); exported intervals are rounded OUTWARD to whole
nanoseconds. The midpoint is never exposed for decisions. No wall clock is read anywhere in this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Iterable

from tools.obs.params import DELTA, FALLBACK_NS, MS, RETENTION_NS, W_MAX_NS


class SyncInadequate(RuntimeError):
    """No usable offset estimate (empty intersection or too uncertain)."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class TimeSample:
    """One `/time` call: monotonic start/end in ns and the integer server timestamp in ms."""

    a_ns: int
    b_ns: int
    s_ms: int

    def __post_init__(self) -> None:
        if not (_is_int(self.a_ns) and _is_int(self.b_ns) and _is_int(self.s_ms)):
            raise TypeError("TimeSample fields must be integers")
        if self.b_ns < self.a_ns:
            raise ValueError("a /time call cannot end before it starts")
        if self.s_ms < 0:
            raise ValueError("server timestamp must be non-negative")


def exact_interval(sample: TimeSample, t_ns: int) -> tuple[Fraction, Fraction]:
    """Exact theta interval (ns) of one sample at time t >= b (v0.5: both endpoints widen from a)."""
    if t_ns < sample.b_ns:
        raise ValueError("an interval is only defined at or after the sample's completion")
    s_ns = sample.s_ms * MS
    widening = DELTA * (t_ns - sample.a_ns)
    return (s_ns - sample.b_ns - widening, s_ns + MS - sample.a_ns + widening)


def interval(sample: TimeSample, t_ns: int) -> tuple[int, int]:
    """Same interval rounded outward to whole nanoseconds (lower floor, upper ceil)."""
    lo, hi = exact_interval(sample, t_ns)
    return (math.floor(lo), math.ceil(hi))


@dataclass(frozen=True)
class Estimate:
    lo: Fraction                 # theta_lo (ns)
    hi: Fraction                 # theta_hi (ns)
    samples: int
    used_fallback: bool

    @property
    def width(self) -> Fraction:
        return self.hi - self.lo

    def adequate(self, w_max_ns: int = W_MAX_NS) -> bool:
        return self.width <= w_max_ns          # exactly W_MAX is adequate, anything above is not

    def server_bounds(self, m_ns: int) -> tuple[Fraction, Fraction]:
        """Server-time interval (ns) at monotonic time m implied by this estimate."""
        return (m_ns + self.lo, m_ns + self.hi)


class OffsetEstimator:
    def __init__(self, *, retention_ns: int = RETENTION_NS, fallback_ns: int = FALLBACK_NS) -> None:
        self.retention_ns = retention_ns
        self.fallback_ns = fallback_ns
        self._samples: list[TimeSample] = []

    @property
    def samples(self) -> tuple[TimeSample, ...]:
        return tuple(self._samples)

    def add(self, sample: TimeSample) -> None:
        self._samples.append(sample)

    def retained(self, t_ns: int, *, window_ns: int | None = None) -> list[TimeSample]:
        """Samples completed by t whose completion is within the window (retention uses b_j >= t - window)."""
        window = self.retention_ns if window_ns is None else window_ns
        return [s for s in self._samples if s.b_ns <= t_ns and s.b_ns >= t_ns - window]

    @staticmethod
    def _intersect(samples: Iterable[TimeSample], t_ns: int) -> tuple[Fraction, Fraction] | None:
        lo: Fraction | None = None
        hi: Fraction | None = None
        count = 0
        for sample in samples:
            s_lo, s_hi = exact_interval(sample, t_ns)
            lo = s_lo if lo is None else max(lo, s_lo)
            hi = s_hi if hi is None else min(hi, s_hi)
            count += 1
        if count == 0 or lo is None or hi is None or lo > hi:
            return None
        return (lo, hi)

    def estimate(self, t_ns: int, *, allow_fallback: bool = True) -> Estimate | None:
        retained = self.retained(t_ns)
        both = self._intersect(retained, t_ns)
        if both is not None:
            return Estimate(both[0], both[1], len(retained), False)
        if not allow_fallback:
            return None
        recent = self.retained(t_ns, window_ns=self.fallback_ns)           # discard samples older than 60 s, once
        both = self._intersect(recent, t_ns)
        if both is None:
            return None
        return Estimate(both[0], both[1], len(recent), True)

    def adequate(self, t_ns: int, w_max_ns: int = W_MAX_NS) -> bool:
        estimate = self.estimate(t_ns)
        return estimate is not None and estimate.adequate(w_max_ns)

    # ----- deadlines (section 5.2) -----
    def deadline_exact(self, target_server_ms: int, now_ns: int) -> Fraction:
        """D(now) = X - theta_lo(now): the monotonic instant from which a request is certainly not early."""
        estimate = self.estimate(now_ns)
        if estimate is None:
            raise SyncInadequate("no offset estimate")
        return target_server_ms * MS - estimate.lo

    def closed_form_start_ns(self, target_server_ms: int, now_ns: int) -> int:
        """First integer-ns instant m with m >= D(m) for the samples retained at `now` (closed form).

        D(m) = min_j (X - s_j + b_j + DELTA (m - a_j)) and m >= D(m) holds iff m >= min_j m_j with
        m_j = (X - s_j + b_j - DELTA a_j) / (1 - DELTA).
        """
        retained = self.retained(now_ns)
        if not retained or self.estimate(now_ns) is None:
            raise SyncInadequate("no offset estimate")
        x_ns = target_server_ms * MS
        roots = [(x_ns - s.s_ms * MS + s.b_ns - DELTA * s.a_ns) / (1 - DELTA) for s in retained]
        return max(now_ns, math.ceil(min(roots)))


def wait_until_server_time(clock, estimator: OffsetEstimator, target_server_ms: int) -> int:
    """Wake loop of section 5.2: sleep to D(now), wake, recompute, repeat until now >= D(now). Returns the start.

    `clock` provides now_ns() and sleep_until_ns(t). Never returns early; lateness is not corrected.
    """
    while True:
        now = clock.now_ns()
        deadline = estimator.deadline_exact(target_server_ms, now)
        if now >= deadline:
            return now
        clock.sleep_until_ns(math.ceil(deadline))
