"""Driver for the Appendix A probe suite (V17-04; V18-02/V18-03; manifest and inventory v2.0, V19-03/V19-05).

  python -m tools.obs.probes.run_all --check             # CI gate: exit 0 pass / 1 mismatch / 2 integrity or environment
  python -m tools.obs.probes.run_all --record            # print a new measurements array for a REVIEWED revision
  python -m tools.obs.probes.run_all --manifest          # print path/bytes/sha256 for EVERY suite file (A.0)
  python -m tools.obs.probes.run_all --update-manifest   # rewrite expected.json's manifest block (reviewed only)
  python -m tools.obs.probes.run_all --report PATH       # write a machine-readable run report (CI artifact)
  python -m tools.obs.probes.run_all --interpose <probe> # internal: one phase under alloc_peak.so (A.7.9)

THE MANIFEST IS ENFORCED (V19-05). `expected.json` carries a `manifest` block with the byte size and SHA-256 of every
other file in this directory. `--check` verifies it BEFORE it measures anything and refuses to run (exit 2) when a file
is modified, added or deleted, so the code that produces a number is the code that was reviewed. `expected.json` cannot
contain its own digest; A.0 in the document pins it instead (the document is anchored in git), and `--manifest` prints
its digest too so a reviewer can check the whole chain.

Instruments per phase: `tracemalloc` (Python-object attribution), the interposer's malloc counter (every malloc arena
and thread, including allocations that live and die inside the region) and, when the request region is measured, the
interposer's direct-mmap counter (anonymous private mappings, the channel a malloc-only interposer cannot see).
mallinfo2 figures are REPORTED only: they are lower bounds (A.5.3) and are never gated. The native region's inventory
(A.5.8) is gated ITEM BY ITEM against the bounds derived there, so a consumer that grows past its derivation fails the
gate instead of being absorbed by a tolerance.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import re
import subprocess
import sys

from tools.obs.probes import probe_common as C

PROBES = ("probe1_phase1", "probe2_seal", "probe3_decode", "probe4_decode_fresh", "probe5_byte_equality",
          "probe6_native", "probe7_structure", "probe8_mmap_threads")
BY_MEASUREMENT = {"phase1_request": "probe1_phase1", "phase2_seal": "probe2_seal", "phase3_decode": "probe3_decode"}
PINNED_PYTHON = "3.12.3"          # A.1: another interpreter invalidates every recorded value
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHIM = os.path.join(HERE, "alloc_peak.so")
SELF = "expected.json"
BUILD_ARTIFACTS = {"alloc_peak.so"}
IGNORED_DIRS = {"__pycache__"}
SCHEMA = "obs-probes/2"
CANONICAL_PREFIX = "tools/obs/probes/"     # A.0 paths are repository-relative and complete (V20-14)
ROW_FIELDS = {"path", "bytes", "sha256"}
BLOCK_FIELDS = {"algorithm", "files"}
SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def suite_files() -> list[str]:
    """Every tracked file of this suite: the directory listing minus the build artifact and interpreter caches."""
    names = []
    for entry in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, entry)
        if os.path.isdir(path):
            if entry not in IGNORED_DIRS:
                raise SystemExit(f"refused: unexpected directory {entry!r} inside the suite (A.0)")
            continue
        if entry in BUILD_ARTIFACTS:
            continue
        names.append(entry)
    return names


def manifest(include_self: bool = True) -> dict:
    """The A.0 table: path, byte size and SHA-256 for every suite file (self included for the document's diff)."""
    rows = []
    for name in suite_files():
        if name == SELF and not include_self:
            continue
        path = os.path.join(HERE, name)
        rows.append({"path": f"tools/obs/probes/{name}", "bytes": os.path.getsize(path), "sha256": sha256(path)})
    return {"algorithm": "sha256", "files": rows}


def check_manifest(expected: dict) -> list[str]:
    """V19-05/V20-14: the manifest is the reviewed code, so it is checked as DATA before it is trusted, and a
    modification, an addition or a deletion is a refusal, never a warning.

    v2.0 matched its rows by BASENAME (`os.path.basename(row["path"])`) after indexing them into a dict, which made
    every structural question about the manifest unanswerable: two rows could share a basename with one silently
    overwriting the other, a row could name `probe3_decode.py` (or `/etc/whatever`) and still bind to the file in this
    directory, `bytes`/`sha256` of the wrong type were trusted until they were compared, and a row for `expected.json`
    itself or for the build artifact was reported as a DELETION rather than as the malformed entry it is. Each row is
    now validated on its own and a malformed entry fails closed - a refusal to run, before a single measurement.
    """
    failures: list[str] = []
    declared = expected.get("manifest")
    if not isinstance(declared, dict):
        return ["manifest: expected.json has no manifest object (V19-05)"]
    unknown_block = sorted(set(declared) - BLOCK_FIELDS)
    if unknown_block:
        failures.append(f"manifest: unknown field(s) {unknown_block} in the manifest block (V20-14)")
    if declared.get("algorithm") != "sha256":
        failures.append(f"manifest: algorithm {declared.get('algorithm')!r} != 'sha256' (V20-14)")
    rows = declared.get("files")
    if not isinstance(rows, list) or not rows:
        return failures + ["manifest: 'files' must be a non-empty list (V19-05)"]
    listed: dict[str, dict] = {}              # canonical path -> validated row
    by_name: dict[str, str] = {}              # basename -> canonical path already seen
    for index, row in enumerate(rows):
        where = f"manifest: files[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{where}: entry is {type(row).__name__}, not an object (V20-14)")
            continue
        unknown = sorted(set(row) - ROW_FIELDS)
        if unknown:
            failures.append(f"{where}: unknown field(s) {unknown} (V20-14)")
        path, size, digest = row.get("path"), row.get("bytes"), row.get("sha256")
        valid = True
        if not isinstance(path, str) or not path:
            failures.append(f"{where}: 'path' must be a non-empty string (V20-14)")
            valid = False
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            failures.append(f"{where} {path!r}: 'bytes' must be a non-negative integer (V20-14)")
            valid = False
        if not isinstance(digest, str) or SHA256_HEX.fullmatch(digest) is None:
            failures.append(f"{where} {path!r}: 'sha256' must be 64 lowercase hex characters (V20-14)")
            valid = False
        if not valid:
            continue
        name = os.path.basename(path)
        if path != CANONICAL_PREFIX + name:
            failures.append(f"{where}: {path!r} is not the canonical path {CANONICAL_PREFIX + name!r} (V20-14)")
            continue                          # a non-canonical path never resolves to a file here
        if name.startswith(".") or name in (".", ".."):
            failures.append(f"{where}: {path!r} is not a suite file name (V20-14)")
            continue
        if name == SELF:
            failures.append(f"{where}: {SELF} cannot pin itself; A.0 pins it against the document (V20-14)")
            continue
        if name in BUILD_ARTIFACTS:
            failures.append(f"{where}: {name} is a build artifact and is never pinned (G-V18-02 d, V20-14)")
            continue
        if path in listed:
            failures.append(f"{where}: duplicate path {path} (V20-14)")
            continue
        if name in by_name:
            failures.append(f"{where}: {path} repeats the basename of {by_name[name]} (V20-14)")
            continue
        by_name[name] = path
        listed[path] = row
    present = set(suite_files()) - {SELF}
    for name in sorted(present - set(by_name)):
        failures.append(f"manifest: {name} exists but is not in the manifest (added file)")
    for name in sorted(set(by_name) - present):
        failures.append(f"manifest: {name} is listed but missing on disk (deleted file)")
    for name in sorted(present & set(by_name)):
        row = listed[CANONICAL_PREFIX + name]
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            failures.append(f"manifest: {name} is not a regular file (V20-14)")
            continue
        size = os.path.getsize(path)
        if size != row["bytes"]:
            failures.append(f"manifest: {name} is {size} B, manifest says {row['bytes']} B (modified)")
            continue
        digest = sha256(path)
        if digest != row["sha256"]:
            failures.append(f"manifest: {name} sha256 {digest[:16]}… != {row['sha256'][:16]}… (modified)")
    return failures


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


def compare_inventory(expected: dict, detail: dict) -> list[str]:
    """A.5.8: every inventory item must sit inside the bound DERIVED for it, and the request region must fit A.5.5."""
    failures: list[str] = []
    spec = expected.get("inventory") or {}
    rows = detail.get("inventory") or {}
    for stage in spec.get("stages") or ():
        if stage not in rows:
            failures.append(f"inventory: stage {stage!r} was not measured (A.5.8)")
    for item in spec.get("items") or ():
        name = item["name"]
        try:
            value = int(rows[item["from"]]["peak"]) - int(rows[item["minus"]]["peak"]) if item.get("minus") \
                else int(rows[item["from"]]["peak"])
        except (KeyError, TypeError, ValueError):
            failures.append(f"inventory: {name}: stage data missing")
            continue
        bound = int(item["bound"])
        floor = -int(item.get("tolerance", 0))
        if value < floor:
            failures.append(f"inventory: {name}: {value} B is below the {floor} B floor (a later stage cannot "
                            f"measure less than glibc block reuse explains)")
        elif value > bound:
            failures.append(f"inventory: {name}: {value} B exceeds its derived bound {bound} B ({item['derivation']})")
    per_request = int(spec.get("per_request_bound") or 0)
    if per_request > C.HTTP_HEADROOM:
        failures.append(f"inventory: the per-request item bounds sum to {per_request} B > HTTP_HEADROOM {C.HTTP_HEADROOM}")
    return failures


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
            if name == "realloc_accounting":
                detail = got.get("detail") or {}
                failed = sorted(key for key, held in (detail.get("checks") or {}).items() if not held) or ["child"]
                failures.append(f"{name}: the realloc-failure regression did not hold: {failed} (peak {got['peak']} B, "
                                f"two-block floor {detail.get('two_block_floor')} B; A.5.4/V20-11)")
            else:
                failures.append(f"{name}: peak {got['peak']} exceeds its bound {got['bound']}")
        if want.get("peak") and name not in ("native_headroom", "mmap_accounting"):
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
            failures.extend(compare_inventory(expected, detail))
            # the mallinfo2 figure is a LOWER BOUND and is deliberately NOT compared to a recorded value
        if name == "realloc_accounting":
            detail = got.get("detail") or {}
            checks = detail.get("checks") or {}
            if not checks:
                failures.append("realloc_accounting: the regression reported no clause results (A.5.4/V20-11)")
            for clause in sorted(checks):
                if checks[clause] is not True:
                    failures.append(f"realloc_accounting: clause {clause!r} did not hold (A.5.4/V20-11)")
            if int(got.get("peak") or 0) < int(detail.get("two_block_floor") or 1):
                failures.append(f"realloc_accounting: peak {got.get('peak')} B does not cover both 4 MiB blocks "
                                f"(floor {detail.get('two_block_floor')} B): a failed realloc erased a live block")
        if name == "mmap_accounting":
            detail = got.get("detail") or {}
            concurrency = detail.get("concurrency") or {}
            partial = detail.get("partial_mremap") or {}
            failure = detail.get("fail_closed") or {}
            if got.get("pass") is not True:
                failures.append("mmap_accounting: the range/concurrency properties did not hold (A.5.9)")
            if partial.get("ok") is not True:
                failures.append(f"mmap_accounting: partial unmap / mremap accounting wrong: {partial}")
            if concurrency.get("ok") is not True:
                failures.append(f"mmap_accounting: concurrency accounting wrong: {concurrency}")
            if int(concurrency.get("end_live") or 0) != 0 or int(concurrency.get("end_regions") or 0) != 0:
                failures.append("mmap_accounting: the range table did not return to its baseline (leaked entries)")
            if int(concurrency.get("peak") or 0) < int(concurrency.get("expected_floor") or 1):
                failures.append("mmap_accounting: peak below the simultaneous-mapping floor (a lost update)")
            if failure.get("ok") is not True:
                failures.append(f"mmap_accounting: capacity exhaustion did not fail closed: {failure}")
    return failures


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode == "--manifest":
        print(json.dumps(manifest(include_self=True), indent=2, sort_keys=True))
        return 0
    if mode == "--interpose":
        module = importlib.import_module(f"tools.obs.probes.{argv[2]}")
        if hasattr(module, "interposed_pair"):
            pair = module.interposed_pair()
        else:
            pair = {"peak": int(module.interposed()), "map_peak": 0}
        print(json.dumps({"peak": int(pair["peak"]), "map_peak": int(pair.get("map_peak", 0))}))
        return 0
    expected_path = os.path.join(HERE, SELF)
    if not os.path.exists(expected_path):
        print(f"refused: {SELF} is missing (A.0)", file=sys.stderr)
        return 2
    with open(expected_path) as handle:
        expected = json.load(handle)
    if expected.get("schema") != SCHEMA:
        print(f"refused: {SELF} schema {expected.get('schema')!r} != {SCHEMA!r} (run_all version skew)", file=sys.stderr)
        return 2
    if mode == "--update-manifest":
        # The repair mode cannot require a valid manifest: it is what repairs it. Everything else refuses first.
        expected["manifest"] = manifest(include_self=False)
        with open(expected_path, "w") as handle:
            json.dump(expected, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"manifest updated: {len(expected['manifest']['files'])} files "
              f"(expected.json excluded: it cannot hash itself; A.0 pins it instead)")
        return 0
    integrity = check_manifest(expected)
    if integrity:
        for line in integrity:
            print(line, file=sys.stderr)
        print("refused: the suite does not match expected.json; run --update-manifest only in a REVIEWED revision",
              file=sys.stderr)
        return 2
    if sys.version.split()[0] != PINNED_PYTHON:
        print(f"refused: interpreter {sys.version.split()[0]} != {PINNED_PYTHON} (A.1)", file=sys.stderr)
        return 2
    measured = collect()
    if mode == "--record":
        print(json.dumps({"env": {"python": sys.version.split()[0], "platform": platform.platform()},
                          "measurements": measured}, indent=2))
        return 0
    failures = compare(expected, measured, interposed)
    report = {
        "schema": SCHEMA,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "manifest": manifest(include_self=True),
        "measurements": measured,
        "failures": failures,
    }
    if "--report" in argv:
        path = argv[argv.index("--report") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"report written to {path}")
    for line in failures:
        print(line, file=sys.stderr)
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed", file=sys.stderr)
        return 1
    print(f"PASS: {len(measured)} measurements, {len(report['manifest']['files'])} files pinned by expected.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
