"""Independent generator for the OBS analysis golden vectors (protocol v0.5, sections 7-8).

Uses ONLY the standard library and the formulas of the protocol; it must not import the harness. Run it to rewrite
obs_analysis_vectors.json; a test regenerates the vectors and compares them with the committed file.
Expected values are derived with formulations that differ from the implementation (e.g. finality as `S - close > L`,
the lag via a loop over whole seconds, bound_k via exact Fractions).
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction as F
from pathlib import Path

DELTA = F(1, 10000)
MS_NS = 10**6
INTERVALS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
O = 1_767_571_200_000                       # 2026-01-05T00:00:00Z, aligned to every interval
MAX_SAMPLES = 2 * 3 * 21


def row(open_ms, interval, *, o="100.0", h="101.0", l="99.0", c="100.5", v="10.0", qv="1005.0", n=100,
        tbb="5.0", tbq="502.5", ignore="0", close=None):
    return [open_ms, o, h, l, c, v, open_ms + interval - 1 if close is None else close, qv, n, tbb, tbq, ignore]


def ceil_div(a, b):
    return -((-a) // b)


def lag_formula(l_obs):
    if l_obs > 60_000:
        return None
    pad = max(2000, l_obs)
    raw = l_obs + pad
    sec = 0
    while sec * 1000 < raw:                # smallest whole-second multiple >= raw
        sec += 1
    return {"l_obs_ms": l_obs, "pad_ms": pad, "l_raw_ms": raw, "l_ms": sec * 1000}


def bound(s1, T, start_ns, end_ns):
    elapsed = F(end_ns - start_ns, MS_NS) * (1 + DELTA)
    c = elapsed.numerator // elapsed.denominator
    if elapsed != c:
        c += 1
    return (s1 - T) + 1 + c


def tuples_stable(obs, ref, idx):
    eq = lambda a, b: a is not None and all((a[i] == b[i]) if i in (0, 6, 8) else (F(a[i]) == F(b[i])) for i in idx)
    first = None
    for i in (3, 2, 1, 0):
        if not eq(obs[i], ref):
            break
        first = i
    return first


def build():
    out = {"delta": "1/10000", "max_samples": MAX_SAMPLES}

    # finality: B-1, B, B+1 at each interval, two lags each; row = close_time_ms, S, L
    fin = []
    for tf, I in INTERVALS.items():
        for lag in (2000, 7000):
            S = O + 40 * I + 123
            B = S - lag
            for delta_b in (-1, 0, 1):
                close = B + delta_b
                fin.append({"timeframe": tf, "close_time_ms": close, "server_time_ms": S, "lag_ms": lag,
                            "offset_from_B": delta_b, "final": (S - close) > lag})
    out["finality"] = fin

    # bound_k
    T = O + 14_400_000
    bk = []
    for name, s1_off, start, end in (
        ("zero elapsed", 0, 5_000_000_000, 5_000_000_000),
        ("exactly representable 10000 ms", 0, 0, 10_000 * MS_NS),
        ("one ns above exact", 0, 0, 10_000 * MS_NS + 1),
        ("one ns below exact", 0, 0, 10_000 * MS_NS - 1),
        ("s1 after boundary, 0.7 s", 450, 1_000_000_000, 1_700_000_000),
        ("window edge 17 s", 2_400, 0, 17_000 * MS_NS),
        ("sub-ms elapsed", 0, 10, 11),
    ):
        s1 = T + s1_off
        bk.append({"name": name, "s1_ms": s1, "boundary_ms": T, "mono_start_s1_ns": start, "mono_end_k_ns": end,
                   "bound_ms": bound(s1, T, start, end)})
    out["bound_k"] = bk

    # lag formula: tier edges, both sides of every threshold, rounding edges
    pts = [0, 1, 999, 1000, 1001, 1234, 1999, 2000, 2001, 3200, 4999, 5000, 5001, 9999, 10000, 10001, 59999, 60000, 60001]
    out["lag"] = [{"l_obs_ms": p, "expected": lag_formula(p)} for p in pts]

    # stability on one 5m sample per scenario
    I = INTERVALS["5m"]
    Tb = O + 12 * I
    op = Tb - I
    ref = row(op, I)
    bounds = [700, 2900, 10_800, 61_000]
    differ = {"price": row(op, I, c="100.6"), "volume": row(op, I, v="10.1"), "trades": row(op, I, n=101),
              "close_time": None, "taker": row(op, I, tbb="5.1"), "text_only": row(op, I, o="100.00", v="10.000")}
    scen = []

    def add(name, observations):
        res = {}
        for tname, idx in (("T_matrix", (1, 2, 3, 4)), ("T_app", tuple(range(1, 9))), ("T_all", tuple(range(1, 11)))):
            f = tuples_stable(observations, ref, idx)
            res[tname] = {"stable_from": f, "bound_ms": None if f is None else bounds[f]}
        scen.append({"name": name, "timeframe": "5m", "boundary_ms": Tb, "observations": observations,
                     "bounds_ms": bounds, "reference": ref, "expected": res})

    add("stable from 0", [ref, ref, ref, ref])
    add("stable from 1", [differ["price"], ref, ref, ref])
    add("stable from 2", [differ["price"], differ["price"], ref, ref])
    add("stable from 3", [differ["price"]] * 3 + [ref])
    add("unbounded", [ref, ref, ref, differ["price"]])
    add("empty response at 0 then stable", [None, ref, ref, ref])
    add("empty response at 3 is unbounded", [ref, ref, ref, None])
    add("flap: equal, differ, equal, equal", [ref, differ["price"], ref, ref])
    add("raw text only difference is stable", [differ["text_only"]] * 4)
    add("volume only differs at 0: matrix stable 0, app stable 1", [differ["volume"], ref, ref, ref])
    add("trade count only differs at 0", [differ["trades"], ref, ref, ref])
    add("taker field only differs at 0: all stable 1, app stable 0", [differ["taker"], ref, ref, ref])
    out["stability"] = [s for s in scen]

    # aggregation scenarios built from stability scenarios (max over samples per tuple)
    def l_obs_of(sc_list, tname):
        vals = [s["expected"][tname]["bound_ms"] for s in sc_list]
        return None if None in vals else max(vals)

    groups = {
        "single sample": [scen[0]],
        "max over three samples": [scen[0], scen[1], scen[2]],
        "one unbounded sample blocks every tuple it differs on": [scen[0], scen[4]],
        "tuple dependent": [scen[0], scen[9], scen[11]],
    }
    agg = []
    for gname, members in groups.items():
        exp = {}
        for tname in ("T_matrix", "T_app", "T_all"):
            lo = l_obs_of(members, tname)
            exp[tname] = {"l_obs_ms": lo, "unbounded": sum(1 for s in members if s["expected"][tname]["bound_ms"] is None),
                          "candidate": None if lo is None else lag_formula(lo)}
        agg.append({"name": gname, "sample_names": [s["name"] for s in members], "expected": exp})
    out["aggregation"] = agg
    out["sizes"] = {"min_samples": 1, "max_samples": MAX_SAMPLES}

    # rejection vectors (exact exception class name and exact message)
    rej = []

    def r(fn, args, exc, msg, name):
        rej.append({"name": name, "fn": fn, "args": args, "exc": exc, "message": msg})

    f3 = {"close_time_ms": 1000, "server_time_ms": 10_000, "lag_ms": 2000}
    nan = {"$float": "nan"}
    for fld in f3:
        r("is_final", {**f3, fld: None}, "MissingValueError", f"{fld} is required", f"is_final {fld} missing")
        r("is_final", {**f3, fld: True}, "InvalidTypeError", f"{fld} must be an int, not bool", f"is_final {fld} bool")
        r("is_final", {**f3, fld: "1000"}, "InvalidTypeError", f"{fld} must be an int, not str", f"is_final {fld} str")
        r("is_final", {**f3, fld: 1.5}, "InvalidTypeError", f"{fld} must be an int, not float", f"is_final {fld} float")
        r("is_final", {**f3, fld: nan}, "InvalidTypeError", f"{fld} must be an int, not float", f"is_final {fld} nan")
        r("is_final", {**f3, fld: -1}, "InvalidValueError", f"{fld} must be >= 0, got -1", f"is_final {fld} negative")
    bk0 = {"s1_ms": T, "boundary_ms": T, "mono_start_s1_ns": 10, "mono_end_k_ns": 20}
    r("bound_k_ms", {**bk0, "mono_end_k_ns": 9}, "NonMonotonicError",
      "mono_end_k_ns 9 is earlier than mono_start_s1_ns 10", "bound_k end before start")
    r("bound_k_ms", {**bk0, "s1_ms": T - 1}, "InvalidValueError", f"s1_ms {T - 1} is before boundary_ms {T}", "bound_k s1 before boundary")
    for fld in bk0:
        r("bound_k_ms", {**bk0, fld: None}, "MissingValueError", f"{fld} is required", f"bound_k {fld} missing")
        r("bound_k_ms", {**bk0, fld: False}, "InvalidTypeError", f"{fld} must be an int, not bool", f"bound_k {fld} bool")
        r("bound_k_ms", {**bk0, fld: "5"}, "InvalidTypeError", f"{fld} must be an int, not str", f"bound_k {fld} str")
        r("bound_k_ms", {**bk0, fld: nan}, "InvalidTypeError", f"{fld} must be an int, not float", f"bound_k {fld} nan")
        r("bound_k_ms", {**bk0, fld: -1}, "InvalidValueError", f"{fld} must be >= 0, got -1", f"bound_k {fld} negative")
    r("lag_candidate", {"l_obs_ms": None}, "MissingValueError", "l_obs_ms is required", "lag missing")
    r("lag_candidate", {"l_obs_ms": True}, "InvalidTypeError", "l_obs_ms must be an int, not bool", "lag bool")
    r("lag_candidate", {"l_obs_ms": "1000"}, "InvalidTypeError", "l_obs_ms must be an int, not str", "lag str")
    r("lag_candidate", {"l_obs_ms": 1000.0}, "InvalidTypeError", "l_obs_ms must be an int, not float", "lag float")
    r("lag_candidate", {"l_obs_ms": nan}, "InvalidTypeError", "l_obs_ms must be an int, not float", "lag nan")
    r("lag_candidate", {"l_obs_ms": -1}, "InvalidValueError", "l_obs_ms must be >= 0, got -1", "lag negative")

    # sample-construction rejections: base sample + one mutation
    base = {"timeframe": "5m", "boundary_ms": Tb, "observations": [ref] * 4, "bounds_ms": [700, 2900, 10_800, 11_000], "reference": ref}

    def mut_row(i, value):
        x = list(ref)
        x[i] = value
        return x

    def s(name, exc, msg, **kw):
        args = dict(base)
        args.update(kw)
        r("SampleInput", args, exc, msg, name)

    s("sample timeframe missing", "MissingValueError", "timeframe is required", timeframe=None)
    s("sample timeframe unknown", "InvalidValueError", "unsupported timeframe '2m'", timeframe="2m")
    s("sample timeframe not str", "InvalidTypeError", "timeframe must be a str, not int", timeframe=5)
    s("sample boundary bool", "InvalidTypeError", "boundary_ms must be an int, not bool", boundary_ms=True)
    s("sample boundary str", "InvalidTypeError", "boundary_ms must be an int, not str", boundary_ms=str(Tb))
    s("sample boundary negative", "InvalidValueError", "boundary_ms must be >= 0, got -300000", boundary_ms=-300_000)
    s("sample boundary misaligned", "InvalidValueError", f"boundary_ms {Tb + 1} is not aligned to 5m", boundary_ms=Tb + 1)
    s("sample bounds non-monotonic", "NonMonotonicError", "bounds_ms[2] 100 is earlier than bounds_ms[1] 2900", bounds_ms=[700, 2900, 100, 11_000])
    s("sample bounds negative", "InvalidValueError", "bounds_ms[0] must be >= 0, got -1", bounds_ms=[-1, 2900, 10_800, 11_000])
    s("sample bounds bool", "InvalidTypeError", "bounds_ms[1] must be an int, not bool", bounds_ms=[700, True, 10_800, 11_000])
    s("sample bounds str", "InvalidTypeError", "bounds_ms[3] must be an int, not str", bounds_ms=[700, 2900, 10_800, "11000"])
    s("sample bounds nan", "InvalidTypeError", "bounds_ms[0] must be an int, not float", bounds_ms=[nan, 2900, 10_800, 11_000])
    s("sample bounds missing entry", "MissingValueError", "bounds_ms[2] is required", bounds_ms=[700, 2900, None, 11_000])
    s("sample bounds wrong length", "InvalidValueError", "observations and bounds_ms must each have 4 entries", bounds_ms=[700, 2900, 10_800])
    s("sample reference missing", "ReferenceMissingError", "reference row is missing", reference=None)
    s("sample reference 11 fields", "MalformedRowError", "reference must have exactly 12 elements, got 11", reference=ref[:11])
    s("sample reference not list", "MalformedRowError", "reference must be a list or tuple, not str", reference="x" * 12)
    s("sample reference open bool", "MalformedRowError", "reference[0] must be an int, not bool", reference=mut_row(0, True))
    s("sample reference trades bool", "MalformedRowError", "reference[8] must be an int, not bool", reference=mut_row(8, True))
    s("sample reference close time float", "MalformedRowError", "reference[6] must be an int, not float", reference=mut_row(6, float(ref[6])))
    s("sample reference price number", "MalformedRowError", "reference[1] must be a decimal string, not float", reference=mut_row(1, 100.0))
    s("sample reference price NaN", "MalformedRowError", "reference[2] is not a finite non-negative decimal string: 'NaN'", reference=mut_row(2, "NaN"))
    s("sample reference price Infinity", "MalformedRowError", "reference[3] is not a finite non-negative decimal string: 'Infinity'", reference=mut_row(3, "Infinity"))
    s("sample reference negative volume", "MalformedRowError", "reference[5] is not a finite non-negative decimal string: '-1.0'", reference=mut_row(5, "-1.0"))
    s("sample reference empty string", "MalformedRowError", "reference[7] is not a finite non-negative decimal string: ''", reference=mut_row(7, ""))
    s("sample reference underscore", "MalformedRowError", "reference[9] is not a finite non-negative decimal string: '1_0'", reference=mut_row(9, "1_0"))
    s("sample reference whitespace", "MalformedRowError", "reference[10] is not a finite non-negative decimal string: ' 5.0'", reference=mut_row(10, " 5.0"))
    s("sample reference exponent", "MalformedRowError", "reference[4] is not a finite non-negative decimal string: '1e2'", reference=mut_row(4, "1e2"))
    s("sample reference ignore not str", "MalformedRowError", "reference[11] must be a str, not int", reference=mut_row(11, 0))
    s("sample reference negative trades", "MalformedRowError", "reference[8] must be >= 0, got -1", reference=mut_row(8, -1))
    s("sample reference wrong open", "MalformedRowError", f"reference[0] open time {op + I} != expected {op}", reference=mut_row(0, op + I))
    s("sample reference wrong close", "MalformedRowError", f"reference[6] close time {op + I} != expected {op + I - 1}", reference=mut_row(6, op + I))
    s("sample observation malformed", "MalformedRowError", "observations[2] must have exactly 12 elements, got 3", observations=[ref, ref, [1, 2, 3], ref])
    s("sample observations wrong length", "InvalidValueError", "observations and bounds_ms must each have 4 entries", observations=[ref, ref, ref])

    r("analyze_samples", {"samples": None}, "MissingValueError", "samples is required", "analyze none")
    r("analyze_samples", {"samples": []}, "EmptySampleError", "no samples", "analyze empty list")
    r("analyze_samples", {"samples": []}, "EmptySampleError", "no samples", "analyze empty tuple")
    r("analyze_samples", {"samples": "abc"}, "InvalidTypeError", "samples must be a list or tuple, not str", "analyze str")
    r("analyze_samples", {"samples": {"a": 1}}, "InvalidTypeError", "samples must be a list or tuple, not dict", "analyze dict")
    r("analyze_samples", {"samples": ["x"]}, "InvalidTypeError", "samples[0] must be a SampleInput, not str", "analyze non-sample")
    r("analyze_samples", {"samples": {"$repeat_sample": MAX_SAMPLES + 1}}, "SampleCountError",
      f"{MAX_SAMPLES + 1} samples exceed the maximum of {MAX_SAMPLES}", "analyze too many samples")
    r("stable_from", {"observations": [ref] * 4, "reference": None, "indices": [1, 2, 3, 4]}, "ReferenceMissingError",
      "reference row is missing", "stable_from reference missing")
    r("stable_from", {"observations": [ref] * 3, "reference": ref, "indices": [1, 2, 3, 4]}, "InvalidValueError",
      "expected 4 observations, got 3", "stable_from wrong observation count")
    out["rejections"] = rej
    return out


if __name__ == "__main__":
    target = Path(__file__).with_name("obs_analysis_vectors.json")
    target.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {target}", file=sys.stderr)
