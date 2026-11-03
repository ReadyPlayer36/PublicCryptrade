"""Independent generator for the OBS estimator golden vectors (protocol v0.5, section 5.5).

Uses ONLY fractions and the formulas of the protocol; it must not import the harness. Run it to rewrite
obs_estimator_vectors.json; a test regenerates the vectors and compares them with the committed file.
All times in milliseconds as exact decimal / rational strings.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from fractions import Fraction as F
from pathlib import Path

DELTA = F(1, 10000)
MS_NS = 10**6


def fs(x: F) -> str:
    """Exact string: integer, finite decimal, or p/q."""
    x = F(x)
    if x.denominator == 1:
        return str(x.numerator)
    d = x.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        digits = 0
        while (x * 10**digits).denominator != 1:
            digits += 1
        n = int(x * 10**digits)
        sign = "-" if n < 0 else ""
        n = abs(n)
        text = str(n).rjust(digits + 1, "0")
        return f"{sign}{text[:-digits]}.{text[-digits:]}"
    return f"{x.numerator}/{x.denominator}"


def interval(a, b, s, t):
    w = DELTA * (t - a)
    return (s - b - w, s + 1 - a + w)


def old_lower(a, b, s, t):
    return s - b - DELTA * (t - b)


def build() -> dict:
    out: dict = {"delta": "1/10000"}
    a, b, s = F(1000), F(1180), F(1_700_000_001_234)
    cases = []
    for t in (F(1180), F(601_000)):
        lo, hi = interval(a, b, s, t)
        cases.append({"a": fs(a), "b": fs(b), "s": fs(s), "t": fs(t), "lo": fs(lo), "hi": fs(hi), "old_lo": fs(old_lower(a, b, s, t)), "width": fs(hi - lo)})
    out["gv1_gv2"] = cases

    t = F(601_000)
    lo, hi = interval(a, b, s, t)
    containment = []
    for g, sign, eps in itertools.product((F(1000), F(1090), F(1180)), (1, -1), (F(0), F(999_999_999, 10**9))):
        theta_t = (s + eps - g) + sign * DELTA * (t - g)
        containment.append({"g": fs(g), "rate_sign": sign, "eps": fs(eps), "margin_lo": fs(theta_t - lo), "margin_hi": fs(hi - theta_t), "inside": bool(lo <= theta_t <= hi)})
    out["gv3"] = {"a": fs(a), "b": fs(b), "s": fs(s), "t": fs(t), "cases": containment}

    a4, b4 = F(1000), F(1200)
    out["gv4"] = [{"a": fs(a4), "b": fs(b4), "s": "1700000001300", "t": fs(t4), "width": fs((b4 - a4) + 1 + 2 * DELTA * (t4 - a4)),
                   "adequate": bool((b4 - a4) + 1 + 2 * DELTA * (t4 - a4) <= 250)} for t4 in (F(246_000), F(246_005))]

    a5, b5, s5 = F(0), F(200), F(1_700_000_002_710)
    T, o, tol, m_e = F(1_700_000_100_000), F(0), F(2500), F(100_000)
    limit = T + o + tol

    def server_bounds(m):
        lo_, hi_ = interval(a5, b5, s5, m)
        return (m + lo_, m + hi_)

    low, up = server_bounds(m_e)
    low1, _ = server_bounds(m_e + F(1, MS_NS))
    out["gv5"] = {"a": fs(a5), "b": fs(b5), "s": fs(s5), "T": fs(T), "o": fs(o), "tol": fs(tol), "m_e": fs(m_e), "limit": fs(limit),
                  "lower_at_m_e": fs(low), "upper_at_m_e": fs(up), "admitted_at_m_e": bool(not low > limit),
                  "lower_at_m_e_plus_1ns": fs(low1), "admitted_at_m_e_plus_1ns": bool(not low1 > limit),
                  "upper_minus_limit": fs(up - limit)}

    X = F(1_700_000_300_000)

    def mstar(samples):
        return min((X - s_ + b_ - DELTA * a_) / (1 - DELTA) for a_, b_, s_ in samples)

    def D(samples, m):
        return min(X - s_ + b_ + DELTA * (m - a_) for a_, b_, s_ in samples)

    one = [(F(0), F(200), F(1_700_000_000_200))]
    two = one + [(F(100_000), F(100_060), F(1_700_000_100_062))]
    gv = {}
    for name, samples in (("one", one), ("two", two)):
        m = mstar(samples)
        first_ns = math.ceil(m * MS_NS)
        ok = F(first_ns, MS_NS) >= D(samples, F(first_ns, MS_NS))
        prev_ok = F(first_ns - 1, MS_NS) >= D(samples, F(first_ns - 1, MS_NS))
        gv[name] = {"samples": [[fs(x) for x in smp] for smp in samples], "X": fs(X), "m_star_ms": fs(m), "first_ns": first_ns,
                    "ok_at_first": bool(ok), "ok_one_ns_earlier": bool(prev_ok)}
    it = []
    m = F(0)
    for _ in range(5):
        m = D(one, m)
        it.append(fs(m))
    gv["one"]["iteration_from_zero_ms"] = it
    t = F(300_000)
    los = [s_ - b_ - DELTA * (t - a_) for a_, b_, s_ in two]
    his = [s_ + 1 - a_ + DELTA * (t - a_) for a_, b_, s_ in two]
    gv["two"]["theta_at_300000"] = {"lo": fs(max(los)), "hi": fs(min(his)), "width": fs(min(his) - max(los)), "lowers": [fs(x) for x in los], "uppers": [fs(x) for x in his]}
    out["gv6_gv7"] = gv

    out["retention_edge"] = {"max_added_width_ms": fs(2 * DELTA * 617_000), "age_s": 617}
    return out


if __name__ == "__main__":
    target = Path(__file__).with_name("obs_estimator_vectors.json")
    target.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {target}", file=sys.stderr)
