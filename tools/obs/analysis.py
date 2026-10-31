"""Pure OBS-01/OBS-02 analysis: finality rule, bound_k, stability, lag formula (protocol v0.5, sections 7.1-7.3, 8).

Everything here is a pure function of explicit arguments. There is NO default lag, NO local clock, NO wall clock,
NO I/O and NO randomness. Any missing, NaN, negative, non-monotonic, boolean/string-coerced or empty input raises a
subclass of ``ManifestError`` (fail closed); nothing is repaired or defaulted.

This module never CHOOSES or APPROVES a lag. ``lag_candidate`` only evaluates the section-8 formula for a given
``L_obs`` and returns an unapproved, derived candidate (or ``None`` when the protocol says INCONCLUSIVE). Approval is
a human/reviewer act (LAG-01 / OBS-03).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Sequence
import math

from tools.obs.params import DELTA, MS
from tools.obs.runstore import ManifestError

INTERVAL_MS: dict[str, int] = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
TUPLES: dict[str, tuple[int, ...]] = {          # section 7.1: kline field indices compared per tuple
    "T_matrix": (1, 2, 3, 4),
    "T_app": (1, 2, 3, 4, 5, 6, 7, 8),
    "T_all": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
}
OBSERVATIONS = 4                                # groups g0..g3 (offsets +0, +2, +10, +60 s)
MIN_SAMPLES = 1
# 2 UTC days x 3 attempts x 21 samples per day (session X: 11 x 5m + 4 at the 4h boundary = 15; session Y: 6) (sections 5.1, 6, 9)
MAX_SAMPLES = 126
MAX_L_OBS_MS = 60_000                           # above this (or any unbounded sample) no lag is proposed
MIN_PAD_MS = 2_000
_DECIMAL_TEXT = re.compile(r"[0-9]+(\.[0-9]+)?")
_STR_FIELDS = (1, 2, 3, 4, 5, 7, 9, 10)
_INT_FIELDS = (0, 6, 8)


class AnalysisError(ManifestError):
    """Base class of every analysis input rejection."""


class MissingValueError(AnalysisError):
    """A required input is None / absent."""


class InvalidTypeError(AnalysisError):
    """Wrong type, including bool-as-int, float-as-int and str-as-number coercion attempts."""


class InvalidValueError(AnalysisError):
    """Right type, impossible value (negative, NaN/Infinity text, malformed decimal text, unknown timeframe, ...)."""


class NonMonotonicError(AnalysisError):
    """Timestamps or bounds that must not decrease do decrease."""


class EmptySampleError(AnalysisError):
    """No samples were supplied."""


class SampleCountError(AnalysisError):
    """More samples than the protocol can produce."""


class ReferenceMissingError(AnalysisError):
    """The +180 s reference row is missing (REFERENCE-MISSING, section 6)."""


class MalformedRowError(AnalysisError):
    """A kline row is not structurally valid (section 7.1)."""


# ----------------------------------------------------------------------------------------------- strict scalars
def _int(name: str, value: object, *, minimum: int | None) -> int:
    if value is None:
        raise MissingValueError(f"{name} is required")
    if isinstance(value, bool):
        raise InvalidTypeError(f"{name} must be an int, not bool")
    if not isinstance(value, int):
        raise InvalidTypeError(f"{name} must be an int, not {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise InvalidValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _interval_ms(timeframe: object) -> int:
    if timeframe is None:
        raise MissingValueError("timeframe is required")
    if not isinstance(timeframe, str):
        raise InvalidTypeError(f"timeframe must be a str, not {type(timeframe).__name__}")
    if timeframe not in INTERVAL_MS:
        raise InvalidValueError(f"unsupported timeframe {timeframe!r}")
    return INTERVAL_MS[timeframe]


# ----------------------------------------------------------------------------------------------- finality rule
def is_final(close_time_ms: int, server_time_ms: int, lag_ms: int) -> bool:
    """Frozen rule: final iff close_time_ms < B, B = S - L. Strict inequality; no default for ``lag_ms``."""
    close = _int("close_time_ms", close_time_ms, minimum=0)
    server = _int("server_time_ms", server_time_ms, minimum=0)
    lag = _int("lag_ms", lag_ms, minimum=0)
    return close < server - lag


# ----------------------------------------------------------------------------------------------- bound_k (section 8)
def bound_k_ms(s1_ms: int, boundary_ms: int, mono_start_s1_ns: int, mono_end_k_ns: int) -> int:
    """bound_k = (s1 - T) + 1 + ceil((mono_end_k - mono_start_S1) x (1 + delta)) in integer ms (exact rational maths)."""
    s1 = _int("s1_ms", s1_ms, minimum=0)
    boundary = _int("boundary_ms", boundary_ms, minimum=0)
    start = _int("mono_start_s1_ns", mono_start_s1_ns, minimum=0)
    end = _int("mono_end_k_ns", mono_end_k_ns, minimum=0)
    if end < start:
        raise NonMonotonicError(f"mono_end_k_ns {end} is earlier than mono_start_s1_ns {start}")
    if s1 < boundary:
        raise InvalidValueError(f"s1_ms {s1} is before boundary_ms {boundary}")
    elapsed_ms = Fraction(end - start, MS)
    return (s1 - boundary) + 1 + math.ceil(elapsed_ms * (1 + DELTA))


# ----------------------------------------------------------------------------------------------- rows (section 7.1)
def _check_label(label: object) -> str:
    if label is None:
        raise MissingValueError("label is required")
    if not isinstance(label, str):
        raise InvalidTypeError(f"label must be a str, not {type(label).__name__}")
    return label


def _check_row_shape(row: object, label: str) -> None:
    """Shape and per-field type/text validity of a non-None row. Never raises anything but AnalysisError."""
    if row is None:
        raise MissingValueError(f"{label} is required")
    if not isinstance(row, (list, tuple)):
        raise MalformedRowError(f"{label} must be a list or tuple, not {type(row).__name__}")
    if len(row) != 12:
        raise MalformedRowError(f"{label} must have exactly 12 elements, got {len(row)}")
    for index in _INT_FIELDS:
        value = row[index]
        if isinstance(value, bool) or not isinstance(value, int):
            raise MalformedRowError(f"{label}[{index}] must be an int, not {type(value).__name__}")
    for index in _STR_FIELDS:
        value = row[index]
        if not isinstance(value, str):
            raise MalformedRowError(f"{label}[{index}] must be a decimal string, not {type(value).__name__}")
        if not _DECIMAL_TEXT.fullmatch(value):
            raise MalformedRowError(f"{label}[{index}] is not a finite non-negative decimal string: {value!r}")
    if not isinstance(row[11], str):
        raise MalformedRowError(f"{label}[11] must be a str, not {type(row[11]).__name__}")
    if row[8] < 0:
        raise MalformedRowError(f"{label}[8] must be >= 0, got {row[8]}")


def validate_row(row: object, *, expected_open_ms: int, interval_ms: int, label: str) -> None:
    """Structural validity of one returned kline row. Any violation is an incident (wrong shape), not instability."""
    name = _check_label(label)
    expected_open = _int("expected_open_ms", expected_open_ms, minimum=0)
    interval = _int("interval_ms", interval_ms, minimum=1)
    _check_row_shape(row, name)
    if row[0] != expected_open:
        raise MalformedRowError(f"{name}[0] open time {row[0]} != expected {expected_open}")
    if row[6] != expected_open + interval - 1:
        raise MalformedRowError(f"{name}[6] close time {row[6]} != expected {expected_open + interval - 1}")


def _check_indices(indices: object) -> tuple[int, ...]:
    if indices is None:
        raise MissingValueError("indices is required")
    if not isinstance(indices, (list, tuple)):
        raise InvalidTypeError(f"indices must be a list or tuple, not {type(indices).__name__}")
    if len(indices) == 0:
        raise InvalidValueError("indices must not be empty")            # an empty comparison would be vacuously equal
    checked = []
    for position, index in enumerate(indices):
        value = _int(f"indices[{position}]", index, minimum=None)
        if not 0 <= value <= 10:                                       # index 11 ("ignore") is never compared (section 7.1)
            raise InvalidValueError(f"indices[{position}] must be between 0 and 10, got {value}")
        checked.append(value)
    return tuple(checked)


def _equal(left: Sequence[Any], right: Sequence[Any], indices: tuple[int, ...]) -> bool:
    for index in indices:
        a, b = left[index], right[index]
        if index in _INT_FIELDS:
            if a != b:
                return False
        elif Decimal(a) != Decimal(b):
            return False
    return True


def rows_equal(left: Sequence[Any] | None, right: Sequence[Any] | None, indices: Sequence[int]) -> bool:
    """Section 7.2: integers by value, decimal strings by numeric Decimal equality; an absent row (None) equals nothing.

    Every non-None row is shape-validated first, so malformed input raises AnalysisError, never IndexError/TypeError.
    """
    checked = _check_indices(indices)
    if left is not None:
        _check_row_shape(left, "left")
    if right is not None:
        _check_row_shape(right, "right")
    if left is None or right is None:
        return False
    return _equal(left, right, checked)


def stable_from(observations: Sequence[Sequence[Any] | None], reference: Sequence[Any] | None, indices: Sequence[int]) -> int | None:
    """Section 7.3: smallest i* with observations i*..3 all equal to the reference, else None (UNBOUNDED within +60 s).

    The reference and ALL four observations are validated before any comparison, so a malformed row can never hide
    behind an earlier mismatch.
    """
    if reference is None:
        raise ReferenceMissingError("reference row is missing")
    if observations is None:
        raise MissingValueError("observations is required")
    if not isinstance(observations, (list, tuple)):
        raise InvalidTypeError(f"observations must be a list or tuple, not {type(observations).__name__}")
    if len(observations) != OBSERVATIONS:
        raise InvalidValueError(f"expected {OBSERVATIONS} observations, got {len(observations)}")
    checked = _check_indices(indices)
    _check_row_shape(reference, "reference")
    for i, row in enumerate(observations):
        if row is not None:
            _check_row_shape(row, f"observations[{i}]")
    first: int | None = None
    for i in range(OBSERVATIONS - 1, -1, -1):
        row = observations[i]
        if row is None or not _equal(row, reference, checked):
            break
        first = i
    return first


# ----------------------------------------------------------------------------------------------- lag formula (section 8)
@dataclass(frozen=True)
class LagCandidate:
    """A DERIVED, UNAPPROVED value of the section-8 formula. It is not a decision and carries no approval flag."""

    l_obs_ms: int
    pad_ms: int
    l_raw_ms: int
    l_ms: int


def lag_candidate(l_obs_ms: int) -> LagCandidate | None:
    """Section 8: M = max(2000, L_obs) (stored as pad_ms); L_raw = L_obs + M; L = ceil(L_raw / 1000) x 1000.

    None (INCONCLUSIVE) if L_obs > 60000.
    """
    l_obs = _int("l_obs_ms", l_obs_ms, minimum=0)
    if l_obs > MAX_L_OBS_MS:
        return None
    pad = max(MIN_PAD_MS, l_obs)
    raw = l_obs + pad
    return LagCandidate(l_obs, pad, raw, -(-raw // 1000) * 1000)


# ----------------------------------------------------------------------------------------------- samples and analysis
@dataclass(frozen=True)
class SampleInput:
    """One sample = one timeframe at one boundary: 4 observations, their bound_k values and the +180 s reference."""

    timeframe: str
    boundary_ms: int
    observations: tuple[Sequence[Any] | None, ...]
    bounds_ms: tuple[int, ...]
    reference: Sequence[Any] | None

    def __post_init__(self) -> None:
        interval = _interval_ms(self.timeframe)
        boundary = _int("boundary_ms", self.boundary_ms, minimum=0)
        if boundary % interval != 0:
            raise InvalidValueError(f"boundary_ms {boundary} is not aligned to {self.timeframe}")
        if not isinstance(self.observations, tuple) or not isinstance(self.bounds_ms, tuple):
            raise InvalidTypeError("observations and bounds_ms must be tuples")
        if len(self.observations) != OBSERVATIONS or len(self.bounds_ms) != OBSERVATIONS:
            raise InvalidValueError(f"observations and bounds_ms must each have {OBSERVATIONS} entries")
        previous = -1
        for i, bound in enumerate(self.bounds_ms):
            value = _int(f"bounds_ms[{i}]", bound, minimum=0)
            if value < previous:
                raise NonMonotonicError(f"bounds_ms[{i}] {value} is earlier than bounds_ms[{i - 1}] {previous}")
            previous = value
        if self.reference is None:
            raise ReferenceMissingError("reference row is missing")
        expected_open = boundary - interval
        validate_row(self.reference, expected_open_ms=expected_open, interval_ms=interval, label="reference")
        for i, row in enumerate(self.observations):
            if row is not None:                                   # an empty response is a legal "absent" observation
                validate_row(row, expected_open_ms=expected_open, interval_ms=interval, label=f"observations[{i}]")


@dataclass(frozen=True)
class TupleResult:
    name: str
    sample_count: int
    unbounded_count: int
    l_obs_ms: int | None                    # None if any sample is unbounded
    candidate: LagCandidate | None          # unapproved formula value, None if INCONCLUSIVE


@dataclass(frozen=True)
class AnalysisResult:
    results: tuple[TupleResult, ...]        # T_matrix, T_app, T_all in that order; T_app is the recommended basis

    def by_name(self, name: str) -> TupleResult:
        for result in self.results:
            if result.name == name:
                return result
        raise InvalidValueError(f"unknown tuple {name!r}")


def analyze_samples(samples: Sequence[SampleInput]) -> AnalysisResult:
    """Max time-to-stable bound over all samples per tuple, then the section-8 formula. Chooses and approves nothing."""
    if samples is None:
        raise MissingValueError("samples is required")
    if isinstance(samples, (str, bytes)) or not isinstance(samples, (list, tuple)):
        raise InvalidTypeError(f"samples must be a list or tuple, not {type(samples).__name__}")
    if len(samples) < MIN_SAMPLES:
        raise EmptySampleError("no samples")
    if len(samples) > MAX_SAMPLES:
        raise SampleCountError(f"{len(samples)} samples exceed the maximum of {MAX_SAMPLES}")
    for position, sample in enumerate(samples):
        if not isinstance(sample, SampleInput):
            raise InvalidTypeError(f"samples[{position}] must be a SampleInput, not {type(sample).__name__}")
    results = []
    for name, indices in TUPLES.items():
        worst = 0
        unbounded = 0
        for sample in samples:
            first = stable_from(sample.observations, sample.reference, indices)
            if first is None:
                unbounded += 1
            else:
                worst = max(worst, sample.bounds_ms[first])
        l_obs = None if unbounded else worst
        results.append(TupleResult(name, len(samples), unbounded, l_obs, None if l_obs is None else lag_candidate(l_obs)))
    return AnalysisResult(tuple(results))
