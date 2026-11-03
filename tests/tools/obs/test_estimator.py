"""Offline golden-vector and unit tests for the server-time -> monotonic estimator (protocol v0.5 sections 5.2-5.5)."""
import importlib.util
import json
import math
import random
from fractions import Fraction as F
from pathlib import Path

import pytest

from tools.obs.estimator import OffsetEstimator, SyncInadequate, TimeSample, exact_interval, interval, wait_until_server_time
from tools.obs.params import DELTA, MS, S
from tests.fixtures.obs_fakes import FakeClock

VECTORS = Path(__file__).resolve().parents[2] / "fixtures" / "vectors"
V = json.loads((VECTORS / "obs_estimator_vectors.json").read_text())


def ms(text: str) -> F:
    return F(text)                                   # exact decimal / rational string, milliseconds


def ns_sample(a, b, s) -> TimeSample:
    return TimeSample(int(F(a) * MS), int(F(b) * MS), int(F(s)))


def test_vectors_are_reproduced_by_the_independent_generator():
    spec = importlib.util.spec_from_file_location("generate_obs_vectors", VECTORS / "generate_obs_vectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build() == V
    text = (VECTORS / "generate_obs_vectors.py").read_text()
    assert "import tools" not in text and "from tools" not in text and "obs." not in text.replace("generate_obs_vectors", "")   # independent of the harness


def test_delta_is_one_hundred_ppm():
    assert DELTA == F(1, 10_000) and V["delta"] == "1/10000"


@pytest.mark.parametrize("case", V["gv1_gv2"], ids=["GV-1 at completion", "GV-2 aged 600 s"])
def test_gv1_gv2_interval_widens_both_endpoints_from_request_start(case):
    sample = ns_sample(case["a"], case["b"], case["s"])
    t_ns = int(ms(case["t"]) * MS)
    lo, hi = exact_interval(sample, t_ns)
    assert lo == ms(case["lo"]) * MS and hi == ms(case["hi"]) * MS
    assert hi - lo == ms(case["width"]) * MS
    assert lo < ms(case["old_lo"]) * MS                                                   # strictly wider than the v0.3 lower edge
    # the integer interval is rounded outward and never inside the exact one
    ilo, ihi = interval(sample, t_ns)
    assert ilo <= lo and ihi >= hi and ihi - ilo <= (hi - lo) + 2


def test_gv2_old_v03_lower_endpoint_is_rejected():
    case = V["gv1_gv2"][1]
    sample = ns_sample(case["a"], case["b"], case["s"])
    lo, _ = exact_interval(sample, 601_000 * MS)
    assert lo == F(1_699_999_999_994) * MS
    assert lo != F(case["old_lo"]) * MS
    assert F(case["old_lo"]) * MS - lo == F(18, 1000) * MS            # delta x RTT = 0.018 ms


def test_interval_is_undefined_before_completion():
    sample = TimeSample(1000, 5000, 1_700_000_000_000)
    with pytest.raises(ValueError):
        exact_interval(sample, 4999)


@pytest.mark.parametrize("bad", [(True, 2, 3), (1.5, 2, 3), (5, 2, 3), (1, 2, -1)])
def test_time_sample_validation(bad):
    with pytest.raises((TypeError, ValueError)):
        TimeSample(*bad)


def test_gv3_containment_for_all_drift_directions_generation_instants_and_truncation():
    block = V["gv3"]
    sample = ns_sample(block["a"], block["b"], block["s"])
    t_ns = int(ms(block["t"]) * MS)
    lo, hi = exact_interval(sample, t_ns)
    assert len(block["cases"]) == 12
    for case in block["cases"]:
        g, eps = ms(case["g"]), ms(case["eps"])
        rate = case["rate_sign"] * DELTA
        theta_t = (ms(block["s"]) + eps - g) + rate * (ms(block["t"]) - g)         # ms; ground-truth offset path
        assert lo <= theta_t * MS <= hi, case
        assert theta_t * MS - lo == ms(case["margin_lo"]) * MS
        assert hi - theta_t * MS == ms(case["margin_hi"]) * MS
    margins = {(c["g"], c["rate_sign"], c["eps"]): (c["margin_lo"], c["margin_hi"]) for c in block["cases"]}
    assert margins[("1180", -1, "0")][0] == "0.018"                    # on the v0.3 lower edge
    assert margins[("1000", 1, "0.999999999")][1] == "0.000000001"      # on the upper edge
    assert margins[("1000", 1, "0")] == ("300", "1")
    assert margins[("1000", -1, "0")] == ("180", "121")


def test_random_drift_paths_always_stay_inside_the_interval_and_deadline_is_never_early():
    rng = random.Random(20261024)
    for _ in range(400):
        theta0 = F(1_700_000_000_000 * MS) + rng.randrange(-10**9, 10**9)            # ns
        rate = F(rng.choice((-1, 1)) * rng.randrange(0, 101), 1_000_000)             # |rate| <= 100 ppm
        theta = lambda m: theta0 + rate * m                                           # noqa: E731
        estimator = OffsetEstimator()
        mono = 1_000 * MS
        for _ in range(rng.randrange(1, 8)):
            a = mono
            b = a + rng.randrange(20, 400) * MS + rng.randrange(0, MS)
            g = a + rng.randrange(0, b - a + 1)
            server_ns = g + theta(g)
            s_ms = math.floor(server_ns / MS)
            estimator.add(TimeSample(a, b, s_ms))
            mono = b + rng.randrange(500, 3000) * MS
        t = mono + rng.randrange(0, 20) * S
        estimate = estimator.estimate(t)
        assert estimate is not None
        assert estimate.lo <= theta(t) <= estimate.hi
        target_ms = (t + theta(t)) // MS + rng.randrange(1, 200_000)
        start = wait_until_server_time(FakeClock(t), estimator, int(target_ms))
        assert start + theta(start) >= int(target_ms) * MS                            # certainly not early


def test_gv4_uncertainty_boundary_is_inclusive_at_exactly_w_max():
    for case in V["gv4"]:
        sample = ns_sample(case["a"], case["b"], case["s"])
        estimator = OffsetEstimator()
        estimator.add(sample)
        t_ns = int(ms(case["t"]) * MS)
        estimate = estimator.estimate(t_ns)
        assert estimate.width == ms(case["width"]) * MS
        assert estimator.adequate(t_ns) is case["adequate"]
    assert V["gv4"][0]["width"] == "250" and V["gv4"][1]["width"] == "250.001"


def test_width_exactly_one_nanosecond_over_w_max_is_not_adequate():
    a, b = 1_000 * MS, 1_200 * MS                                                    # RTT 200 ms: width = 201 ms + 2 delta (t - a)
    estimator = OffsetEstimator()
    estimator.add(TimeSample(a, b, 1_700_000_001_300))
    t_equal = a + 245_000 * MS                                                       # width exactly 250 ms
    t_over = t_equal + 5_000                                                         # +5000 ns of age adds exactly 1 ns of width
    assert estimator.estimate(t_equal).width == 250 * MS and estimator.adequate(t_equal)
    assert estimator.estimate(t_over).width == 250 * MS + 1 and not estimator.adequate(t_over)
    assert not estimator.adequate(t_equal, w_max_ns=250 * MS - 1)


def test_maximum_widening_at_the_edge_of_the_retention_window_is_123_4_ms():
    assert V["retention_edge"] == {"age_s": 617, "max_added_width_ms": "123.4"}
    a = 1_000 * MS
    b = a + 17 * S                                                                   # a request lasting the full 17 s deadline
    estimator = OffsetEstimator()
    estimator.add(TimeSample(a, b, 1_700_000_000_000))
    t = b + 600 * S                                                                  # b_j >= t - 600 s holds with equality
    assert estimator.retained(t) and not estimator.retained(t + 1)
    assert t - a == 617 * S
    lo, hi = exact_interval(estimator.samples[0], t)
    assert hi - lo - (17 * S + MS) == F(1234, 10) * MS                               # 2 delta (t - a) = 123.4 ms


def test_empty_intersection_discards_samples_older_than_60_s_once():
    estimator = OffsetEstimator()
    estimator.add(TimeSample(0, 100 * MS, 1_700_000_000_100))                         # old sample, offset 1.7e12 ms
    estimator.add(TimeSample(100 * S, 100 * S + 100 * MS, 1_700_000_900_000))        # recent sample, inconsistent offset
    t = 100 * S + 200 * MS
    assert estimator.estimate(t, allow_fallback=False) is None
    estimate = estimator.estimate(t)
    assert estimate is not None and estimate.used_fallback and estimate.samples == 1
    estimator.add(TimeSample(100 * S + 300 * MS, 100 * S + 350 * MS, 1_700_001_000_000))     # also inconsistent with the recent one
    assert estimator.estimate(100 * S + 400 * MS) is None
    assert not estimator.adequate(100 * S + 400 * MS)


def test_no_samples_means_no_estimate_and_no_deadline():
    estimator = OffsetEstimator()
    assert estimator.estimate(5 * S) is None
    with pytest.raises(SyncInadequate):
        estimator.deadline_exact(1_700_000_000_000, 5 * S)
    with pytest.raises(SyncInadequate):
        estimator.closed_form_start_ns(1_700_000_000_000, 5 * S)


def test_samples_outside_the_retention_window_are_dropped_and_future_samples_ignored():
    estimator = OffsetEstimator()
    estimator.add(TimeSample(0, MS, 1_700_000_000_001))
    assert len(estimator.retained(600 * S + MS)) == 1                                # b = 1 ms, t - 600 s = 1 ms: kept (>=)
    assert len(estimator.retained(600 * S + MS + 1)) == 0                            # one ns older: dropped
    assert estimator.retained(0) == []                                              # not yet completed at t = 0


def test_gv5_admission_vector_inputs_are_consistent():
    block = V["gv5"]
    assert block["admitted_at_m_e"] is True and block["admitted_at_m_e_plus_1ns"] is False
    assert block["lower_at_m_e"] == block["limit"] and F(block["upper_minus_limit"]) == 221


@pytest.mark.parametrize("name", ["one", "two"])
def test_gv6_gv7_fixed_point_deadline(name):
    block = V["gv6_gv7"][name]
    estimator = OffsetEstimator()
    for a, b, s in block["samples"]:
        estimator.add(ns_sample(a, b, s))
    now = int(F(block["samples"][-1][1]) * MS)
    target = int(F(block["X"]))
    first = block["first_ns"]
    assert estimator.closed_form_start_ns(target, first) == first                    # closed form
    assert estimator.deadline_exact(target, first) <= first                          # the condition m >= D(m) holds at the first ns ...
    assert estimator.deadline_exact(target, first - 1) > first - 1                    # ... and fails one nanosecond earlier
    clock = FakeClock(now)
    started = wait_until_server_time(clock, estimator, target)
    assert started == first and len(clock.sleeps) >= 2                                # the deadline moves later after each wake
    assert block["ok_at_first"] is True and block["ok_one_ns_earlier"] is False


def test_gv6_exact_values_and_iteration():
    one = V["gv6_gv7"]["one"]
    assert one["first_ns"] == 300_030_003_001 and one["m_star_ms"] == "1000000000/3333"
    assert one["iteration_from_zero_ms"][:3] == ["300000", "300030", "300030.003"]
    assert V["gv6_gv7"]["two"]["first_ns"] == 300_018_001_801 and V["gv6_gv7"]["two"]["m_star_ms"] == "333320000/1111"
    theta = V["gv6_gv7"]["two"]["theta_at_300000"]
    estimator = OffsetEstimator()
    for a, b, s in V["gv6_gv7"]["two"]["samples"]:
        estimator.add(ns_sample(a, b, s))
    estimate = estimator.estimate(300_000 * MS)
    assert (estimate.lo, estimate.hi, estimate.width) == (F(theta["lo"]) * MS, F(theta["hi"]) * MS, F(theta["width"]) * MS)


def test_wake_lateness_is_not_corrected_and_never_early():
    block = V["gv6_gv7"]["one"]
    estimator = OffsetEstimator()
    for a, b, s in block["samples"]:
        estimator.add(ns_sample(a, b, s))
    clock = FakeClock(200 * MS)
    clock.wake_lateness_ns = 7_000_000                                                 # every wake is 7 ms late
    started = wait_until_server_time(clock, estimator, int(F(block["X"])))
    assert started >= block["first_ns"] and clock.sleeps and all(t <= started for t in clock.sleeps)
    assert estimator.deadline_exact(int(F(block["X"])), started) <= started


def test_estimator_module_never_uses_the_wall_clock_or_float_time():
    source = (Path(__file__).resolve().parents[3] / "tools" / "obs" / "estimator.py").read_text()
    assert "time.time" not in source and "datetime" not in source and "float(" not in source


def test_touching_intervals_form_a_single_point_estimate_not_an_empty_one():
    # Two identical requests (a = 0, b = 100 ms) evaluated at t = 500 s: each widens by 50 ms per side, so
    # upper1 = s1 + 1 + 50 ms and lower2 = s2 - 100 - 50 ms; they touch exactly when s2 = s1 + 201 ms.
    t = 500 * S
    base = 1_700_000_000_000

    def estimate(delta_ms):
        estimator = OffsetEstimator()
        estimator.add(TimeSample(0, 100 * MS, base))
        estimator.add(TimeSample(0, 100 * MS, base + delta_ms))
        return estimator.estimate(t)

    touching = estimate(201)
    assert touching is not None and touching.width == 0 and touching.lo == touching.hi
    assert estimate(200).width == 1 * MS                                               # overlapping by 1 ms
    assert estimate(202) is None                                                       # disjoint by 1 ms: empty, and no fallback sample remains
    assert touching.adequate()
