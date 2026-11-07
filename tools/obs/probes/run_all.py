"""Driver for the Appendix A probe suite (V17-04; V18-02/V18-03; manifest and inventory v2.0, V19-03/V19-05; v2.2 V21-01/V21-02; v2.3 V22-01/V22-02/V22-03; v2.4 V23-01; v2.5 V24-01; v2.6 V25-01; v2.7 V26-01).

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

THE CODE THAT RUNS IS THE BYTES THAT WERE HASHED (V22-01). The check above is worthless if the module that produces a
number is imported from the PATH afterwards: an import re-opens the file (or a `.pyc` built from another version of it),
so the digest a reviewer verified would describe bytes other than the ones that ran. Nothing the driver executes is
imported by path. `--check` reads each suite file ONCE through `opened_regular`, hashes that buffer against
`expected.json`, and KEEPS it; the probe modules, `probe_common` and the package itself are then built from those buffers
— `compile(data, path, "exec")` into a fresh `types.ModuleType` registered in `sys.modules` — and executed, after every
manifest check has passed and never before. A file that fails the check contributes no executable source at all, a tree
that passes cannot execute a byte that was not hashed, and no `.pyc` is consulted for any module the driver runs. The
interposed child (`--interpose`, one phase under `alloc_peak.so`) verifies and binds the tree by the same route before it
measures.

WHAT THAT BINDING DOES NOT COVER, STATED RATHER THAN IMPLIED (V22-01, revised by V23-01). One path stays outside it and
is not hidden: the DRIVER ITSELF. `python -m tools.obs.probes.run_all` is imported by the interpreter before any of this
code can run, so `run_all.py` is the trust root and cannot verify the import that created it; A.0 pins it, `--manifest`
prints the digest a reviewer compares, and every measurement is produced by a module that WAS checked. v2.3 also left
the CHILD interpreters outside (they were launched with `-m` on the checked tree but executed from disk); v2.4 closed the
child's PAYLOAD and v2.5 its interpreter STARTUP, and the two paragraphs that follow say how. Nothing else is outside:
no import, no child and no startup hook contributes a byte to a measurement.

A CHILD IS STARTED FROM THE SAME BYTES (V23-01). v2.3 spawned probe6's server, stage and realloc children and probe8's
mmap child with `python -m tools.obs.probes.<probe>`, so the child's interpreter opened the module FILE — after the
parent's manifest check, in a process that never read the manifest. A tree substituted in that window ran unverified
code inside a gated measurement. Every child is now started from the parent's retained buffers, through
`probe_common.spawn_suite_child` / `run_suite_child` / `run_program` (which live in probe_common.py, itself a pinned
file): the source travels over a pipe, one frame per module with the SHA-256 `expected.json` PROMISES for that file,
and the child recomputes it and refuses to execute anything that does not match. The child's bootstrap is bound the
same way — the parent passes the digest of the bootstrap text and the child hashes the `-c` argument it was actually
started with (`sys.orig_argv`) — and the child's `tools.obs.probes` package is CLOSED (`__path__ = []`), so a module the
parent did not send cannot be imported from disk there. Dependencies are not assumed: the closure is read with `ast`
from the verified sources, so `probe_common` (and anything else a probe imports) is in the payload ahead of the probe.
WHAT IS PRESERVED, because it decides the numbers: the child is still a fresh interpreter, and the shim still counts it
from exec, so Python startup remains inside the native peak exactly as in v2.3 and earlier; the same `cwd`, the same
`sys.argv[0]` (`-m` gives the module path, and the parent passes that path), the same resets inside the measured
regions, and the module is still executed as `__main__`. probe8's inline capacity program, previously a `-c` argument
with no binding, travels the same pipe. Every gate (`--check`, `--record`, `--interpose`) starts its children this way,
so there is no mode left that falls back to `-m`; a probe executed on its own has no registered suite and refuses to
start an unverified child instead of doing it silently (see probes/README.md).

THE CHILD'S INTERPRETER STARTUP IS ISOLATED TOO (V24-01). v2.4 bound the payload but launched the child as
`python -c <bootstrap>`: with no `-I` and no `-S`, interpreter STARTUP was outside every check — `site` imports the
working directory's `sitecustomize`, `PYTHONPATH` entries are searched, and for `-c` the working directory is
`sys.path[0]`, so a planted `sitecustomize.py` or a shadowing `hashlib.py` (the module the payload verification itself
calls) could run BEFORE the bootstrap's first line. Every child is now `python -I -S -c <bootstrap>`: `-I` removes the
`PYTHON*` environment, the user site directory and the working directory from `sys.path`, and `-S` skips `site`
entirely, so neither `sitecustomize` nor `usercustomize` is imported and no working-directory module can resolve ahead
of the standard library. The bootstrap enforces the same thing from inside rather than trusting its launcher:
`isolated()` runs before it reads the parent's request and refuses (exit 86) unless `sys.flags.isolated`, `no_site`,
`ignore_environment` and `no_user_site` are all set, no startup hook is in `sys.modules` and no `sys.path` entry is the
working directory — so an edit that drops a flag fails closed instead of silently re-opening the hole. `--self-test`
proves it with a child whose working directory holds a hostile `sitecustomize.py`, `hashlib.py` and `ssl.py`: none of
them runs, `hashlib` still resolves to the real standard library, and a child started without the flags is refused.

THE BOOTSTRAP CHECKS THE INTERPRETER BEFORE IT IMPORTS ANYTHING (V25-01). v2.5 launched the child correctly, but the
bootstrap's first line imported `builtins`, `hashlib`, `json`, `os`, `sys` and `types`, so `isolated()` ran AFTER the
imports it exists to protect: with `-I` dropped, a working-directory `hashlib.py` executes during `import hashlib`,
ahead of the first check. The prelude now imports `sys` alone — built in, never searched for on `sys.path` — refuses
from `sys.stderr` with `SystemExit(86)` (no `os._exit()`, since `os` must not be imported in order to refuse), CALLS
`isolated()` as its first executable statement, and only then imports `builtins`/`hashlib`/`json`/`os`/`types`.
`isolated()` is import-free: it uses `sys.flags` and the form of each `sys.path` entry instead of `os.getcwd()`, and
`cwd_free()` re-confirms the path claim after the imports as defence in depth. `--self-test` parses the bootstrap it is
about to run and fails unless `isolated()` is executed before the first file-backed import with only `sys` ahead of it,
and it launches the child with `-I` REMOVED in a working directory whose `hashlib.py` records itself and raises: the
child must exit 86 with the plant never executing, and a CONTROL shows the same plant DOES run once `-I` is removed, so
that refusal cannot pass vacuously.

THE FLAGS ARE A STATIC LAUNCHER INVARIANT, NOT A RUNTIME CHECK (V26-01). v2.6 also ran a child with `-S` removed in a
working directory holding `sitecustomize.py` and reported that no hook executed — which proved less than it appeared to.
`-I` keeps the working directory off `sys.path` even when `-S` is gone, so that child could never have imported the
planted hook: the case exercised `-I`, not the absence of `site`. And CPython runs `site` during interpreter STARTUP,
before a byte of the `-c` bootstrap is compiled, so a SYSTEM site hook cannot be prevented by any script — `isolated()`
can only observe `sys.flags.no_site` afterwards and refuse to measure. v2.7 states that boundary instead of implying it
is covered. `-I`/`-S` are static launcher invariants: the immutable `CHILD_FLAGS` tuple is the only place they are
spelled, `child_command()` derives the command from it and nothing else, and .github/workflows/ci.yml mutates each flag,
the launcher's return value and the guard call, failing the build if `--self-test` survives any of them. `--self-test`
now proves the invariant statically (tuple type, immutability, no flag literal outside the tuple, the CI step's own
text), keeps the V25-01 ordering proof, and launches a `-S`-less child only to show the post-hoc DETECTION fires — it no
longer plants a working-directory `sitecustomize.py` and pretends that tests system site initialization.

COUNTS ARE THREE DIFFERENT NUMBERS (V21-02). v2.1 printed "14 files pinned by expected.json", which is false:
`expected.json` pins 13 files, the suite ships 14, and `expected.json` itself is pinned by §A.0 of the document. The run
line and the report's `coverage` block name all three, so no reader has to infer which count a number is.

A SKIP IS NOT A PASS (V22-03). The self-test reports passed, failed and skipped SEPARATELY: a case this host could not
run (no `CAP_MKNOD`, no `O_NOFOLLOW`) is printed as `skip` and never contributes to the passed count. The exit status
depends only on failures, so an environment that skips a case cannot manufacture a green run without saying so.

Instruments per phase: `tracemalloc` (Python-object attribution), the interposer's malloc counter (every malloc arena
and thread, including allocations that live and die inside the region) and, when the request region is measured, the
interposer's direct-mmap counter (anonymous private mappings, the channel a malloc-only interposer cannot see).
mallinfo2 figures are REPORTED only: they are lower bounds (A.5.3) and are never gated. The native region's inventory
(A.5.8) is gated ITEM BY ITEM against the bounds derived there, so a consumer that grows past its derivation fails the
gate instead of being absorbed by a tolerance.
"""
from __future__ import annotations

import ast
import contextlib
import errno
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import types

PROBES = ("probe1_phase1", "probe2_seal", "probe3_decode", "probe4_decode_fresh", "probe5_byte_equality",
          "probe6_native", "probe7_structure", "probe8_mmap_threads")
BY_MEASUREMENT = {"phase1_request": "probe1_phase1", "phase2_seal": "probe2_seal", "phase3_decode": "probe3_decode"}
PACKAGE = "tools.obs.probes"
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
# V22-01: the order the suite executes in. `__init__.py` first (it is the package the others are registered under),
# then `probe_common`, then the probes in the order they are measured, so a probe that imports a function from another
# probe (probe4 <- probe3) finds it already defined.
LOAD_ORDER = ("__init__.py", "probe_common.py") + tuple(f"{name}.py" for name in PROBES)
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


def read_regular(path: str, label: str) -> tuple[bytes, int, str]:
    """Return `(data, bytes, sha256)` for a suite file, read and hashed through ONE no-follow descriptor (V21-01).

    V22-01: the buffer is returned, not just its digest. It is the only copy of the source this process will ever have:
    the module is compiled from it after the manifest check, so the bytes executed are the bytes hashed, and a rewrite
    of the path between the two cannot take effect.
    """
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    with opened_regular(path, label) as (handle, opened):
        for chunk in iter(lambda: handle.read(READ_CHUNK), b""):
            total += len(chunk)
            digest.update(chunk)
            chunks.append(chunk)
        if total != opened.st_size:
            raise SuiteIntegrityError(f"{label}: read {total} B from an inode of {opened.st_size} B: modified while "
                                      f"being hashed (V21-01)")
    return b"".join(chunks), total, digest.hexdigest()


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
        _data, size, digest = read_regular(os.path.join(here, name), f"{CANONICAL_PREFIX}{name}")
        rows.append({"path": f"{CANONICAL_PREFIX}{name}", "bytes": size, "sha256": digest})
    return {"algorithm": "sha256", "files": rows}


def check_manifest(expected: dict, here: str = HERE, keep: dict[str, bytes] | None = None) -> list[str]:
    """V19-05/V20-14/V21-01/V22-01: the manifest is the reviewed code, so it is checked as DATA before it is trusted,
    and a modification, an addition or a deletion is a refusal, never a warning.

    v2.0 matched its rows by BASENAME (`os.path.basename(row["path"])`) after indexing them into a dict, which made
    every structural question about the manifest unanswerable: two rows could share a basename with one silently
    overwriting the other, a row could name `probe3_decode.py` (or `/etc/whatever`) and still bind to the file in this
    directory, `bytes`/`sha256` of the wrong type were trusted until they were compared, and a row for `expected.json`
    itself or for the build artifact was reported as a DELETION rather than as the malformed entry it is. Each row is
    now validated on its own and a malformed entry fails closed - a refusal to run, before a single measurement.

    v2.2 adds IDENTITY (V21-01): the inventory refuses any entry that is not a regular file, and each compared file is
    read through `read_regular`, so a symlink — to a file inside the suite, to one outside it, dangling, or swapped in
    after the inventory — cannot be hashed in place of the file the manifest pinned.

    v2.3 adds BINDING (V22-01): with `keep` supplied, the exact buffer that was hashed for a file that MATCHED its row is
    stored in it. `load_verified_modules` executes those buffers and nothing else, so a file that fails here contributes
    no source to be run, and a file that passes cannot be re-read afterwards.
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
            data, size, digest = read_regular(os.path.join(here, name), f"{CANONICAL_PREFIX}{name}")
        except SuiteIntegrityError as exc:
            failures.append(f"manifest: {exc}")
            continue
        if size != row["bytes"]:
            failures.append(f"manifest: {name} is {size} B, manifest says {row['bytes']} B (modified)")
            continue
        if digest != row["sha256"]:
            failures.append(f"manifest: {name} sha256 {digest[:16]}… != {row['sha256'][:16]}… (modified)")
            continue
        if keep is not None:
            keep[name] = data                 # V22-01: the ONLY source that may be executed
    return failures


def _execute_module(qualified: str, path: str, data: bytes, parent: types.ModuleType | None = None,
                    is_package: bool = False) -> types.ModuleType:
    """Build a module from `data` and execute it, with no path, no loader and no `.pyc` in the picture (V22-01).

    `compile()` runs on the bytes that `check_manifest` hashed; the module object is created here, registered in
    `sys.modules` before execution (so a module that imports itself, or a `from ... import name` inside it, sees this
    object and not a fresh file read), and its parent package gets the attribute, because the import system only sets
    that attribute when IT loads a submodule. If execution raises, the half-built module is removed again.
    """
    code = compile(data, path, "exec", dont_inherit=True)
    spec = importlib.machinery.ModuleSpec(qualified, loader=None, origin=path, is_package=is_package)
    if is_package:
        spec.submodule_search_locations = [os.path.dirname(path)]
    module = importlib.util.module_from_spec(spec)
    module.__file__ = path
    sys.modules[qualified] = module
    short = qualified.rpartition(".")[2]
    if parent is not None:
        setattr(parent, short, module)
    try:
        exec(code, module.__dict__)           # noqa: S102 — executing verified source is the point of this function
    except BaseException:
        sys.modules.pop(qualified, None)
        if parent is not None:
            with contextlib.suppress(AttributeError):
                delattr(parent, short)
        raise
    return module


def load_verified_modules(sources: dict[str, bytes], here: str = HERE) -> dict[str, types.ModuleType]:
    """Execute the suite FROM the bytes that matched `expected.json`, in dependency order (V22-01).

    `sources` is filled by `check_manifest(keep=...)` and holds a file name only if that file's size and SHA-256 matched
    its row. A name that is missing here is a refusal, not a reason to read the path: falling back to the filesystem is
    exactly the defect this function exists to remove. `tools.obs.probes` itself is rebuilt from its verified
    `__init__.py` (the interpreter imported the real package to start this module, which is why the package is replaced
    rather than trusted), `probe_common` is executed next, and each probe follows in measurement order.
    """
    missing = [name for name in LOAD_ORDER if name not in sources]
    if missing:
        raise SuiteIntegrityError(f"no VERIFIED bytes for {', '.join(missing)}: a module is never re-read from disk "
                                  f"after the manifest check (V22-01)")
    package = _execute_module(PACKAGE, os.path.join(here, "__init__.py"), sources["__init__.py"],
                             parent=sys.modules.get("tools.obs"), is_package=True)
    modules: dict[str, types.ModuleType] = {"__init__": package}
    for name in ("probe_common",) + PROBES:
        modules[name] = _execute_module(f"{PACKAGE}.{name}", os.path.join(here, f"{name}.py"), sources[f"{name}.py"],
                                        parent=package)
    return modules


def self_test() -> int:
    """Negative regressions for the integrity checks, with passed / failed / skipped counted separately (V22-03).

    Every case builds a throw-away suite tree in a temporary directory, so nothing here reads or writes the real one.
    CI runs this (`--self-test`) ahead of the gate, so the refusals are demonstrated on every revision instead of being
    described in prose. The first case is a CONTROL: the same harness must ACCEPT an honest tree, or "everything is
    refused" would pass this file. A case this host cannot run is printed as `skip` and counted as skipped, never as
    passed (V22-03): the summary says how many of each, and only failures affect the exit status.

    V23-01's cases (added in v2.4) start REAL children through the transport that probe_common.py ships — executed here
    from its verified bytes, exactly as the driver executes it — and prove the three properties a `-m` spawn never had:
    a frame that does not match the promised digest is refused instead of executed, a child runs the bytes it was sent
    even when the path it was told about now holds different source, and the child's bootstrap cannot be swapped.

    V24-01's cases (added in v2.5) start a child in a working directory that holds a hostile `sitecustomize.py` and
    shadow `hashlib.py` / `ssl.py` modules, and prove the interpreter is isolated and site-free before any child code
    runs: the hook never executes, the shadow modules never win, `hashlib` is still the real standard-library module,
    and a child launched WITHOUT `-I -S` is refused by the bootstrap rather than measured.

    V25-01's cases (added in v2.6) check the ORDER v2.5 left implicit. The bootstrap text is PARSED and `isolated()` must
    be executed before the first file-backed import, with `sys` the only module imported ahead of it — a comment cannot
    satisfy that and a reordering cannot pass it. The launcher's `CHILD_FLAGS` must be exactly `('-I', '-S')` and
    `child_command()` exactly `[sys.executable, '-I', '-S', '-c', BOOTSTRAP]`, so neither flag can be dropped silently.
    `-I` is then removed in a hostile working directory (where a planted `hashlib.py` would win): the child must be
    REFUSED with nothing planted executing, and a CONTROL runs the same plant with no isolation at all to show it is live.

    V26-01's cases (added in v2.7) test what can honestly be verified and stop testing what cannot. `-I`/`-S` are STATIC
    launcher invariants: CPython runs `site` during startup, before any `-c` code is compiled, so a child script cannot
    prevent a system site hook — it can only DETECT the missing flag afterwards and refuse the measurement. The cases
    therefore require `CHILD_FLAGS` to be an immutable tuple of exactly the two flags and `child_command()` to derive the
    command from it with no flag literal of its own, prove that a `-S`-less child in an EMPTY directory is detected and
    refused (with nothing to plant, so the case cannot be read as prevention), and parse .github/workflows/ci.yml and
    require the mutation step that fails the build when either flag, the launcher's return value or the guard call is
    tampered with. The v2.6 case that planted `sitecustomize.py` in the child's working directory with `-S` removed is
    GONE: `-I` still kept that directory off `sys.path`, so it exercised `-I`, never system site initialization, and
    passing it proved nothing about the case V26-01 raised.
    """
    counts = {"passed": 0, "failed": 0, "skipped": 0}

    def report_case(label: str, ok: bool, detail: str = "", skipped: bool = False) -> None:
        if skipped:
            counts["skipped"] += 1
            mark = "skip"
        elif ok:
            counts["passed"] += 1
            mark = "ok  "
        else:
            counts["failed"] += 1
            mark = "FAIL"
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

    @contextlib.contextmanager
    def swapped_before_open(path: str, payload: bytes):
        """Arm a one-shot `os.open` hook that REPLACES `path` with a NEW INODE immediately before it is opened.

        V22-02: this is the race `samestat` exists for, injected deterministically rather than argued about. The hook
        fires on the next `open(O_RDONLY|O_NOFOLLOW)` of exactly this path, writes a different file beside it and
        `os.replace`s it into place — so `lstat` has already named inode A and the `open` that follows resolves inode B.
        The hook is disarmed after one shot and `os.open` is always restored.
        """
        real_open = os.open
        state = {"armed": True}

        def hooked(target, flags, *args, **kwargs):
            if (state["armed"] and flags == OPEN_REGULAR
                    and os.path.abspath(target) == os.path.abspath(path)):
                state["armed"] = False
                staging = path + ".race"
                fd = real_open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                try:
                    os.write(fd, payload)
                finally:
                    os.close(fd)
                os.replace(staging, path)         # a DIFFERENT inode is what the following open() will see
            return real_open(target, flags, *args, **kwargs)

        os.open = hooked
        try:
            yield state
        finally:
            os.open = real_open

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

    # V22-02: the ACTIVE race. lstat() names one inode, a new file is renamed over the path, open() gets the other.
    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        path = os.path.join(tmp, "probe1_phase1.py")
        before = os.lstat(path)
        with swapped_before_open(path, b"# substituted between lstat and open\n" * 3) as state:
            try:
                with opened_regular(path, "probe1_phase1.py"):
                    pass
            except SuiteIntegrityError as exc:
                message = str(exc)
                after = os.lstat(path)
                moved = (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                report_case("TOCTOU: an inode swapped between lstat() and open() is CAUGHT by samestat (V22-02)",
                            "identity changed between lstat and open" in message and moved and not state["armed"],
                            f"{message} [inode {before.st_ino} -> {after.st_ino}]")
            else:
                report_case("TOCTOU: an inode swapped between lstat() and open() is CAUGHT by samestat (V22-02)", False,
                            "opened_regular ACCEPTED the substituted inode")
        if state["armed"]:
            report_case("TOCTOU: the fault-injection hook actually fired (V22-02)", False,
                        "the hook never matched the open, so the case above proved nothing")

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

    # V22-01: the executed source is the buffer that was hashed, even when the path says something else entirely.
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "probe_common.py")
        with open(path, "wb") as handle:
            handle.write(b"# module under test\nVALUE = 'verified bytes'\n")
        try:
            data, size, digest = read_regular(path, "probe_common.py")
        except SuiteIntegrityError as exc:
            report_case("a module executes the HASHED bytes, not the file that replaced them (V22-01)", False, str(exc))
        else:
            with open(path, "wb") as handle:           # what a rewrite between check and import would leave behind
                handle.write(b"# module under test\nVALUE = 'rewritten after the hash'\n")
            module = _execute_module("obs_verified_demo", path, data)
            value = getattr(module, "VALUE", None)
            sys.modules.pop("obs_verified_demo", None)
            report_case("a module executes the HASHED bytes, not the file that replaced them (V22-01)",
                        value == "verified bytes",
                        f"executed VALUE={value!r} from the {size} B buffer hashed as {digest[:16]}…")
    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        block = manifest(include_self=False, here=tmp)
        sources: dict[str, bytes] = {}
        check_manifest({"manifest": block}, here=tmp, keep=sources)
        try:
            load_verified_modules(sources, here=tmp)
        except SuiteIntegrityError as exc:
            report_case("a probe with no VERIFIED bytes is refused, never fetched from the path (V22-01)",
                        "no VERIFIED bytes" in str(exc), str(exc))
        else:
            report_case("a probe with no VERIFIED bytes is refused, never fetched from the path (V22-01)", False,
                        "load_verified_modules executed a module whose bytes were never verified")
    driver = os.path.join(HERE, "run_all.py")
    try:
        with open(driver, "rb") as handle:
            text = handle.read()
    except OSError as exc:
        report_case("the driver contains no path-based import of a suite module (V22-01)", False,
                    f"cannot read {driver}: {exc}")
    else:
        # assembled at run time so this case's own text cannot satisfy it
        needle = b"import" + b"_module("
        report_case("the driver contains no path-based import of a suite module (V22-01)", needle not in text,
                    "no path-based import found" if needle not in text else "a path-based import is still present")
    # V23-01: the child transport, executed from probe_common.py's own bytes (the code that will run in the child, not a
    # copy written for the test). The cases below start REAL child processes; each is a negative or a positive control.
    transport = None
    common_path = os.path.join(HERE, "probe_common.py")
    try:
        common_data, _, _ = read_regular(common_path, "probe_common.py")
        transport = _execute_module("obs_selftest_common", common_path, common_data)
    except (SuiteIntegrityError, SyntaxError) as exc:
        report_case("the child transport loads from probe_common.py's verified bytes (V23-01)", False, str(exc))
    else:
        sys.modules.pop("obs_selftest_common", None)
    if transport is not None:
        # V25-01: the guard must come FIRST, and it must be in the SOURCE the child runs. Parsed, not pattern-matched:
        # a reordering fails, and a comment mentioning the ordering cannot satisfy it.
        try:
            parsed = ast.parse(transport.BOOTSTRAP, "<bootstrap>")
        except SyntaxError as exc:
            report_case("the bootstrap validates the interpreter BEFORE importing hashlib/json/os/types (V25-01)",
                        False, f"the bootstrap does not parse: {exc}")
        else:
            guard_at: int | None = None
            first_backed: int | None = None
            prelude: list[str] = []
            for node in parsed.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) \
                        and getattr(node.value.func, "id", None) == "isolated":
                    guard_at = node.lineno
                    continue
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                if guard_at is None:
                    prelude.extend(names)
                if first_backed is None and set(names) & {"builtins", "hashlib", "json", "os", "types"}:
                    first_backed = node.lineno
            ordered = guard_at is not None and first_backed is not None and guard_at < first_backed \
                and set(prelude) <= {"sys"}
            report_case("the bootstrap validates the interpreter BEFORE importing hashlib/json/os/types (V25-01)",
                        ordered,
                        f"isolated() at line {guard_at}, first file-backed import at line {first_backed}, "
                        f"imported ahead of the guard: {sorted(set(prelude)) or ['none']}")
        report_case("the child launcher carries BOTH -I and -S, in that order (V25-01)",
                    tuple(transport.CHILD_FLAGS) == ("-I", "-S")
                    and transport.child_command() == [sys.executable, "-I", "-S", "-c", transport.BOOTSTRAP],
                    f"CHILD_FLAGS={tuple(transport.CHILD_FLAGS)!r}, command opens {transport.child_command()[:3]!r}")

        # V26-01: the flags are a STATIC invariant, so prove the shape a mutation would have to break. `CHILD_FLAGS` must
        # be an immutable tuple and `child_command()` must derive the command from it with no flag literal of its own —
        # a second place the flags are spelled is a second place that can drift.
        launcher_uses_tuple = False
        launcher_literals: list = []
        try:
            for node in ast.walk(ast.parse(common_data.decode("utf-8"), "<probe_common.py>")):
                if isinstance(node, ast.FunctionDef) and node.name == "child_command":
                    launcher_uses_tuple = "CHILD_FLAGS" in ast.dump(node)
                    launcher_literals = [n.value for n in ast.walk(node)
                                         if isinstance(n, ast.Constant) and n.value in ("-I", "-S")]
        except (UnicodeDecodeError, SyntaxError):
            launcher_uses_tuple = False
        try:
            transport.CHILD_FLAGS[0] = "-S"   # type: ignore[index]  # the mutation this case exists to rule out
            immutable = False
        except TypeError:
            immutable = True
        report_case("CHILD_FLAGS is an immutable tuple and the only place the flags are spelled (V26-01)",
                    isinstance(transport.CHILD_FLAGS, tuple) and tuple(transport.CHILD_FLAGS) == ("-I", "-S")
                    and immutable and launcher_uses_tuple and not launcher_literals
                    and transport.child_command()[1:3] == ["-I", "-S"],
                    f"{type(transport.CHILD_FLAGS).__name__} {tuple(transport.CHILD_FLAGS)!r}, item assignment "
                    f"{'refused' if immutable else 'ACCEPTED'}, launcher literals {launcher_literals or 'none'}")

        # V26-01: the enforcement that closes the gap a runtime check cannot. CI mutates the flags, the launcher and the
        # guard call and REQUIRES `--self-test` to fail, so the workflow text is part of the claim and is checked here.
        ci_path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
        try:
            with open(ci_path, "r", encoding="utf-8") as handle:
                ci_text = handle.read()
        except OSError as exc:
            report_case("CI fails closed when a flag, the launcher or the guard call is tampered with (V26-01)", False,
                        f"no CI workflow beside this suite ({exc.__class__.__name__}) to inspect", skipped=True)
        else:
            required = {
                "a mutation step": "Mutation:",
                "-I removed": """mutate 'CHILD_FLAGS = ("-I", "-S")' 'CHILD_FLAGS = ("-I",)' no-I""",
                "-S removed": """mutate 'CHILD_FLAGS = ("-I", "-S")' 'CHILD_FLAGS = ("-S",)' no-S""",
                "launcher narrowed": "no-command-S",
                "guard call removed": "no-guard",
                "a survivor fails the job": "MUTATION SURVIVED",
                "it runs the self-test": "--self-test",
            }
            missing = [name for name, marker in required.items() if marker not in ci_text]
            report_case("CI fails closed when a flag, the launcher or the guard call is tampered with (V26-01)",
                        not missing, "missing from ci.yml: " + ", ".join(missing) if missing else
                        "all four mutations present; a surviving mutation fails the job")
        with tempfile.TemporaryDirectory() as tmp:
            frames = {"__init__.py": b"",
                      "probe_common.py": b"MARK = 'common'\n",
                      "probe9_child.py": b"print('VERIFIED-RUN', flush=True)\n"}
            origins = {name: os.path.join(tmp, name) for name in frames}
            digests = {name: hashlib.sha256(chunk).hexdigest() for name, chunk in frames.items()}
            control = transport.run_child(frames, digests, origins, "probe9_child", [])
            control_out = control.stdout.decode()
            report_case("control: a child runs the module the parent sent (V23-01)",
                        control.returncode == 0 and "VERIFIED-RUN" in control_out,
                        f"exit {control.returncode}, stdout {control_out.strip()[:60]!r}")

            substituted = dict(frames)
            substituted["probe9_child.py"] = b"print('SUBSTITUTED', flush=True)\n"
            refused = transport.run_child(substituted, digests, origins, "probe9_child", [])
            refused_out = refused.stdout.decode()
            refused_err = refused.stderr.decode().strip().splitlines()
            report_case("a child REFUSES a frame that does not match its manifest digest (V23-01)",
                        refused.returncode == transport.CHILD_REFUSED and "SUBSTITUTED" not in refused_out,
                        f"exit {refused.returncode}: {(refused_err[-1] if refused_err else 'no stderr')[:110]}")

            with open(origins["probe9_child.py"], "wb") as handle:     # the substitution a `-m` spawn would have run
                handle.write(b"print('FROM-DISK', flush=True)\n")
            on_disk = transport.run_child(frames, digests, origins, "probe9_child", [])
            disk_out = on_disk.stdout.decode()
            report_case("a child executes the VERIFIED bytes, never the file that replaced them (V23-01)",
                        on_disk.returncode == 0 and "VERIFIED-RUN" in disk_out and "FROM-DISK" not in disk_out,
                        f"stdout {disk_out.strip()[:40]!r} while the path held 'FROM-DISK'")

            environment = transport.child_env(digests, origins, "probe9_child", "module", [])
            altered = transport.BOOTSTRAP.replace("obs-child: REFUSED:", "obs-child: WELCOMED:")
            swapped = subprocess.run([sys.executable, *transport.CHILD_FLAGS, "-c", altered],
                                     input=transport.payload(frames), env=environment, capture_output=True, timeout=120)
            swapped_err = swapped.stderr.decode().strip().splitlines()
            report_case("a child started with a DIFFERENT bootstrap refuses to run at all (V23-01)",
                        swapped.returncode == transport.CHILD_REFUSED and swapped.stdout == b"",
                        f"exit {swapped.returncode}: {(swapped_err[-1] if swapped_err else 'no stderr')[:110]}")

            whole = transport.payload(frames)
            cut = subprocess.run([sys.executable, *transport.CHILD_FLAGS, "-c", transport.BOOTSTRAP],
                                 input=whole[: len(whole) // 2], env=environment, capture_output=True, timeout=120)
            cut_err = cut.stderr.decode().strip().splitlines()
            report_case("a TRUNCATED payload is refused, never half-executed (V23-01)",
                        cut.returncode == transport.CHILD_REFUSED and cut.stdout == b"",
                        f"exit {cut.returncode}: {(cut_err[-1] if cut_err else 'no stderr')[:110]}")

            # `tools/obs/probes/probe7_structure.py` exists on disk and is importable from this cwd; in the child the
            # package is closed, so an unverified sibling must be unreachable even though the file is right there.
            probe = (b"try:\n"
                     b"    import tools.obs.probes.probe7_structure as sibling\n"
                     b"except ModuleNotFoundError as exc:\n"
                     b"    print('CLOSED', exc, flush=True)\n"
                     b"else:\n"
                     b"    print('OPEN', sibling.__file__, flush=True)\n")
            closed = dict(frames)
            closed["probe9_child.py"] = probe
            closed_digests = {name: hashlib.sha256(chunk).hexdigest() for name, chunk in closed.items()}
            leaked = transport.run_child(closed, closed_digests, origins, "probe9_child", [])
            leaked_out = leaked.stdout.decode()
            report_case("a child's suite package is CLOSED: an unverified sibling cannot be imported (V23-01)",
                        leaked.returncode == 0 and "CLOSED" in leaked_out and "OPEN" not in leaked_out,
                        leaked_out.strip()[:100] or "no output")

            # V24-01: the child's INTERPRETER STARTUP is isolated too. This working directory plants the three things a
            # plain `python -c` resolved before the bootstrap's first line: a `sitecustomize` hook, and shadow modules
            # for `hashlib` (which payload verification itself calls) and `ssl`.
            with tempfile.TemporaryDirectory() as hostile:
                marker = os.path.join(hostile, "startup-ran.txt")
                with open(os.path.join(hostile, "sitecustomize.py"), "w", encoding="utf-8") as handle:
                    handle.write(f"open({marker!r}, 'a').write('sitecustomize\\n')\n")
                for shadow in ("hashlib", "ssl"):
                    with open(os.path.join(hostile, shadow + ".py"), "w", encoding="utf-8") as handle:
                        handle.write(f"open({marker!r}, 'a').write({shadow!r} + '\\n')\n"
                                     f"raise ImportError('the {shadow} shadow module executed')\n")

                def startup_ran() -> str:
                    try:
                        with open(marker, "r", encoding="utf-8") as handle:
                            return handle.read().strip()
                    except FileNotFoundError:
                        return ""

                # CONTROL: with the flags removed the SAME plant runs, so the isolated cases below are not vacuous.
                # `PYTHONPATH` is what `-I`/`-E` ignore, and `site` imports `sitecustomize` from it.
                subprocess.run([sys.executable, "-c", "pass"], cwd=hostile,
                               env={**os.environ, "PYTHONPATH": hostile}, capture_output=True, timeout=120)
                control_ran = startup_ran()
                report_case("control: the planted startup hook DOES run when the interpreter is not isolated (V24-01)",
                            "sitecustomize" in control_ran,
                            f"hooks that ran without -I -S: {control_ran!r}")
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(marker)

                probe_source = (
                    "import hashlib, json, os, ssl, sys\n"
                    "print('CHILD ' + json.dumps({\n"
                    "    'isolated': bool(sys.flags.isolated),\n"
                    "    'no_site': bool(sys.flags.no_site),\n"
                    "    'ignore_environment': bool(sys.flags.ignore_environment),\n"
                    "    'no_user_site': bool(sys.flags.no_user_site),\n"
                    "    'hooks': [n for n in ('site', 'sitecustomize', 'usercustomize') if n in sys.modules],\n"
                    "    'cwd_on_path': [e for e in sys.path\n"
                    "                   if e in ('', '.') or (e and os.path.abspath(e) == os.getcwd())],\n"
                    "    'hashlib': hashlib.__file__,\n"
                    "    'ssl': ssl.__file__,\n"
                    "    'digest': hashlib.sha256(b'x').hexdigest()[:16],\n"
                    "}), flush=True)\n")
                probe_bytes = probe_source.encode("utf-8")
                probe_frames = {"__program__": probe_bytes}
                probe_digests = {"__program__": hashlib.sha256(probe_bytes).hexdigest()}
                # `PYTHONPATH` points at the hostile directory on purpose: -I must ignore it.
                startup_env = transport.child_env(probe_digests, {"__program__": "<obs-child-program>"},
                                                  "__program__", "program", [])
                startup_env["PYTHONPATH"] = hostile
                startup = subprocess.run([sys.executable, *transport.CHILD_FLAGS, "-c", transport.BOOTSTRAP],
                                         input=transport.payload(probe_frames), env=startup_env, cwd=hostile,
                                         capture_output=True, timeout=120)
                report: dict = {}
                for line in startup.stdout.decode().splitlines():
                    if line.startswith("CHILD "):
                        report = json.loads(line[len("CHILD "):])
                ran = startup_ran()
                report_case(
                    "a child's interpreter is ISOLATED and site-free (V24-01)",
                    startup.returncode == 0 and report.get("isolated") is True and report.get("no_site") is True
                    and report.get("ignore_environment") is True and report.get("no_user_site") is True
                    and report.get("hooks") == [] and report.get("cwd_on_path") == [],
                    f"exit {startup.returncode}, {report or 'no child report'}")
                report_case("a hostile sitecustomize.py in the child's cwd never executes (V24-01)",
                            startup.returncode == 0 and ran == "",
                            f"startup hooks that ran: {ran!r}" if ran else "no startup hook ran")
                report_case(
                    "a cwd hashlib.py / ssl.py cannot shadow the standard library in the child (V24-01)",
                    startup.returncode == 0 and report.get("hashlib") == hashlib.__file__
                    and not (report.get("hashlib") or "").startswith(hostile)
                    and not (report.get("ssl") or "").startswith(hostile)
                    and report.get("digest") == hashlib.sha256(b"x").hexdigest()[:16]
                    and ran == "",
                    f"hashlib {report.get('hashlib')!r}, ssl {report.get('ssl')!r}, "
                    f"digest {report.get('digest')!r}, hooks ran {ran!r}")
                bare = subprocess.run([sys.executable, "-c", transport.BOOTSTRAP],
                                      input=transport.payload(probe_frames),
                                      env=transport.child_env(probe_digests, {"__program__": "<obs-child-program>"},
                                                              "__program__", "program", []),
                                      cwd=ROOT, capture_output=True, timeout=120)
                bare_err = bare.stderr.decode().strip().splitlines()
                report_case("a child started WITHOUT -I -S is refused, never measured (V24-01)",
                            bare.returncode == transport.CHILD_REFUSED and bare.stdout == b""
                            and "not started isolated" in bare.stderr.decode(),
                            f"exit {bare.returncode}: {(bare_err[-1] if bare_err else 'no stderr')[:110]}")

                # V25-01: each flag REMOVED ON ITS OWN, in the same hostile directory. Its `hashlib.py` records itself
                # and raises, so "did the plant run" is a file on disk, not an opinion about the source.
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(marker)
                # CONTROL: with `-I` gone, `PYTHONPATH` and the child's cwd are importable again, so a plain
                # `import hashlib` DOES execute the plant. Without this, "nothing ran" below would prove nothing.
                subprocess.run([sys.executable, "-S", "-c", "import hashlib"], cwd=hostile,
                               env={**os.environ, "PYTHONPATH": hostile}, capture_output=True, timeout=120)
                shadow_ran = startup_ran()
                report_case("control: the planted hashlib.py DOES execute once -I is removed (V25-01)",
                            "hashlib" in shadow_ran,
                            f"plants that ran without -I: {shadow_ran!r}")
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(marker)

                # (a) `-I` removed, `-S` kept: nothing protects the import path, so the guard has to refuse BEFORE
                # `import hashlib` is reached. The plant must never execute and no payload byte may be read.
                no_isolation = subprocess.run([sys.executable, "-S", "-c", transport.BOOTSTRAP],
                                              input=transport.payload(probe_frames),
                                              env={**startup_env, "PYTHONPATH": hostile}, cwd=hostile,
                                              capture_output=True, timeout=120)
                no_isolation_err = no_isolation.stderr.decode().strip().splitlines()
                ran_without_i = startup_ran()
                report_case("-I removed, -S kept: the child FAILS CLOSED and no shadow hashlib.py runs (V25-01)",
                            no_isolation.returncode == transport.CHILD_REFUSED and no_isolation.stdout == b""
                            and ran_without_i == "",
                            f"exit {no_isolation.returncode}, plants that ran {ran_without_i!r}: "
                            f"{(no_isolation_err[-1] if no_isolation_err else 'no stderr')[:110]}")

                # (b) `-S` removed, `-I` kept, and NEITHER a plant nor `PYTHONPATH` in reach (V26-01). This is the honest
                # case: `site` has already run by the time the bootstrap starts, so the only thing left to demonstrate is
                # that the child DETECTS the missing flag and refuses to be measured. Nothing here claims to have
                # prevented a system hook — that is the static invariant's job, checked above and in CI.
                with tempfile.TemporaryDirectory() as neutral:
                    neutral_env = {key: value for key, value in startup_env.items() if key != "PYTHONPATH"}
                    no_site_flag = subprocess.run([sys.executable, "-I", "-c", transport.BOOTSTRAP],
                                                  input=transport.payload(probe_frames), env=neutral_env,
                                                  cwd=neutral, capture_output=True, timeout=120)
                no_site_err = no_site_flag.stderr.decode().strip().splitlines()
                no_site_text = no_site_err[-1] if no_site_err else ""
                report_case("-S removed: the child DETECTS the missing flag and refuses — prevention is static (V26-01)",
                            no_site_flag.returncode == transport.CHILD_REFUSED and no_site_flag.stdout == b""
                            and "DETECTION ONLY" in no_site_text,
                            f"exit {no_site_flag.returncode}: {no_site_text[:130]}")

    with tempfile.TemporaryDirectory() as tmp:
        tree(tmp)
        path = os.path.join(tmp, "run_all.py")
        data, size, digest = read_regular(path, "run_all.py")
        want = hashlib.sha256(data).hexdigest()
        report_case("a regular file still hashes to its own bytes", (size, digest) == (os.path.getsize(path), want),
                    f"{size} B, {digest[:16]}…")

    total = counts["passed"] + counts["failed"] + counts["skipped"]
    print(f"{'PASS' if not counts['failed'] else 'FAIL'}: {counts['passed']} passed, {counts['failed']} failed, "
          f"{counts['skipped']} skipped ({total} cases)")
    if counts["skipped"]:
        print("      skipped cases are NOT passes: each names the capability this host lacked")
    return 0 if not counts["failed"] else 1


def collect(modules: dict[str, types.ModuleType]) -> list[dict]:
    """Run every probe module that was built from verified bytes (V22-01): no import, no path, no cache."""
    results: list[dict] = []
    for name in PROBES:
        produced = modules[name].main()
        results.extend(produced if isinstance(produced, list) else [produced])
    return results


def interposed(measurement: str, common: types.ModuleType) -> dict[str, int] | None:
    """Re-run one phase in a child with alloc_peak.so preloaded; None when the shim cannot be used.

    V23-01: the child is THIS driver, executed from the `run_all.py` buffer the manifest check accepted, and it verifies
    the tree itself before it measures anything (`--interpose` runs the same `check_manifest`). The old `-m` spawn left
    that child's own source unverified by its parent; the child still re-checks the tree, so this is defence in depth
    rather than a replacement for the check. V24-01: it is started `-I -S`, so its interpreter startup is isolated and
    site-free like every other child's, and the measurement window begins at exec as before.
    """
    module = BY_MEASUREMENT.get(measurement)
    if module is None or not os.path.exists(SHIM):
        return None
    done = common.run_suite_child("run_all", ["--interpose", module], env={"LD_PRELOAD": SHIM}, timeout=300, cwd=ROOT)
    if done.returncode != 0:
        return None
    data = json.loads(done.stdout.decode() or "{}")
    return {"peak": int(data["peak"]), "map_peak": int(data.get("map_peak", 0))}


def compare_inventory(expected: dict, detail: dict, common: types.ModuleType) -> list[str]:
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
    if per_request > common.HTTP_HEADROOM:
        failures.append(f"inventory: the per-request item bounds sum to {per_request} B > HTTP_HEADROOM "
                        f"{common.HTTP_HEADROOM}")
    return failures


def compare(expected: dict, measured: list[dict], probe_interposed, common: types.ModuleType) -> list[str]:
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
            if want.get("interposed_map_peak") is not None and instrument["map_peak"] > common.HTTP_HEADROOM:
                failures.append(f"{name}: direct-mmap channel {instrument['map_peak']} > HTTP_HEADROOM "
                                f"{common.HTTP_HEADROOM} (A.5.7: the malloc figure is no longer a usable bound)")
        if name == "native_headroom":
            detail = got.get("detail") or {}
            instrument = detail.get("interposed") or {}
            peak, map_peak = instrument.get("peak"), instrument.get("map_peak")
            if peak is None or map_peak is None:
                failures.append("native_headroom: interposer unavailable (the analytic term cannot be checked)")
                continue
            if peak > common.HTTP_HEADROOM:
                failures.append(f"native_headroom: request-region malloc peak {peak} > HTTP_HEADROOM "
                                f"{common.HTTP_HEADROOM}")
            # V18-03 fence: the direct-mmap channel is added to the malloc channel, so the SUM must fit the constant.
            if peak + map_peak > common.HTTP_HEADROOM:
                failures.append(f"native_headroom: malloc {peak} + direct mmap {map_peak} > "
                                f"HTTP_HEADROOM {common.HTTP_HEADROOM} (A.5.7 fence)")
            failures.extend(compare_inventory(expected, detail, common))
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
    sources: dict[str, bytes] = {}
    integrity = check_manifest(expected, keep=sources)     # V22-01: the hashed buffers are retained here
    if integrity:
        for line in integrity:
            print(line, file=sys.stderr)
        print("refused: the suite does not match expected.json; run --update-manifest only in a REVIEWED revision",
              file=sys.stderr)
        return 2
    if sys.version.split()[0] != PINNED_PYTHON:
        print(f"refused: interpreter {sys.version.split()[0]} != {PINNED_PYTHON} (A.1)", file=sys.stderr)
        return 2
    # V22-01: only now, after every check, is suite code turned into objects — and only from the bytes that passed.
    try:
        modules = load_verified_modules(sources)
    except SuiteIntegrityError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except SyntaxError as exc:
        print(f"refused: {exc.filename}:{exc.lineno}: {exc.msg} (V22-01)", file=sys.stderr)
        return 2
    # V23-01: hand the suite to probe_common, so every child is fed THESE buffers and the MANIFEST's digests. The rows
    # were validated by check_manifest above, and the buffers are the ones it accepted, so the two cannot disagree
    # without one of the two checks having failed first.
    manifest_sha = {row["path"]: row["sha256"] for row in expected["manifest"]["files"]}
    modules["probe_common"].register_sources(
        sources,
        {name: manifest_sha[CANONICAL_PREFIX + name] for name in sources},
        {name: os.path.join(HERE, name) for name in sources})     # the path `-m` used to execute from
    if mode == "--interpose":
        name = argv[2] if len(argv) > 2 else ""
        module = modules.get(name)
        if module is None:
            print(f"refused: {name!r} is not a probe of this suite (V22-01)", file=sys.stderr)
            return 2
        if hasattr(module, "interposed_pair"):
            pair = module.interposed_pair()
        else:
            pair = {"peak": int(module.interposed()), "map_peak": 0}
        print(json.dumps({"peak": int(pair["peak"]), "map_peak": int(pair.get("map_peak", 0))}))
        return 0
    if mode == "--record":
        print(json.dumps({"env": {"python": sys.version.split()[0], "platform": platform.platform()},
                          "measurements": collect(modules)}, indent=2))
        return 0
    measured = collect(modules)
    failures = compare(expected, measured, lambda name: interposed(name, modules["probe_common"]),
                       modules["probe_common"])
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
