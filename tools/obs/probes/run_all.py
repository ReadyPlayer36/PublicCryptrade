"""Driver for the Appendix A probe suite (V17-04; V18-02/V18-03).

  python -m tools.obs.probes.run_all --check      # CI gate: exit 0 pass / 1 mismatch / 2 environment refused
  python -m tools.obs.probes.run_all --record     # print a new expected.json body for a REVIEWED revision
  python -m tools.obs.probes.run_all --manifest   # print {path: sha256} for every file of this suite (A.0)
  python -m tools.obs.probes.run_all --interpose <probe>   # internal: one phase under alloc_peak.so (A.7.9)

Instruments per phase: `tracemalloc` (Python-object attribution), the interposer's malloc counter (every malloc arena
and thread, including allocations that live and die inside the region) and, when the request region is measured, the
interposer's direct-mmap counter (anonymous private mappings, the channel a malloc-only interposer cannot see).
mallinfo2 figures are REPORTED only: they are lower bounds (A.5.3) and are never gated. Arena-scale mmap reservations
are reported and fenced, not added to a tracemalloc figure (A.5.7 states why they are not the same quantity).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys

from tools.obs.probes import probe_common as C

PROBES = ("probe1_phase1", "probe2_seal", "probe3_decode", "probe4_decode_fresh", "probe5_byte_equality",
          "probe6_native", "probe7_structure")
BY_MEASUREMENT = {"phase1_request": "probe1_phase1", "phase2_seal": "probe2_seal", "phase3_decode": "probe3_decode"}
PINNED_PYTHON = "3.12.3"          # A.1: another interpreter invalidates every recorded value
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHIM = os.path.join(HERE, "alloc_peak.so")
SUITE = ("__init__.py", "alloc_peak.c", "expected.json", "probe_common.py", "probe1_phase1.py", "probe2_seal.py",
         "probe3_decode.py", "probe4_decode_fresh.py", "probe5_byte_equality.py", "probe6_native.py",
         "probe7_structure.py", "README.md", "run_all.py")


def collect() -> list[dict]:
    results: list[dict] = []
    for name in PROBES:
        produced = importlib.import_module(f"tools.obs.probes.{name}").main()
        results.extend(produced if isinstance(produced, list) else [produced])
    return results


def interposed(measurement: str) -> dict[str, int] | None:
    """Re-run one phase in a child with alloc_peak.so preloaded; None when the shim cannot be used."""
    module = BY_MEASUREMENT.get(measurement)
    if module is None or not os.path.exists(SHIM):
        return None
    done = subprocess.run([sys.executable, "-m", "tools.obs.probes.run_all", "--interpose", module],
                          env=dict(os.environ, LD_PRELOAD=SHIM, PYTHONPATH=ROOT),
                          capture_output=True, timeout=300, cwd=ROOT)
    if done.returncode != 0:
        return None
    data = json.loads(done.stdout.decode() or "{}")
    return {"peak": int(data["peak"]), "map_peak": int(data.get("map_peak", 0))}


def manifest() -> dict[str, str]:
    """sha256 of every suite file: the A.0 table a reviewer (and CI) can diff against the repository."""
    out = {}
    for name in SUITE:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            out[name] = "MISSING"
            continue
        out[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return out


def compare(expected: dict, measured: list[dict], probe_interposed) -> list[str]:
    failures: list[str] = []
    by_name = {m["probe"]: m for m in measured}
    for want in expected["measurements"]:
        name = want["probe"]
        got = by_name.get(name)
        if got is None:
            failures.append(f"{name}: not measured")
            continue
        tolerance = want.get("tolerance", 0.02)
        if want.get("expected_fail"):
            if got.get("pass") is not False:
                failures.append(f"{name}: banned pattern PASSED its bound (it must fail)")
        elif got.get("pass") is False:
            failures.append(f"{name}: peak {got['peak']} exceeds its bound {got['bound']}")
        if want.get("peak") and name != "native_headroom":
            if abs(got["peak"] - want["peak"]) > want["peak"] * tolerance:
                failures.append(f"{name}: peak {got['peak']} != recorded {want['peak']} (tolerance {tolerance:.0%})")
        if want.get("interposed") is not None and name != "native_headroom":
            instrument = probe_interposed(name)
            if instrument is None:
                failures.append(f"{name}: interposer unavailable — build alloc_peak.so (A.7.9)")
                continue
            peak = instrument["peak"]
            if want.get("bound") is not None and peak > want["bound"]:
                failures.append(f"{name}: interposed peak {peak} exceeds the bound {want['bound']}")
            elif abs(peak - want["interposed"]) > want["interposed"] * tolerance:
                failures.append(f"{name}: interposed {peak} != recorded {want['interposed']}")
            # the direct-mmap channel is bounded by the headroom constant for phases too (A.5.7): arena reservations
            # are not live Domain B bytes, so no sum is taken, but a measurement-region mapping larger than the
            # constant would mean the malloc figure is under-reporting and must be reviewed before it is trusted.
            if want.get("interposed_map_peak") is not None and instrument["map_peak"] > C.HTTP_HEADROOM:
                failures.append(f"{name}: direct-mmap channel {instrument['map_peak']} > HTTP_HEADROOM "
                                f"{C.HTTP_HEADROOM} (A.5.7: the malloc figure is no longer a usable bound)")
        if name == "native_headroom":
            detail = got.get("detail") or {}
            instrument = detail.get("interposed") or {}
            peak, map_peak = instrument.get("peak"), instrument.get("map_peak")
            if peak is None or map_peak is None:
                failures.append("native_headroom: interposer unavailable (the analytic term cannot be checked)")
                continue
            if peak > C.HTTP_HEADROOM:
                failures.append(f"native_headroom: request-region malloc peak {peak} > HTTP_HEADROOM {C.HTTP_HEADROOM}")
            # V18-03 fence: the direct-mmap channel is added to the malloc channel, so the SUM must fit the constant.
            if peak + map_peak > C.HTTP_HEADROOM:
                failures.append(f"native_headroom: malloc {peak} + direct mmap {map_peak} > "
                                f"HTTP_HEADROOM {C.HTTP_HEADROOM} (A.5.7 fence)")
            # the mallinfo2 figure is a LOWER BOUND and is deliberately NOT compared to a recorded value
    return failures


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode == "--manifest":
        print(json.dumps(manifest(), indent=2, sort_keys=True))
        return 0
    if mode == "--interpose":
        module = importlib.import_module(f"tools.obs.probes.{argv[2]}")
        if hasattr(module, "interposed_pair"):
            pair = module.interposed_pair()
        else:
            pair = {"peak": int(module.interposed()), "map_peak": 0}
        print(json.dumps({"peak": int(pair["peak"]), "map_peak": int(pair.get("map_peak", 0))}))
        return 0
    if sys.version.split()[0] != PINNED_PYTHON:
        print(f"refused: interpreter {sys.version.split()[0]} != {PINNED_PYTHON} (A.1)", file=sys.stderr)
        return 2
    missing = [name for name in SUITE if not os.path.exists(os.path.join(HERE, name))]
    if missing:
        print(f"refused: suite is incomplete, missing {missing} (A.0)", file=sys.stderr)
        return 2
    measured = collect()
    if mode == "--record":
        print(json.dumps({"env": {"python": sys.version.split()[0], "platform": platform.platform()},
                          "measurements": measured}, indent=2))
        return 0
    expected = json.load(open(os.path.join(HERE, "expected.json")))
    failures = compare(expected, measured, interposed)
    for line in failures:
        print(line, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
