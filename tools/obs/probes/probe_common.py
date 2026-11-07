"""Shared harness for the Appendix A memory protocol. Deterministic, stdlib only, no network.

A CHILD PROCESS STARTS FROM THE PARENT'S VERIFIED BYTES (V23-01). Two probes measure in child interpreters —
probe6 (server, stage and realloc children) and probe8 (the mmap child and the capacity-exhaustion program) — and until
v2.3 those children were started with `python -m tools.obs.probes.<probe>`, which makes the interpreter open the module
FILE after the parent has verified a manifest the child never consults. A tree substituted between the parent's check
and the child's import would run unverified. That is what V23-01 reported, and the fix is here:

  * the parent sends the SOURCE over a pipe — the retained buffers `check_manifest(keep=...)` hashed, never a re-read;
  * every frame carries the SHA-256 the MANIFEST promises for that file (`expected.json`'s row, not a value re-derived
    from the buffer), and the child recomputes it and refuses to execute anything that does not match;
  * the child's own bootstrap text is bound the same way: the parent passes its digest, and the child hashes the `-c`
    argument it was started with (`sys.orig_argv`) and refuses when the two differ;
  * the suite package in the child is CLOSED (`__path__ = []`), so no import can fall back to the filesystem: a module
    the parent did not send does not exist for the child.

THE CHILD'S INTERPRETER STARTUP IS ISOLATED BEFORE ANY OF THAT RUNS (V24-01). v2.4 verified the payload but still
started the child as `python -c <bootstrap>`, so interpreter STARTUP was unprotected: `site` imports `sitecustomize`,
`PYTHONPATH` entries are searched, and the working directory is `sys.path[0]` for `-c`, so a plant could run before
the bootstrap's first line and shadow `hashlib` (which the payload verification itself uses). Every child is now
`python -I -S -c <bootstrap>`: `-I` drops `PYTHON*` from the environment, the user site directory and the working
directory from `sys.path`, and `-S` skips `site` altogether, so neither `sitecustomize` nor `usercustomize` is
imported and nothing in the working directory can resolve ahead of the real standard library. The bootstrap does not
take that on trust: its first action is `isolated()`, which refuses (exit 86) unless `sys.flags.isolated`, `no_site`,
`ignore_environment` and `no_user_site` are all set, no startup hook is in `sys.modules`, and no `sys.path` entry is
the working directory. Dropping a flag therefore FAILS CLOSED instead of quietly re-opening the hole, and `--self-test`
runs a child whose working directory holds a hostile `sitecustomize.py`, `hashlib.py` and `ssl.py` to prove that none
of them executes.

What is preserved is the measurement: the child is still a fresh interpreter whose startup is inside the shim's window
(the shim counts from exec, before this code runs), it still gets `cwd` = repository root and the same `sys.argv[0]`
(`-m` gives the module path, and that is what the parent passes), it still resets at the same points, and it still runs
its module as `__main__`. No test hook, no fallback: a probe started outside the driver has no registered suite and
refuses to start an unverified child rather than doing it the old way.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
import subprocess
import sys
import tracemalloc

# Section 12 constants - the probes never read these from a mutable config.
MAX_BODY_BYTES = 4 * 1024 * 1024
FRAMING_ALLOWANCE_BYTES = 512
MAX_LINE = 4 * ((MAX_BODY_BYTES + 2) // 3) + FRAMING_ALLOWANCE_BYTES  # 5,592,920
CHUNK_BYTES = 65_536
SEAL_SLICE_BYTES = 49_152  # 3 x 16,384: base64-aligned, no mid-line padding
SESSION_BODY_BUDGET_BYTES = 52_428_800
HTTP_HEADROOM = 262_144
PAD_LIMIT = 4_096

BOUNDS = {
    "phase1_request": 8_781_824,
    "phase2_seal": 151_552,
    "phase2_seal_no_del": 151_552,
    "phase3_decode": 11_202_224,
    "phase3_decode_fresh": 11_202_224,
    "phase3_structure": 11_202_224,
    "native_headroom": HTTP_HEADROOM,
}

RECORD_KEYS = frozenset({
    "seq", "role", "path", "start_ns", "end_ns", "status", "error", "group_name", "group_kind",
    "boundary_ms", "body_b64", "headers",
})

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PACKAGE = "tools.obs.probes"


def canonical(obj: object) -> str:
    """Step-1's serializer (runstore._canonical): sort_keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def body(size: int = MAX_BODY_BYTES) -> bytes:
    """Deterministic worst-case body: every byte value, repeated, exactly `size` bytes."""
    pattern = bytes(range(251))
    return (pattern * (size // len(pattern) + 1))[:size]


def record_line(body_bytes: bytes, pad: int = 0) -> bytes:
    """One schema-valid record line (12 keys, canonical order); `pad` extends the `error` field by `pad` bytes."""
    return canonical({
        "seq": 2000,
        "role": "K5m",
        "path": "/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1000&startTime=0&endTime=1",
        "start_ns": 1_700_000_000_000_000_000,
        "end_ns": 1_700_000_000_017_000_000,
        "status": 200,
        "error": "x" * pad,
        "group_name": "resync",
        "group_kind": "5m",
        "boundary_ms": 180000,
        "body_b64": base64.b64encode(body_bytes).decode("ascii"),
        "headers": [["content-type", "application/json"], ["x-mbx-used-weight-1m", "1234"]],
    }).encode("utf-8")


def line_at(content_bytes: int) -> bytes:
    """A valid record line whose UTF-8 content is EXACTLY `content_bytes` long (<= MAX_LINE)."""
    base = len(record_line(b""))
    if content_bytes < base:
        raise SystemExit(f"{content_bytes} is below the empty-body framing ({base} B)")
    target_b64 = content_bytes - base
    length = min(MAX_BODY_BYTES, 3 * (target_b64 // 4))
    line = record_line(body(length), 0)
    pad = content_bytes - len(line)
    if not 0 <= pad <= PAD_LIMIT:
        raise SystemExit(f"cannot build a {content_bytes}-byte line (pad {pad})")
    line = record_line(body(length), pad)
    assert len(line) == content_bytes, (len(line), content_bytes)
    return line


def shim():
    """ctypes handle on alloc_peak.so's getters; the caller must have LD_PRELOADed the shim (A.5.4/A.5.7)."""
    import ctypes

    lib = ctypes.CDLL(None)
    lib.alloc_peak_reset.restype = None
    lib.alloc_peak_peak.restype = ctypes.c_size_t
    lib.alloc_peak_map_peak.restype = ctypes.c_size_t
    return lib


def interposed_pair(lib, fn) -> dict[str, int]:
    """Reset the shim, run ONE measured region, and report both channels: malloc bytes and direct anon mmap bytes."""
    lib.alloc_peak_reset()
    fn()
    return {"peak": int(lib.alloc_peak_peak()), "map_peak": int(lib.alloc_peak_map_peak())}


def measure(name: str, fn, **detail) -> dict:
    """Run `fn` under tracemalloc; report the peak. INPUTS MUST BE BUILT OUTSIDE `fn` (A.1)."""
    tracemalloc.start()
    try:
        value = fn()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    bound = BOUNDS.get(name)
    return {
        "probe": name,
        "peak": peak,
        "bound": bound,
        "pass": None if bound is None else peak <= bound,
        "detail": {"value": value if isinstance(value, int) else None, **detail},
    }


# ---------------------------------------------------------------------------------------------------------------------
# V23-01: the verified child bootstrap.
#
# This source is what the parent runs in the child (`python -c <BOOTSTRAP>`). It is part of probe_common.py, so it is
# covered by probe_common.py's manifest digest; the child additionally requires the digest of the text it was actually
# started with to equal the one its parent passed, which is computed from THIS constant. Anything the child executes
# arrived on stdin and was checked against the manifest digests the parent sent. The bootstrap only transports and
# verifies: it makes no decision that a substituted payload could exploit.
# ---------------------------------------------------------------------------------------------------------------------
TRANSPORT_MAGIC = b"OBS-PROBE/1\n"
CHILD_REFUSED = 86          # a child refusal is never confused with a measurement failure (1) or an abort (SIGABRT)
# V24-01: isolated (-I: no PYTHON* environment, no user site, no working directory on sys.path) and site-free (-S: no
# sitecustomize/usercustomize import at startup). The bootstrap refuses to run when it was not started with both.
CHILD_FLAGS = ("-I", "-S")

BOOTSTRAP = r'''import builtins, hashlib, json, os, sys, types

REFUSED = 86
MAGIC = b"OBS-PROBE/1\n"
PACKAGE = "tools.obs.probes"


def refuse(why):
    sys.stderr.write("obs-child: REFUSED: " + why + "\n")
    sys.stderr.flush()
    os._exit(REFUSED)


def isolated():
    flags = sys.flags
    if not (flags.isolated and flags.no_site and flags.ignore_environment and flags.no_user_site):
        refuse("the child interpreter was not started isolated and site-free (-I -S): its startup hooks, "
               "PYTHONPATH or working directory were not protected (V24-01)")
    hooks = [name for name in ("site", "sitecustomize", "usercustomize") if name in sys.modules]
    if hooks:
        refuse("a startup hook ran before the bootstrap (%s): V24-01" % ", ".join(hooks))
    here = os.getcwd()
    for entry in sys.path:
        if entry in ("", ".") or (entry and os.path.abspath(entry) == here):
            refuse("the child's sys.path contains the working directory (%r): a shadow module could be imported "
                   "ahead of the standard library (V24-01)" % (entry,))


def settings():
    try:
        own = sys.orig_argv[sys.orig_argv.index("-c") + 1]
    except (AttributeError, ValueError, IndexError):
        refuse("the bootstrap cannot read its own source text (sys.orig_argv is unavailable): V23-01")
    if hashlib.sha256(own.encode("utf-8")).hexdigest() != os.environ.pop("OBS_CHILD_BOOTSTRAP", ""):
        refuse("the bootstrap text is not the verified bootstrap of the parent: V23-01")
    try:
        expect = json.loads(os.environ.pop("OBS_CHILD_EXPECT"))
        origin = json.loads(os.environ.pop("OBS_CHILD_ORIGIN"))
        target = os.environ.pop("OBS_CHILD_TARGET")
        mode = os.environ.pop("OBS_CHILD_MODE")
        argv = json.loads(os.environ.pop("OBS_CHILD_ARGV"))
    except (KeyError, ValueError) as exc:
        refuse("the parent's request is incomplete: %r: V23-01" % (exc,))
    if not isinstance(expect, dict) or not isinstance(origin, dict) or not isinstance(argv, list):
        refuse("the parent's request is malformed: V23-01")
    return expect, origin, target, mode, argv


def frames(data):
    if data[:len(MAGIC)] != MAGIC:
        refuse("the payload does not begin with the transport header: V23-01")
    index = len(MAGIC)
    out = []
    while True:
        if data[index:] == b"END\n":
            return out
        if data[index:index + 2] != b"F ":
            refuse("malformed payload at byte %d: expected a frame header or END: V23-01" % index)
        end = data.find(b"\n", index)
        if end < 0:
            refuse("truncated frame header at byte %d: V23-01" % index)
        try:
            name, length = data[index + 2:end].decode("ascii").rsplit(" ", 1)
            length = int(length)
        except (UnicodeDecodeError, ValueError):
            refuse("malformed frame header at byte %d: V23-01" % index)
        start = end + 1
        if length < 0 or start + length > len(data):
            refuse("frame %r is truncated: %d B promised, %d B present: V23-01"
                   % (name, length, len(data) - start))
        out.append((name, data[start:start + length]))
        index = start + length


def receive(expect):
    sent = {}
    for name, chunk in frames(sys.stdin.buffer.read()):
        if name in sent:
            refuse("frame %r was sent twice: V23-01" % name)
        if name not in expect:
            refuse("frame %r was never promised by the parent: V23-01" % name)
        got = hashlib.sha256(chunk).hexdigest()
        if got != expect[name]:
            refuse("frame %r hashes to %s..., the parent promised %s...: the source is NOT executed: V23-01"
                   % (name, got[:16], expect[name][:16]))
        sent[name] = chunk
    missing = [name for name in expect if name not in sent]
    if missing:
        refuse("the parent promised %s but sent no bytes: V23-01" % ", ".join(missing))
    return sent


def packages():
    built = {}
    for qualified in ("tools", "tools.obs", PACKAGE):
        module = types.ModuleType(qualified)
        module.__path__ = []         # CLOSED: no suite import may fall back to the filesystem (V23-01)
        module.__package__ = qualified
        sys.modules[qualified] = module
        built[qualified] = module
    built["tools"].obs = built["tools.obs"]
    built["tools.obs"].probes = built[PACKAGE]
    return built[PACKAGE]


def execute(name, chunk, path, into):
    exec(compile(chunk, path, "exec", dont_inherit=True), into)


def main():
    isolated()                                # V24-01: before anything reads the parent's request
    expect, origin, target, mode, argv = settings()
    sent = receive(expect)
    package = packages()
    skip = target if mode in ("module", "program") else ""
    for name in expect:                       # payload order, which is dependency order (V23-01)
        if name == skip:                      # executed ONCE, as __main__ (or as the program), never twice
            continue
        path = origin.get(name, name)
        if name == "__init__.py":
            package.__file__ = path
            execute(name, sent[name], path, package.__dict__)
            continue
        short = name[:-3] if name.endswith(".py") else name
        qualified = PACKAGE + "." + short
        module = types.ModuleType(qualified)
        module.__file__ = path
        module.__package__ = PACKAGE
        sys.modules[qualified] = module
        setattr(package, short, module)
        execute(name, sent[name], path, module.__dict__)
    common = sys.modules.get(PACKAGE + ".probe_common")
    if common is not None and hasattr(common, "register_sources"):
        common.register_sources(dict(sent), dict(expect), dict(origin))
    if mode == "program":
        if "__program__" not in sent:
            refuse("the parent asked for a program but sent no source: V23-01")
        sys.argv = ["-c"] + list(argv)
        execute("__program__", sent["__program__"], "<obs-child-program>",
                {"__name__": "__main__", "__builtins__": builtins})
        return
    if mode != "module":
        refuse("unknown child mode %r: V23-01" % (mode,))
    if target not in sent:
        refuse("the target %r was never sent by the parent: V23-01" % (target,))
    path = origin.get(target, target)
    script = types.ModuleType("__main__")
    script.__file__ = path
    script.__package__ = PACKAGE
    script.__builtins__ = builtins
    sys.modules["__main__"] = script
    sys.argv = [path] + list(argv)            # what `-m` gives the module
    execute(target, sent[target], path, script.__dict__)


main()
'''

BOOTSTRAP_SHA256 = hashlib.sha256(BOOTSTRAP.encode("utf-8")).hexdigest()

# Filled by run_all.load_verified_modules -> register_sources, from the buffers the manifest check accepted.
_SOURCES: dict[str, bytes] | None = None
_DIGESTS: dict[str, str] | None = None
_ORIGINS: dict[str, str] | None = None


def register_sources(sources: dict[str, bytes], digests: dict[str, str],
                     origins: dict[str, str] | None = None) -> None:
    """Bind the verified suite to this process, so a child can be started from it (V23-01).

    `digests` are the values `expected.json`'s manifest promises for those files - not values re-derived from the
    buffers. The parent only calls this after `check_manifest` has required equality with the same rows, so the two
    agree, and a child handed a digest can check its payload against the manifest rather than against its sender.
    """
    global _SOURCES, _DIGESTS, _ORIGINS
    _SOURCES = dict(sources)
    _DIGESTS = dict(digests)
    _ORIGINS = dict(origins) if origins is not None else {
        name: os.path.join(HERE, name) for name in sources}


def registered() -> tuple[dict[str, bytes], dict[str, str], dict[str, str]]:
    """The suite this process may start children from; a refusal, never a filesystem fallback (V23-01)."""
    if _SOURCES is None or _DIGESTS is None or _ORIGINS is None:
        raise RuntimeError("no verified suite is registered in this process: a child is only ever started from the "
                           "driver's manifest-checked buffers (V23-01) — run `python -m tools.obs.probes.run_all`")
    return _SOURCES, _DIGESTS, _ORIGINS


def imports_of(data: bytes) -> list[str]:
    """Suite modules a verified source imports, read from the SOURCE rather than assumed (V23-01)."""
    try:
        tree = ast.parse(data)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == PACKAGE:
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE + "."):
                    names.append(alias.name[len(PACKAGE) + 1:])
    return [name for name in names if name and not name.startswith("_")]


def closure(sources: dict[str, bytes], target: str) -> list[str]:
    """`target` and its dependencies, dependency-first, starting with the package body (V23-01)."""
    order: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        filename = name if name.endswith(".py") else f"{name}.py"
        if filename in seen:
            return
        seen.add(filename)
        for dependency in imports_of(sources.get(filename, b"")):
            visit(dependency)
        if filename in sources:
            order.append(filename)

    if "__init__.py" in sources:
        visit("__init__")
    visit(target)
    return order


def packet(names: list[str]) -> tuple[dict[str, bytes], dict[str, str], dict[str, str]]:
    """Frames, manifest digests and origins for `names`, in the order the child must execute them."""
    sources, digests, origins = registered()
    absent = [name for name in names if name not in sources or name not in digests]
    if absent:
        raise RuntimeError(f"no verified bytes for {', '.join(absent)}: a child is never fed a file from disk (V23-01)")
    return ({name: sources[name] for name in names},
            {name: digests[name] for name in names},
            {name: origins[name] for name in names})


def payload(frames: dict[str, bytes]) -> bytes:
    """`MAGIC`, one `F <name> <length>\\n<bytes>` frame per module, then `END\\n` (V23-01)."""
    parts = [TRANSPORT_MAGIC]
    for name, data in frames.items():
        parts.append(b"F " + name.encode("ascii") + b" " + str(len(data)).encode("ascii") + b"\n" + data)
    parts.append(b"END\n")
    return b"".join(parts)


def child_command() -> list[str]:
    """The child's command line: isolated, site-free, and running this module's bootstrap (V24-01)."""
    return [sys.executable, *CHILD_FLAGS, "-c", BOOTSTRAP]


def frame_name(target: str) -> str:
    """The payload key a target travels under: `probe6_native` -> `probe6_native.py` (V23-01)."""
    if target == "__program__" or target.endswith(".py"):
        return target
    return target + ".py"


def child_env(digests: dict[str, str], origins: dict[str, str], target: str, mode: str,
              argv: list[str] | tuple[str, ...], extra: dict[str, str] | None = None) -> dict[str, str]:
    """The child's environment: the request, the digests it must see, and the bootstrap it must be running.

    `sort_keys` is deliberately off for the digest and origin maps: the child executes frames in the order the parent
    listed them, which is dependency order, and JSON objects keep insertion order.
    """
    env = dict(os.environ)
    # V24-01: the child is launched with -I (implied -E -s) and -S, so PYTHON* is ignored and no site directory exists.
    # Removing them here keeps the environment honest: nothing in it suggests the child needs a path to import from.
    for name in ("OBS_CHILD_EXPECT", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(name, None)
    env.update({
        "OBS_CHILD_BOOTSTRAP": BOOTSTRAP_SHA256,
        "OBS_CHILD_EXPECT": json.dumps(digests),
        "OBS_CHILD_ORIGIN": json.dumps(origins),
        "OBS_CHILD_TARGET": target,
        "OBS_CHILD_MODE": mode,
        "OBS_CHILD_ARGV": json.dumps(list(argv)),
    })
    if extra:
        env.update(extra)
    return env


def run_child(frames: dict[str, bytes], digests: dict[str, str], origins: dict[str, str], target: str,
              argv: list[str] | tuple[str, ...] = (), *, mode: str = "module",
              env: dict[str, str] | None = None, timeout: float = 300, cwd: str = ROOT) -> subprocess.CompletedProcess:
    """Run a verified child to completion, feeding it the payload on stdin (V23-01)."""
    target = frame_name(target)
    return subprocess.run(child_command(), input=payload(frames),
                          env=child_env(digests, origins, target, mode, argv, env),
                          capture_output=True, timeout=timeout, cwd=cwd)


def spawn_child(frames: dict[str, bytes], digests: dict[str, str], origins: dict[str, str], target: str,
                argv: list[str] | tuple[str, ...] = (), *, mode: str = "module", env: dict[str, str] | None = None,
                cwd: str = ROOT) -> subprocess.Popen:
    """Start a verified child and return it with its stdin already fed and closed (V23-01).

    The payload goes over a pipe rather than through a temporary file, so there is no path a substitution could
    redirect: the bytes the child sees are the bytes this process wrote.
    """
    target = frame_name(target)
    process = subprocess.Popen(child_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=child_env(digests, origins, target, mode, argv, env), cwd=cwd)
    try:
        assert process.stdin is not None
        process.stdin.write(payload(frames))
        process.stdin.close()
    finally:
        process.stdin = None
    return process


def suite_packet(target: str) -> tuple[dict[str, bytes], dict[str, str], dict[str, str]]:
    """Frames for `target` from the suite THIS process was started from (V23-01)."""
    sources, _digests, _origins = registered()
    return packet(closure(sources, target))


def run_suite_child(target: str, argv: list[str] | tuple[str, ...] = (), *, env: dict[str, str] | None = None,
                    timeout: float = 300, cwd: str = ROOT) -> subprocess.CompletedProcess:
    """Run one suite module from the verified buffers of this process (V23-01)."""
    return run_child(*suite_packet(target), target, argv, env=env, timeout=timeout, cwd=cwd)


def spawn_suite_child(target: str, argv: list[str] | tuple[str, ...] = (), *,
                      env: dict[str, str] | None = None, cwd: str = ROOT) -> subprocess.Popen:
    """Start one suite module from the verified buffers of this process (V23-01)."""
    return spawn_child(*suite_packet(target), target, argv, env=env, cwd=cwd)


def run_program(source: str, argv: list[str] | tuple[str, ...] = (), *, env: dict[str, str] | None = None,
                timeout: float = 300, cwd: str = ROOT) -> subprocess.CompletedProcess:
    """Run a LITERAL program in a verified child, with `sys.argv == ['-c', *argv]` (V23-01).

    probe8's capacity program is a string constant in probe8's verified source, so it travels through the same pipe and
    is checked against a digest of itself; nothing about it is left for the child to read from anywhere.
    """
    data = source.encode("utf-8")
    frames = {"__program__": data}
    digests = {"__program__": hashlib.sha256(data).hexdigest()}
    origins = {"__program__": "<obs-child-program>"}
    return run_child(frames, digests, origins, "__program__", argv, mode="program", env=env, timeout=timeout, cwd=cwd)
