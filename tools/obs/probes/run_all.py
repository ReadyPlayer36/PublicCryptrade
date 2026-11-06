"""Driver for the Appendix A probe suite (V17-04; V18-02/V18-03; manifest and inventory v2.0, V19-03/V19-05; v2.2 V21-01/V21-02).

  python -m tools.obs.probes.run_all --check             # CI gate: exit 0 pass / 1 mismatch / 2 integrity or environment
  python -m tools.obs.probes.run_all --self-test         # CI gate: the integrity REFUSALS, proven by negative cases
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

A FILE IS ITS INODE, NOT ITS NAME (V21-01). Every suite file is enumerated with `lstat` semantics, must BE a regular file
(a symlink pointing inside or outside the tree, a directory, a FIFO, a socket or a device is a refusal before any
measurement), and is then opened ONCE with `O_NOFOLLOW`, `fstat`ed and compared to the `lstat` result, so a path swapped
for a link after the inventory is refused instead of hashed. The bytes that are compared are the bytes of the inode that
was checked. `--self-test` demonstrates each refusal as a negative regression case.

COUNTS ARE THREE DIFFERENT NUMBERS (V21-02). v2.1 printed "14 files pinned by expected.json", which is false:
`expected.json` pins 13 files, the suite ships 14, and `expected.json` itself is pinned by §A.0 of the document. The run
line and the report's `coverage` block name all three, so no reader has to infer which count a number is.

Instruments per phase: `tracemalloc` (Python-object attribution), the interposer's malloc counter (every malloc arena
and thread, including allocations that live and die inside the region) and, when the request region is measured, the
interposer's direct-mmap counter (anonymous private mappings, the channel a malloc-only interposer cannot see).
mallinfo2 figures are REPORTED only: they are lower bounds (A.5.3) and are never gated. The native region's inventory
(A.5.8) is gated ITEM BY ITEM against the bounds derived there, so a consumer that grows past its derivation fails the
gate instead of being absorbed by a tolerance.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile

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
# V21-01: O_NOFOLLOW turns "is this a link?" into an OPEN-TIME fact rather than a check the caller must win a race to
# use. It exists on Linux/POSIX; where it does not, the lstat/ fstat identity comparison below still refuses a link,
# because a followed link's inode cannot equal the inode lstat named.
OPEN_REGULAR = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
READ_CHUNK = 1 << 20


class SuiteIntegrityError(Exception):
    """A suite file failed its identity check: missing, not a regular file, a link, or replaced while being read."""


def describe_mode(mode: int) -> str:
    """Name a non-regular file type for a diagnostic (V21-01): 'not a regular file' alone hides what was there."""
    if stat.S_ISLNK(mode):
        return "a symbolic link"
    if stat.S_ISDIR(mode):
        return "a directory"
    if stat.S_ISFIFO(mode):
        return "a FIFO"
    if stat.S_ISSOCK(mode):
        return "a socket"
    if stat.S_ISCHR(mode):
        return "a character device"
    if stat.S_ISBLK(mode):
        return "a block device"
    return f"mode {oct(mode)}"


@contextlib.contextmanager
def opened_regular(path: str, label: str):
    """Yield `(handle, stat_result)` for a suite file that was a regular file at OPEN time, opened without links.

    V21-01: every read of a suite file goes through here. `lstat` refuses a link, directory, FIFO, socket or device
    before a byte is read; `O_NOFOLLOW` makes the same refusal race-free at open; `os.path.samestat` proves the open
    descriptor is the inode that was inspected, so a post-enumeration substitution is refused rather than hashed; and
    the caller's size check proves nothing changed while the bytes were being read.
    """
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        raise SuiteIntegrityError(f"{label}: missing on disk") from None
    except OSError as exc:
        raise SuiteIntegrityError(f"{label}: lstat failed: {exc.strerror or exc}") from None
    if not stat.S_ISREG(before.st_mode):
        raise SuiteIntegrityError(f"{label}: is {describe_mode(before.st_mode)}, not a regular file (V21-01)")
    try:
        fd = os.open(path, OPEN_REGULAR)
    except OSError as exc:
        raise SuiteIntegrityError(f"{label}: open(O_NOFOLLOW) failed: {exc.strerror or exc} (V21-01)") from None
    handle = None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SuiteIntegrityError(f"{label}: the opened descriptor is {describe_mode(opened.st_mode)}, not a "
                                      f"regular file (V21-01)")
        if not os.path.samestat(before, opened):
            raise SuiteIntegrityError(
                f"{label}: identity changed between lstat and open (device {before.st_dev}, inode {before.st_ino} -> "
                f"device {opened.st_dev}, inode {opened.st_ino}): post-enumeration substitution (V21-01)")
        handle = os.fdopen(fd, "rb", closefd=False)
        yield handle, opened
    finally:
        if handle is not None:
            handle.close()
        os.close(fd)


def read_regular(path: str, label: str) -> tuple[int, str]:
    """Return `(bytes, sha256)` for a suite file, hashed from ONE no-follow descriptor (V21-01)."""
    digest = hashlib.sha256()
    total = 0
    with opened_regular(path, label) as (handle, opened):
        for chunk in iter(lambda: handle.read(READ_CHUNK), b""):
            total += len(chunk)
            digest.update(chunk)
        if total != opened.st_size:
            raise SuiteIntegrityError(f"{label}: read {total} B from an inode of {opened.st_size} B: modified while "
                                      f"being hashed (V21-01)")
    return total, digest.hexdigest()


def suite_files(here: str = HERE) -> list[str]:
    """Every file of this suite: entries that ARE regular files, minus the build artifact and interpreter caches.

    V21-01: an inventory that resolves links cannot pin the code that runs. Anything here that is not a regular file
    — a symlink (inside or outside the tree, dangling or not), a directory that is not `__pycache__`, a FIFO, a socket,
    a device — refuses the run instead of being counted, followed or skipped.
    """
    try:
        with os.scandir(here) as entries:
            listing = sorted(entries, key=lambda entry: entry.name)
            names: list[str] = []
            for entry in listing:
                try:
                    info = entry.stat(follow_symlinks=False)          # == lstat: a link is reported as a link
                except OSError as exc:
                    raise SuiteIntegrityError(f"{entry.name}: lstat failed: {exc.strerror or exc} (V21-01)") from None
                if stat.S_ISLNK(info.st_mode):
                    try:
                        target = os.readlink(entry.path)
                    except OSError:
                        target = "?"
                    raise SuiteIntegrityError(f"{entry.name}: is a symbolic link -> {target!r}; the suite is "
                                              f"inventoried without following links (V21-01)")
                if stat.S_ISDIR(info.st_mode):
                    if entry.name not in IGNORED_DIRS:
                        raise SuiteIntegrityError(f"unexpected directory {entry.name!r} inside the suite (A.0)")
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise SuiteIntegrityError(f"{entry.name}: is {describe_mode(info.st_mode)}, not a regular file "
                                              f"(V21-01)")
                if entry.name in BUILD_ARTIFACTS:
                    continue
                names.append(entry.name)
            return names
    except FileNotFoundError:
        raise SuiteIntegrityError(f"the suite directory {here!r} does not exist (A.0)") from None
    except OSError as exc:
        raise SuiteIntegrityError(f"cannot list the suite directory {here!r}: {exc.strerror or exc} (A.0)") from None


def manifest(include_self: bool = True, here: str = HERE) -> dict:
    """The A.0 table: path, byte size and SHA-256 for every suite file (self included for the document's diff)."""
    rows = []
    for name in suite_files(here):
        if name == SELF and not include_self:
            continue
        size, digest = read_regular(os.path.join(here, name), f"{CANONICAL_PREFIX}{name}")
        rows.append({"path": f"{CANONICAL_PREFIX}{name}", "bytes": size, "sha256": digest})
    return {"algorithm": "sha256", "files": rows}


def check_manifest(expected: dict, here: str = HERE) -> list[str]:
    """V19-05/V20-14/V21-01: the manifest is the reviewed code, so it is checked as DATA before it is trusted, and a
    modification, an addition or a deletion is a refusal, never a warning.

    v2.0 matched its rows by BASENAME (`os.path.basename(row["path"])`) after indexing them into a dict, which made
    every structural question about the manifest unanswerable: two rows could share a basename with one silently
    overwriting the other, a row could name `probe3_decode.py` (or `/etc/whatever`) and still bind to the file in this
    directory, `bytes`/`sha256` of the wrong type were trusted until they were compared, and a row for `expected.json`
    itself or for the build artifact was reported as a DELETION rather than as the malformed entry it is. Each row is
    now validated on its own and a malformed entry fails closed - a refusal to run, before a single measurement.

    v2.2 adds IDENTITY (V21-01): the inventory refuses any entry that is not a regular file, and each compared file is
    read through `read_regular`, so a symlink — to a file inside the suite, to one outside it, dangling, or swapped in
    after the inventory — cannot be hashed in place of the file the manifest pinned.
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
    try:
        present = set(suite_files(here)) - {SELF}
    except SuiteIntegrityError as exc:
        # V21-01: a non-regular entry makes the whole inventory untrustworthy, so the run stops here. It is reported
        # as a refusal line, not raised, so `--check` keeps its documented exit status (2).
        return failures + [f"manifest: {exc}"]
    for name in sorted(present - set(by_name)):
        failures.append(f"manifest: {name} exists but is not in the manifest (added file)")
    for name in sorted(set(by_name) - present):
        failures.append(f"manifest: {name} is listed but missing on disk (deleted file)")
    for name in sorted(present & set(by_name)):
        row = listed[CANONICAL_PREFIX + name]
        try:
            size, digest = read_regular(os.path.join(here, name), f"{CANONICAL_PREFIX}{name}")
        except SuiteIntegrityError as exc:
            failures.append(f"manifest: {exc}")
            continue
        if size != row["bytes"]:
            failures.append(f"manifest: {name} is {size} B, manifest says {row['bytes']} B (modified)")
            continue
        if digest != row["sha256"]:
            failures.append(f"manifest: {name} sha256 {digest[:16]}… != {row['sha256'][:16]}… (modified)")
    return failures


def self_test() -> int:
    """V21-01 negative regressions: a suite entry that is a link or not a regular file must be REFUSED, not hashed.

    Every case builds a throw-away suite tree in a temporary directory, so nothing here reads or writes the real one.
    CI runs this (`--self-test`) ahead of the gate, so the refusals are demonstrated on every revision instead of being
    described in prose. The first case is a CONTROL: the same harness must ACCEPT an honest tree, or "everything is
    refused" would pass this file.
    """
    results: list[tuple[str, bool]] = []

    def report_case(label: str, ok: bool, detail: str = "", skipped: bool = False) -> None:
        results.append((label, ok))
        mark = "skip" if skipped else ("ok  " if ok else "FAIL")
        print(f"{mark}  {label}{(' — ' + detail) if detail else ''}")

    def tree(root: str) -> None:
        for name in ("probe1_phase1.py", "run_all.py"):
            with open(os.path.join(root, name), "wb") as handle:
                handle.write(f"# {name}\n".encode())

    def refuses(label: str, needle: str, mutate) -> None:
        """Record the manifest while every file is honest, apply `mutate`, then require a refusal naming `needle`."""
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp)
            block = manifest(include_self=False, here=tmp)
            mutate(tmp)
            try:
                failures = check_manifest({"manifest": block}, here=tmp)
            except SuiteIntegrityError as exc:      # refusals are RETURNED by check_manifest, never raised
                failures = [f"raised: {exc}"]
            text = " | ".join(failures)
            report_case(label, bool(failures) and needle in text, text or "no failure reported")

    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        block = manifest(include_self=False, here=tmp)
        failures = check_manifest({"manifest": block}, here=tmp)
        report_case("control: an honest tree validates", not failures, " | ".join(failures) or "no failures")

    def link_inside(tmp: str) -> None:
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.symlink(os.path.join(tmp, "run_all.py"), os.path.join(tmp, "probe1_phase1.py"))

    def link_outside(tmp: str) -> None:
        outside = os.path.join(os.path.dirname(tmp), "outside-the-suite.txt")
        with open(outside, "wb") as handle:
            handle.write(b"not a suite file\n")
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.symlink(outside, os.path.join(tmp, "probe1_phase1.py"))

    def link_added(tmp: str) -> None:
        os.symlink(os.path.join(tmp, "run_all.py"), os.path.join(tmp, "probe9_extra.py"))

    def link_dangling(tmp: str) -> None:
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.symlink(os.path.join(tmp, "no-such-file.py"), os.path.join(tmp, "probe1_phase1.py"))

    def link_device(tmp: str) -> None:
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.symlink("/dev/null", os.path.join(tmp, "probe1_phase1.py"))

    def directory(tmp: str) -> None:
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.mkdir(os.path.join(tmp, "probe1_phase1.py"))

    def fifo(tmp: str) -> None:
        os.unlink(os.path.join(tmp, "probe1_phase1.py"))
        os.mkfifo(os.path.join(tmp, "probe1_phase1.py"))

    def modified(tmp: str) -> None:
        with open(os.path.join(tmp, "probe1_phase1.py"), "ab") as handle:
            handle.write(b"# drift\n")

    refuses("post-enumeration substitution: a link to a file INSIDE the suite is refused", "symbolic link",
            link_inside)
    refuses("a link to a file OUTSIDE the suite is refused", "symbolic link", link_outside)
    refuses("a link ADDED to the suite after the inventory is refused", "symbolic link", link_added)
    refuses("a DANGLING link is refused (never reported as a deleted file)", "symbolic link", link_dangling)
    refuses("a link to a device is refused (the link is the problem, not the target)", "symbolic link", link_device)
    refuses("a DIRECTORY in place of a suite file is refused", "directory", directory)
    refuses("a FIFO in place of a suite file is refused", "FIFO", fifo)
    refuses("a MODIFIED regular file is still refused (V19-05 behaviour retained)", "modified", modified)
    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        block = manifest(include_self=False, here=tmp)
        try:
            os.unlink(os.path.join(tmp, "probe1_phase1.py"))
            os.mknod(os.path.join(tmp, "probe1_phase1.py"), stat.S_IFCHR | 0o600, os.makedev(1, 3))
        except (PermissionError, AttributeError, OSError) as exc:
            report_case("a DEVICE node in place of a suite file is refused", True,
                        f"skipped: mknod unavailable here ({exc.__class__.__name__}); the symlink-to-/dev/null case "
                        f"covers devices", skipped=True)
        else:
            failures = check_manifest({"manifest": block}, here=tmp)
            text = " | ".join(failures)
            report_case("a DEVICE node in place of a suite file is refused", bool(failures) and "device" in text,
                        text or "no failure reported")
    if os.path.exists("/dev/null"):                      # a real character device, no privileges needed
        try:
            with opened_regular("/dev/null", "/dev/null"):
                pass
        except SuiteIntegrityError as exc:
            report_case("a real character device is refused, not read as a file", "character device" in str(exc),
                        str(exc))
        else:
            report_case("a real character device is refused, not read as a file", False, "the device was accepted")
    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        os.symlink(os.path.join(tmp, "run_all.py"), os.path.join(tmp, "link.py"))
        try:
            with opened_regular(os.path.join(tmp, "link.py"), "link.py"):
                pass
        except SuiteIntegrityError as exc:
            report_case("opened_regular refuses a link when called directly", "symbolic link" in str(exc), str(exc))
        else:
            report_case("opened_regular refuses a link when called directly", False, "the link was accepted")
    if getattr(os, "O_NOFOLLOW", 0):
        with tempfile.TemporaryDirectory() as tmp:
            tree(tmp)
            os.symlink(os.path.join(tmp, "run_all.py"), os.path.join(tmp, "link.py"))
            try:
                os.open(os.path.join(tmp, "link.py"), OPEN_REGULAR)
            except OSError as exc:
                report_case("open(..., O_NOFOLLOW) refuses a link at open time (ELOOP): the race-free half of V21-01",
                            exc.errno == errno.ELOOP,
                            f"{exc.__class__.__name__}: {exc.strerror} (errno {exc.errno})")
            else:
                report_case("open(..., O_NOFOLLOW) refuses a link at open time (ELOOP)", False,
                            "open SUCCEEDED on a symbolic link")
    else:
        report_case("open(..., O_NOFOLLOW) refuses a link at open time (ELOOP)", True,
                    "skipped: O_NOFOLLOW is unavailable on this platform (lstat + fstat identity still applies)",
                    skipped=True)
    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        path = os.path.join(tmp, "run_all.py")
        size, digest = read_regular(path, "run_all.py")
        with open(path, "rb") as handle:
            want = hashlib.sha256(handle.read()).hexdigest()
        report_case("a regular file still hashes to its own bytes", (size, digest) == (os.path.getsize(path), want),
                    f"{size} B, {digest[:16]}…")
    failed = [label for label, ok in results if not ok]
    print(f"{'PASS' if not failed else 'FAIL'}: {len(results) - len(failed)}/{len(results)} integrity regression cases")
    return 0 if not failed else 1


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


def coverage(block: dict, expected: dict) -> dict:
    """V21-02: the three counts v2.1 collapsed into one. They are not interchangeable.

    * `inventoried` — every file the suite ships (A.0's rows, `expected.json` included);
    * `pinned_by_expected_json` — the rows of its `manifest` block (`expected.json` cannot hash itself);
    * `self` — `expected.json`, pinned by §A.0 of the document instead, which is why A.0 is generated and reviewed.
    """
    rows = {row["path"]: row for row in block["files"]}
    self_path = f"{CANONICAL_PREFIX}{SELF}"
    return {
        "inventoried": len(block["files"]),
        "pinned_by_expected_json": len((expected.get("manifest") or {}).get("files") or []),
        "self_path": self_path,
        "self_sha256": (rows.get(self_path) or {}).get("sha256"),
        "self_pinned_by": "Appendix A.0 of docs/obs-session-runner-design.md (expected.json cannot contain its own "
                          "digest)",
        "build_artifacts_excluded": sorted(BUILD_ARTIFACTS),
        "directories_skipped": sorted(IGNORED_DIRS),
    }


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode == "--self-test":
        # The negative regressions of the integrity checks; they build their own trees and need neither the manifest
        # nor the pinned interpreter, so they run first in CI and fail closed on their own.
        return self_test()
    if mode == "--manifest":
        try:
            block = manifest(include_self=True)
        except SuiteIntegrityError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(block, indent=2, sort_keys=True))
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
    try:
        with opened_regular(expected_path, SELF) as (handle, _info):
            expected = json.load(handle)
    except SuiteIntegrityError as exc:
        print(f"refused: {exc} (A.0)", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"refused: {SELF} is not readable JSON: {exc}", file=sys.stderr)
        return 2
    if expected.get("schema") != SCHEMA:
        print(f"refused: {SELF} schema {expected.get('schema')!r} != {SCHEMA!r} (run_all version skew)", file=sys.stderr)
        return 2
    if mode == "--update-manifest":
        # The repair mode cannot require a valid manifest: it is what repairs it. Everything else refuses first.
        try:
            expected["manifest"] = manifest(include_self=False)
        except SuiteIntegrityError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        with open(expected_path, "w") as handle:
            json.dump(expected, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"manifest updated: {len(expected['manifest']['files'])} files pinned "
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
    try:
        block = manifest(include_self=True)
    except SuiteIntegrityError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    counts = coverage(block, expected)
    report = {
        "schema": SCHEMA,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "manifest": block,
        "coverage": counts,
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
    # V21-02: three counts, named. "14 files pinned by expected.json" (v2.1) was false on two of them.
    print(f"PASS: {len(measured)} measurements; {counts['inventoried']} suite files inventoried, "
          f"{counts['pinned_by_expected_json']} pinned by expected.json, {SELF} pinned by Appendix A.0")
    print(f"      {SELF} sha256 {counts['self_sha256']} (compare with A.0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
