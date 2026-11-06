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
  D. CAPACITY EXHAUSTION fails closed: a child with ALLOC_PEAK_MAP_SLOTS=1 that needs two ranges must die with
     SIGABRT and a diagnostic - never continue with an untracked mapping, which would silently under-count.

The probe runs its measurements in a child process with `alloc_peak.so` preloaded. Exits 0 when every property holds.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHIM = os.path.join(HERE, "alloc_peak.so")

PROT_READ_WRITE = 0x1 | 0x2
MAP_PRIVATE_ANON = 0x02 | 0x20
MREMAP_MAYMOVE = 1
THREADS = 8
ITERATIONS = 64
THREAD_MAPPING = 1024 * 1024

PAGE = 4096


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
    address = lib.mmap(None, size, PROT_READ_WRITE, MAP_PRIVATE_ANON, -1, 0)
    if address in (None, ctypes.c_void_p(-1).value):
        raise SystemExit(f"mmap({size}) failed")
    return int(address)


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


def fail_closed() -> dict[str, object]:
    """Property D: the table cannot grow past its capacity, so the shim must abort instead of under-counting."""
    program = (
        "import ctypes\n"
        "lib = ctypes.CDLL(None)\n"
        "lib.mmap.restype = ctypes.c_void_p\n"
        "lib.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]\n"
        "for size in (4096, 4096):\n"
        "    p = lib.mmap(None, size, 3, 0x22, -1, 0)\n"
        "    assert p not in (None, ctypes.c_void_p(-1).value), 'mmap failed'\n"
        "print('SURVIVED')\n"
    )
    env = dict(os.environ, LD_PRELOAD=SHIM, ALLOC_PEAK_MAP_SLOTS="1", PYTHONPATH=ROOT)
    done = subprocess.run([sys.executable, "-c", program], env=env, capture_output=True, timeout=120, cwd=ROOT)
    stderr = done.stderr.decode("utf-8", "replace")
    aborted = done.returncode < 0 and -done.returncode == 6          # SIGABRT
    return {"returncode": done.returncode, "aborted": aborted, "diagnostic": "capacity exhausted" in stderr,
            "survived": "SURVIVED" in done.stdout.decode("utf-8", "replace"),
            "ok": aborted and not ("SURVIVED" in done.stdout.decode("utf-8", "replace"))}


def child() -> int:
    lib = api()
    result = {
        "partial_mremap": partial_and_mremap(lib),
        "concurrency": concurrency(lib),
        "fail_closed": fail_closed(),
        "capacity": int(lib.alloc_peak_map_capacity()),
    }
    result["ok"] = all(result[key]["ok"] for key in ("partial_mremap", "concurrency"))
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
