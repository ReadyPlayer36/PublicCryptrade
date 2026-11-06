"""Probe 8 - the mmap channel under concurrency, partial unmapping and mremap (V19-01/V19-02).

v1.9's shim tracked mappings in a bare array with no lock and subtracted a bare length, so it could not answer the
question this probe asks: is the second channel still exact when several threads map and unmap at once, when an unmap
covers only PART of a mapping, and when `mremap` moves or grows one?  Four properties, each measured here rather than
argued:

  A. PARTIAL UNMAP is range-aware: a hole punched in the middle of a mapping subtracts only the hole, splits the
     tracked range in two, and the remaining pieces keep their exact byte count.
  B. MREMAP is accounted as remove(old) + add(new): a grow from 8 KiB to 32 KiB raises live by exactly 32 KiB (not by
     40 KiB, and not by 24 KiB), and the following unmap returns the total to the baseline.
  C. CONCURRENCY does not lose updates: THREADS threads map 1 MiB each and meet at a barrier, so their mappings are
     live at the same instant; the recorded peak must be at least the sum (a lost update makes it smaller) and the
     phase must END at exactly the baseline, with the range table back to its starting size (an entry leaked per
     iteration would grow the table, and the shim aborts rather than drop one).
  D. CAPACITY EXHAUSTION fails closed, and is proven to happen WHERE INTENDED. The interpreter itself maps anonymous
     memory before any probe code runs (its arenas are part of the tracked table), so a fixed `ALLOC_PEAK_MAP_SLOTS=1`
     aborts during startup - the v2.0 form of this check passed for exactly that reason, having never reached its own
     mapping. This probe therefore measures the child's own baseline first, sets the capacity relative to it
     (PRESSURE_SLOTS, comfortably above startup), and requires all four of:
       D1. the child prints a flushed MAPPED line before dying, so the abort is known to have happened AFTER the
           explicit test mapping - and that line must report tracked == capacity and live == baseline + the bytes the
           child itself mapped;
       D2. the child fills the table EXACTLY (capacity - baseline regions successful mappings, no more, no fewer);
       D3. the child dies with SIGABRT, not an exit code, and its stderr carries the exact diagnostic string with the
           exact tracked/capacity/live numbers the same child just printed - one line, byte for byte, not a substring;
       D4. a NEGATIVE CONTROL - the identical program, identical preload, capacity left at the compiled default and only
           a handful of explicit mappings - completes, prints SURVIVED, exits 0, and emits no diagnostic. Without it,
           an abort caused by anything else (a bad argument, a preload failure) would look like a pass.

     Mapping addresses are MAP_FIXED_NOREPLACE and 1 GiB apart so no two explicit mappings can coalesce, which would
     otherwise make the table fill later than capacity predicts.

The probe runs its measurements in a child process with `alloc_peak.so` preloaded. Exits 0 when every property holds.
"""
from __future__ import annotations

import ctypes
import itertools
import json
import os
import re
import signal
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHIM = os.path.join(HERE, "alloc_peak.so")

PROT_READ_WRITE = 0x1 | 0x2
MAP_PRIVATE_ANON = 0x02 | 0x20
MAP_FIXED_NOREPLACE = 0x10 | 0x100000
MREMAP_MAYMOVE = 1

# Every mapping this probe makes is placed explicitly and 1 GiB from its neighbour. A kernel-chosen address can land
# flush against an existing tracked range; the shim coalesces adjacent ranges (correctly, to keep the table bounded), and
# the region-count assertions of property A would then depend on where the kernel happened to put the mapping. Fixed,
# isolated addresses remove that degree of freedom, so "+1 range per mapping, +2 after a hole" is a property of the
# bookkeeping rather than of the address layout.
ISOLATION_BASE = 0x300000000000
ISOLATION_STRIDE = 0x40000000
THREADS = 8
ITERATIONS = 64
THREAD_MAPPING = 1024 * 1024

PAGE = 4096
ISOLATION_SLOT = itertools.count()   # process-wide: unique isolated address per explicit mapping

CONTROL_MAPPINGS = 4          # negative control: a handful of explicit mappings, capacity left at its default
PRESSURE_SLOTS = 64           # abort run: capacity well above the interpreter's own startup table
FILL_MAPPINGS = 4096          # "map until the table refuses" - the loop never reaches this number
DIAGNOSTIC_PREFIX = "alloc_peak: FATAL:"

STAGE = re.compile(r"^(BASELINE|MAPPED|SURVIVED) live=(\d+) regions=(\d+)$")
CAPACITY = re.compile(r"^CAPACITY (\d+)$")

# The probed program. Its stdout is the evidence: every line is flushed BEFORE the next mapping is attempted, so a
# MAPPED line on stdout proves the interposer recorded that mapping while the process was still alive.
CHILD_PROGRAM = """\
import ctypes, sys

lib = ctypes.CDLL(None)
mmap = lib.mmap
mmap.restype = ctypes.c_void_p
mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
for name in ("alloc_peak_map_live", "alloc_peak_map_regions", "alloc_peak_map_capacity"):
    getattr(lib, name).restype = ctypes.c_size_t

PAGE = 4096
STRIDE = 0x40000000                     # 1 GiB apart: two explicit mappings can never be coalesced into one range
BASE_ADDRESS = 0x200000000000
MAP_FIXED_NOREPLACE = 0x10 | 0x100000


def state(label):
    print("%s live=%d regions=%d" % (label, lib.alloc_peak_map_live(), lib.alloc_peak_map_regions()), flush=True)


state("BASELINE")
print("CAPACITY %d" % lib.alloc_peak_map_capacity(), flush=True)

for index in range(int(sys.argv[1])):
    address = BASE_ADDRESS + index * STRIDE
    p = mmap(ctypes.c_void_p(address), PAGE, 3, 0x02 | 0x20 | MAP_FIXED_NOREPLACE, -1, 0)
    if p in (None, ctypes.c_void_p(-1).value):
        raise SystemExit("MAP_FIXED_NOREPLACE rejected at %#x" % address)
    state("MAPPED")

state("SURVIVED")
"""


def api():
    """ctypes bindings for the shim's getters and the libc mapping calls (which the shim interposes)."""
    lib = ctypes.CDLL(None)
    for name in ("alloc_peak_reset", "alloc_peak_peak", "alloc_peak_map_peak", "alloc_peak_map_live",
                 "alloc_peak_map_regions", "alloc_peak_map_capacity"):
        getattr(lib, name).restype = ctypes.c_size_t
    lib.mmap.restype = ctypes.c_void_p
    lib.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
    lib.munmap.restype = ctypes.c_int
    lib.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.mremap.restype = ctypes.c_void_p
    lib.mremap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int, ctypes.c_void_p]
    lib.alloc_peak_map_live.restype = ctypes.c_size_t
    return lib


def mapped(lib, size: int) -> int:
    """Map `size` bytes at an isolated address: address `SLOT.next()` × 1 GiB from its neighbours, so no two explicit
    mappings can ever be coalesced into one tracked range (the shim would coalesce adjacent ones, correctly)."""
    address = ISOLATION_BASE + next(ISOLATION_SLOT) * ISOLATION_STRIDE
    p = lib.mmap(ctypes.c_void_p(address), size, PROT_READ_WRITE, MAP_PRIVATE_ANON | MAP_FIXED_NOREPLACE, -1, 0)
    if p in (None, ctypes.c_void_p(-1).value):
        raise SystemExit(f"mmap at {address:#x} ({size} B) failed: the isolated slot is occupied")
    if int(p) != address:
        raise SystemExit(f"mmap at {address:#x} returned {int(p):#x}: MAP_FIXED_NOREPLACE not honoured")
    return address


def unmap(lib, address: int, size: int) -> None:
    if lib.munmap(ctypes.c_void_p(address), size) != 0:
        raise SystemExit(f"munmap({address:#x}, {size}) failed")


def partial_and_mremap(lib) -> dict[str, int | bool]:
    """Properties A and B, single-threaded, so every byte is attributable."""
    lib.alloc_peak_reset()
    base_live, base_regions = int(lib.alloc_peak_map_live()), int(lib.alloc_peak_map_regions())

    first = mapped(lib, 3 * PAGE)
    after_map = int(lib.alloc_peak_map_live()) - base_live
    unmap(lib, first + PAGE, PAGE)                       # hole in the middle: 8 KiB left, two ranges
    after_hole = int(lib.alloc_peak_map_live()) - base_live
    hole_regions = int(lib.alloc_peak_map_regions()) - base_regions
    unmap(lib, first, PAGE)
    unmap(lib, first + 2 * PAGE, PAGE)
    after_free = int(lib.alloc_peak_map_live()) - base_live

    second = mapped(lib, 2 * PAGE)
    after_second = int(lib.alloc_peak_map_live()) - base_live
    moved = lib.mremap(ctypes.c_void_p(second), 2 * PAGE, 8 * PAGE, MREMAP_MAYMOVE, None)
    if moved in (None, ctypes.c_void_p(-1).value):
        raise SystemExit("mremap failed")
    after_mremap = int(lib.alloc_peak_map_live()) - base_live
    unmap(lib, int(moved), 8 * PAGE)
    after_remap_free = int(lib.alloc_peak_map_live()) - base_live
    peak = int(lib.alloc_peak_map_peak())

    return {
        "map": after_map, "hole": after_hole, "hole_regions": hole_regions, "freed": after_free,
        "remap_before": after_second, "remap_after": after_mremap, "remap_freed": after_remap_free, "peak": peak,
        "ok": (after_map == 3 * PAGE and after_hole == 2 * PAGE and hole_regions == 2 and after_free == 0
               and after_second == 2 * PAGE and after_mremap == 8 * PAGE and after_remap_free == 0
               and peak == 8 * PAGE),
    }


def churn(lib, barrier: threading.Barrier | None = None, hold: int = 0) -> None:
    """One thread's workload: map, map, partial unmap, mremap, then unmap everything."""
    first = mapped(lib, 16 * PAGE)
    second = mapped(lib, 4 * PAGE)
    if barrier is not None:
        barrier.wait(timeout=30)
        if hold:
            threading.Event().wait(hold)
    unmap(lib, first + 8 * PAGE, 8 * PAGE)               # PARTIAL: keep the lower half
    moved = lib.mremap(ctypes.c_void_p(second), 4 * PAGE, 12 * PAGE, MREMAP_MAYMOVE, None)
    if moved in (None, ctypes.c_void_p(-1).value):
        raise SystemExit("mremap failed in churn")
    unmap(lib, first, 8 * PAGE)
    unmap(lib, int(moved), 12 * PAGE)


def concurrency(lib) -> dict[str, int | bool]:
    """Property C: simultaneous mappings are all counted, and nothing is left behind."""
    barrier = threading.Barrier(THREADS)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            mapped_share = mapped(lib, THREAD_MAPPING)
            barrier.wait(timeout=60)                      # every thread's 1 MiB is live at this instant
            unmap(lib, mapped_share, THREAD_MAPPING)
            for _ in range(ITERATIONS):
                churn(lib)
        except BaseException as exc:                      # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(THREADS)]
    churn(lib)                                            # warm-up: settles the interpreter's own arenas
    lib.alloc_peak_reset()
    base_live, base_regions = int(lib.alloc_peak_map_live()), int(lib.alloc_peak_map_regions())
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)
    if errors:
        raise SystemExit(f"worker failed: {errors[0]!r}")
    peak = int(lib.alloc_peak_map_peak())
    end_live = int(lib.alloc_peak_map_live()) - base_live
    end_regions = int(lib.alloc_peak_map_regions()) - base_regions
    expected = THREADS * THREAD_MAPPING
    return {
        "threads": THREADS, "iterations": ITERATIONS, "expected_floor": expected, "peak": peak,
        "end_live": end_live, "end_regions": end_regions,
        # no lost update: the peak saw all THREADS mappings at once. The ceiling admits the interpreter's own
        # arena growth during the phase (a few pages per thread), which is not one of our mappings.
        "ok": peak >= expected and peak <= expected + THREADS * 64 * PAGE and end_live == 0 and end_regions == 0,
    }


def _run_stages(slots: int | None, mappings: int) -> dict[str, object]:
    """Run the probed program once and return what it printed: its own baseline, its mappings, and how it died."""
    env = {key: value for key, value in os.environ.items() if key != "ALLOC_PEAK_MAP_SLOTS"}
    env.update(LD_PRELOAD=SHIM, PYTHONPATH=ROOT)
    if slots is not None:
        env["ALLOC_PEAK_MAP_SLOTS"] = str(slots)
    done = subprocess.run([sys.executable, "-c", CHILD_PROGRAM, str(mappings)],
                          env=env, capture_output=True, timeout=180, cwd=ROOT)
    stdout = done.stdout.decode("utf-8", "replace")
    stderr = done.stderr.decode("utf-8", "replace")
    stages = [(match.group(1), int(match.group(2)), int(match.group(3)))
              for line in stdout.splitlines() if (match := STAGE.match(line))]
    capacity = next((int(match.group(1)) for line in stdout.splitlines()
                     if (match := CAPACITY.match(line))), None)
    return {
        "returncode": done.returncode,
        "baseline": next(((live, regions) for label, live, regions in stages if label == "BASELINE"), None),
        "capacity": capacity,
        "mapped": [(live, regions) for label, live, regions in stages if label == "MAPPED"],
        "survived": any(label == "SURVIVED" for label, _, _ in stages),
        "fatal": [line for line in stderr.splitlines() if line.startswith(DIAGNOSTIC_PREFIX)],
        "stderr_tail": stderr[-400:],
    }


def fail_closed() -> dict[str, object]:
    """Property D: the table cannot grow past its capacity, so the shim must abort - where the test intends, with the
    exact diagnostic, and not at all when the capacity is not exceeded."""
    control = _run_stages(None, CONTROL_MAPPINGS)
    control_baseline = control["baseline"] or (0, 0)
    control_ok = (
        control["returncode"] == 0
        and control["baseline"] is not None and control["capacity"] is not None
        and control["mapped"] == [(control_baseline[0] + PAGE * (step + 1), control_baseline[1] + (step + 1))
                                 for step in range(CONTROL_MAPPINGS)]
        and control["survived"] and not control["fatal"]
    )

    pressure = _run_stages(PRESSURE_SLOTS, FILL_MAPPINGS)
    base_live, base_regions = pressure["baseline"] or (0, 0)
    capacity = int(pressure["capacity"] or 0)
    slots_left = capacity - base_regions
    last = pressure["mapped"][-1] if pressure["mapped"] else None
    aborted = pressure["returncode"] < 0 and -pressure["returncode"] == signal.SIGABRT
    expected_diagnostic = (
        f"{DIAGNOSTIC_PREFIX} range table capacity exhausted "
        f"(tracked {capacity}, capacity {capacity}, live {base_live + PAGE * slots_left}): "
        f"refusing to under-report")
    reached_mapping = (slots_left >= 1 and len(pressure["mapped"]) == slots_left
                       and last == (base_live + PAGE * slots_left, capacity))
    return {
        "control": {
            "mappings": CONTROL_MAPPINGS, "baseline": {"live": control_baseline[0], "regions": control_baseline[1]},
            "capacity": control["capacity"], "filled": len(control["mapped"]), "survived": control["survived"],
            "returncode": control["returncode"], "fatal": control["fatal"],
            "stderr_tail": control["stderr_tail"], "ok": control_ok,
        },
        "pressure": {
            "baseline": {"live": base_live, "regions": base_regions}, "capacity": capacity, "filled": len(pressure["mapped"]),
            "last": {"live": last[0], "regions": last[1]} if last else None,
            "aborted_by_sigabrt": aborted, "returncode": pressure["returncode"], "reached_mapping": reached_mapping,
            "diagnostic": pressure["fatal"][0] if pressure["fatal"] else None,
            "diagnostic_expected": expected_diagnostic,
            "diagnostic_exact": pressure["fatal"] == [expected_diagnostic],
            "survived": pressure["survived"], "stderr_tail": pressure["stderr_tail"],
        },
        "ok": bool(control_ok and aborted and reached_mapping and pressure["fatal"] == [expected_diagnostic]
                   and not pressure["survived"]),
    }


def child() -> int:
    lib = api()
    result = {
        "partial_mremap": partial_and_mremap(lib),
        "concurrency": concurrency(lib),
        "fail_closed": fail_closed(),
        "capacity": int(lib.alloc_peak_map_capacity()),
    }
    result["ok"] = all(result[key]["ok"] for key in ("partial_mremap", "concurrency", "fail_closed"))
    print(json.dumps(result, sort_keys=True))
    return 0


def main() -> list[dict]:
    """Run the child under the interposer and turn its report into one gated measurement."""
    if not os.path.exists(SHIM):
        raise SystemExit("probe8: alloc_peak.so is missing; build it first (A.7.9)")
    env = dict(os.environ, LD_PRELOAD=SHIM, PYTHONPATH=ROOT)
    done = subprocess.run([sys.executable, "-m", "tools.obs.probes.probe8_mmap_threads", "--child"],
                          env=env, capture_output=True, timeout=600, cwd=ROOT)
    if done.returncode != 0:
        raise SystemExit(f"probe8: child failed ({done.returncode}): {done.stderr.decode()[-600:]}")
    data = json.loads(done.stdout.decode())
    concurrency = data["concurrency"]
    return [{
        "probe": "mmap_accounting",
        "peak": int(concurrency["peak"]),
        "bound": None,
        "pass": bool(data["ok"]),
        "detail": {
            "instrument": "alloc_peak.so direct-mmap channel, concurrency + range bookkeeping (A.5.9)",
            "partial_mremap": data["partial_mremap"],
            "concurrency": concurrency,
            "fail_closed": data["fail_closed"],
            "capacity": data["capacity"],
        },
    }]


if __name__ == "__main__":
    if "--child" in sys.argv[1:]:
        raise SystemExit(child())
    print(json.dumps(main()))
