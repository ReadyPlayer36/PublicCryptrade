"""Probe 6 - native memory around ONE local-TLS request (Appendix A.5; inventory A.5.8, V19-03).

Three instruments, all reported, none interchangeable:
  * mallinfo2 at six sample points -> max(uordblks + hblkhd) since the first sample. A LOWER BOUND (A.5.2/A.5.3):
    it is a net difference, blind to allocations that live and die inside the window, blind to other threads'
    arenas, and (for uordblks alone) blind to mmapped blocks - so hblkhd is added.
  * alloc_peak.so via LD_PRELOAD -> the true peak live-minus-baseline MALLOC bytes in the child that actually
    performs the request, across all malloc arenas and threads (A.5.4).
  * the same shim's direct-mmap counter -> the peak live anonymous-private MAPPING bytes since the same reset
    (A.5.7): the channel a malloc-only interposer cannot see, because Python's object allocator mmaps its arenas.
The gate NEVER treats the mallinfo2 delta as an upper bound.

ONE PROCESS, ONE ROLE (v2.0). The loopback SERVER runs in a separate process (`--serve`), so the measured region
contains the CLIENT path only - what the runner actually costs. v1.9 ran both endpoints inside the measured process,
which inflated the figure with a server the runner never runs (the sum still passed, so the error was conservative,
but it made per-consumer attribution impossible).

STAGES (A.5.8, V19-03). The same fixture is measured five times in separate children, each reset immediately before its
region, so the total decomposes by subtraction instead of assertion:

  tcp        plain HTTP over loopback, 64 KiB body        - sockets and HTTP staging, no TLS
  handshake  TLS handshake, connection closed, no request  - TLS session state and record buffers
  empty      TLS + one request, zero-length response body  - adds request/response staging only
  full       TLS + one request, 64 KiB body                - adds body staging (the §6.4 recv chunk)
  big        TLS + one request, 1 MiB body                 - SCALING control: only the body term may grow

`full` is the gated region. A sixth measurement, `realloc_accounting` (V20-11/V20-12), runs the A.5.4 realloc-failure
regression in its own child under the interposer: 4 MiB live, `realloc(p, SIZE_MAX)` returns NULL with the block intact
and still owned, a second 4 MiB block, and the peak must show BOTH blocks (> 8,388,608 B). The pre-fix shim reported
4,198,384 B, so this is a gated regression, not a documented anecdote.

The inventory rows of A.5.8 are derived from constants and CHECKED against these stages:
`handshake` covers TLS-consumer bounds, `empty - handshake` the HTTP-staging bounds, `full - empty` the body term,
and `big - full` must track the extra body bytes (a consumer that scaled with anything else would surface here).

The TLS fixture is the repository's `tests/fixtures/tls/localhost.pem` when present; otherwise an ephemeral
self-signed certificate is generated with `openssl` in a temporary directory, so a clean clone can run the gate
without committing key material (A.1, probes/README.md).
"""
from __future__ import annotations

import atexit
import ctypes
import errno as errno_module
import hashlib
import http.server
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

from tools.obs.probes import probe_common as C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "tls", "localhost.pem")
SHIM = os.path.join(HERE, "alloc_peak.so")
PAYLOAD = C.body(64 * 1024)          # the normative recv chunk: the native term is per-connection, not per-byte
BIG_PAYLOAD = C.body(1024 * 1024)    # scaling control only (A.5.8)
KIND_BODY = {"connect": 0, "handshake": 0, "empty": 0, "full": 65536, "big": 1048576}
KINDS = ("connect", "handshake", "empty", "full", "big")
# cold_* = the FIRST such request in a fresh process (the worst case, and what a one-request session pays);
# warm_* = the same request after one throwaway run, i.e. the steady-state per-request cost (A.5.8).
STAGES = ("cold_connect", "cold_full", "warm_connect", "warm_handshake", "warm_empty", "warm_full", "warm_big")
# A.5.4's realloc-failure regression (V20-11/V20-12): 4 MiB live, a realloc that FAILS (NULL, block intact), then a
# second 4 MiB. The peak must count both blocks, so the floor is exactly 2 x 4 MiB and the pre-fix shim's 4,198,384 B
# (one block: the failed realloc erased the first) cannot reach it. The ceiling is the floor plus one block of slack for
# interpreter and allocator overhead; anything above it would mean more than the two blocks survived.
REALLOC_BLOCK = 4 * 1024 * 1024
REALLOC_FLOOR = 2 * REALLOC_BLOCK
REALLOC_CEILING = REALLOC_FLOOR + REALLOC_BLOCK
REALLOC_PATTERN = 0x5A

_MATERIAL: tuple[str, str] | None = None
_PAYLOAD = PAYLOAD


def material() -> tuple[str, str]:
    """(certificate, private key) for the loopback server: the committed fixture, else an ephemeral one."""
    global _MATERIAL
    if _MATERIAL is not None:
        return _MATERIAL
    if os.path.exists(FIXTURE):
        _MATERIAL = (FIXTURE, FIXTURE)          # combined PEM: the same file carries cert and key
        return _MATERIAL
    openssl = shutil.which("openssl")
    if openssl is None:
        raise SystemExit(f"missing TLS fixture {FIXTURE} and no `openssl` to generate one (see probes/README.md)")
    temporary = tempfile.mkdtemp(prefix="obs-probe6-")
    atexit.register(shutil.rmtree, temporary, True)
    cert, key = os.path.join(temporary, "cert.pem"), os.path.join(temporary, "key.pem")
    done = subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                           "-keyout", key, "-out", cert, "-subj", "/CN=localhost",
                           "-addext", "subjectAltName=DNS:localhost"],
                          capture_output=True, timeout=120)
    if done.returncode != 0:
        raise SystemExit(f"openssl could not create the TLS fixture: {done.stderr.decode()[-400:]}")
    _MATERIAL = (cert, key)
    return _MATERIAL


class _Mi(ctypes.Structure):
    _fields_ = [(name, ctypes.c_size_t) for name in
                ("arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks", "fsmblks", "uordblks", "fordblks",
                 "keepcost")]


_LIBC: ctypes.CDLL | None = None


def _libc() -> ctypes.CDLL:
    """One cached handle: rebuilding it per sample allocates inside the measured region (a v1.9 probe artifact)."""
    global _LIBC
    if _LIBC is None:
        _LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
        _LIBC.mallinfo2.restype = _Mi
    return _LIBC


def sample() -> int:
    """In-use native bytes visible to the calling thread's arena(s): arena in-use + mmapped in-use."""
    info = _libc().mallinfo2()
    return int(info.uordblks) + int(info.hblkhd)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:                                   # noqa: N802 - http.server API
        body = _PAYLOAD
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def _serve(port: int = 0, tls: bool = True) -> http.server.ThreadingHTTPServer:
    global _PAYLOAD
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    if tls:
        cert, key = material()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


GET = b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"


def request_once(port: int, client: ssl.SSLContext, samples: dict[int, int] | None = None) -> tuple[int, dict[int, int]]:
    """The client MUST run on the main thread: mallinfo2 reports only the calling thread's arena(s) (A.5.2)."""
    samples = {} if samples is None else samples
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        samples[0] = sample()                                   # before the handshake
        with client.wrap_socket(raw, server_hostname="localhost") as sock:
            samples[1] = sample()                               # after the handshake
            sock.sendall(GET)
            samples[2] = sample()                               # after the request bytes
            received = 0
            while True:
                chunk = sock.recv(65_536)
                if not chunk:
                    break
                received += len(chunk)
                samples[3] = sample()                           # mid-body
            samples[4] = sample()                               # last byte
    samples[5] = sample()                                       # after close
    return received, samples


def plain_once(port: int) -> int:
    """The same request without TLS: sockets and HTTP staging only (stage `tcp`)."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(GET)
        received = 0
        while True:
            chunk = sock.recv(65_536)
            if not chunk:
                break
            received += len(chunk)
    return received


def handshake_once(port: int, client: ssl.SSLContext) -> None:
    """TLS handshake and an orderly close, with no HTTP bytes (stage `handshake`)."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with client.wrap_socket(raw, server_hostname="localhost"):
            pass


def serve_forever_child(port: int, tls: bool, payload_bytes: int, cert: str = "", key: str = "") -> int:
    """`--serve`: the server half, in its OWN process, so it is never inside the measured region."""
    global _PAYLOAD, _MATERIAL
    if cert and key:
        _MATERIAL = (cert, key)          # the CLIENT's material: an ephemeral pair must be shared, not regenerated
    _PAYLOAD = C.body(payload_bytes) if payload_bytes else b""
    server = _serve(port=port, tls=tls)
    print(f"PORT {server.server_address[1]}", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown() or sys.exit(0))
    try:
        while True:
            threading.Event().wait(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


def start_server(kind: str) -> tuple[subprocess.Popen, int]:
    """Launch the server process and wait for its port."""
    command = [sys.executable, "-m", "tools.obs.probes.probe6_native", "--serve",
               str(KIND_BODY[kind]), "plain" if kind == "connect" else "tls"]
    if kind != "connect":
        cert, key = material()
        command += [cert, key]
    process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    line = process.stdout.readline().decode().strip()
    if not line.startswith("PORT "):
        process.kill()
        raise SystemExit(f"probe6: server did not start: {line!r} {process.stderr.read().decode()[-300:] if process.stderr else ''}")
    return process, int(line.split()[1])


def interposed_peak(stage: str = "full") -> dict[str, object] | None:
    """Re-run ONE stage in a child with alloc_peak.so; the child reports its own two peaks."""
    if not os.path.exists(SHIM):
        return None
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report = handle.name
    env = dict(os.environ, LD_PRELOAD=SHIM, ALLOC_PEAK_FILE=report, PYTHONPATH=ROOT)
    done = subprocess.run([sys.executable, "-m", "tools.obs.probes.probe6_native", "--child", stage],
                          env=env, capture_output=True, timeout=300, cwd=ROOT)
    if done.returncode != 0:
        return {"error": done.stderr.decode()[-400:]}
    data = json.loads(done.stdout.decode() or "{}")
    try:
        os.unlink(report)
    except OSError:
        pass
    return data


def run_stage(kind: str, port: int, client: ssl.SSLContext | None) -> int:
    """The client half of ONE stage; returns bytes received."""
    if kind == "connect":
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            return 0
    if kind == "handshake":
        handshake_once(port, client)
        return 0
    if kind == "empty":
        return request_once(port, client)[0]
    if kind == "big":
        return request_once(port, client)[0]
    return request_once(port, client)[0]


def realloc_child() -> int:
    """`--realloc`: the A.5.4 failure regression, measured in ONE child under alloc_peak.so (V20-11/V20-12).

    Two 4 MiB blocks are allocated with a KNOWN pattern. Between them the first is reallocated to `SIZE_MAX`, which glibc
    refuses: the call returns NULL, `errno` is ENOMEM, and the block is still the caller's - readable, byte-identical and
    writable. A shim that moves accounting on the failed call erases 4 MiB from the total, so the recorded peak shows
    one block instead of two; A.5.4 requires both. The digest is taken through the buffer protocol, so verifying 4 MiB
    does not allocate 4 MiB inside the measured region and inflate the figure being checked.
    """
    # CDLL(None) resolves through the GLOBAL scope, so these are the PRELOADED wrapper's symbols - a handle on
    # libc.so.6 would dlsym glibc's malloc directly and bypass the very counter this measurement is about.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.malloc.restype = ctypes.c_void_p
    libc.malloc.argtypes = [ctypes.c_size_t]
    libc.realloc.restype = ctypes.c_void_p
    libc.realloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.free.argtypes = [ctypes.c_void_p]
    lib = ctypes.CDLL(None)
    lib.alloc_peak_peak.restype = ctypes.c_size_t
    lib.alloc_peak_reset()
    first = libc.malloc(REALLOC_BLOCK)
    if not first:
        print(json.dumps({"stage": "realloc", "error": "malloc returned NULL"}))
        return 2
    ctypes.memset(first, REALLOC_PATTERN, REALLOC_BLOCK)
    view = (ctypes.c_char * REALLOC_BLOCK).from_address(first)
    before = hashlib.sha256(view).hexdigest()
    ctypes.set_errno(0)
    moved = libc.realloc(first, ctypes.c_size_t(-1))          # SIZE_MAX: cannot be satisfied
    failure_errno = ctypes.get_errno()
    returned_null = not moved
    intact = returned_null and hashlib.sha256(view).hexdigest() == before
    writable = False
    if intact:                                               # ownership: the caller may still write the block
        ctypes.memset(first, REALLOC_PATTERN ^ 0xFF, 1)
        writable = ctypes.string_at(first, 1) == bytes([REALLOC_PATTERN ^ 0xFF])
        ctypes.memset(first, REALLOC_PATTERN, 1)
    second = libc.malloc(REALLOC_BLOCK)
    if second:
        ctypes.memset(second, REALLOC_PATTERN ^ 0xFF, REALLOC_BLOCK)
    peak = int(lib.alloc_peak_peak())
    libc.free(first)
    if second:
        libc.free(second)
    print(json.dumps({
        "stage": "realloc", "peak": peak, "block_bytes": REALLOC_BLOCK, "floor": REALLOC_FLOOR,
        "ceiling": REALLOC_CEILING, "returned_null": returned_null, "errno": failure_errno,
        "errno_name": errno_module.errorcode.get(failure_errno, ""), "content_intact": intact,
        "writable_after_failure": writable, "second_block": bool(second),
    }))
    return 0


def realloc_regression() -> dict:
    """Run the regression child and turn its report into a GATED row: every clause is required (V20-11/V20-12)."""
    row: dict = {"probe": "realloc_accounting", "bound": REALLOC_CEILING, "peak": 0,
                 "detail": {"instrument": "alloc_peak.so malloc channel, one child (A.5.4)",
                            "block_bytes": REALLOC_BLOCK, "two_block_floor": REALLOC_FLOOR}}
    if not os.path.exists(SHIM):
        row["pass"] = False
        row["detail"]["error"] = "alloc_peak.so is not built: the regression cannot be measured (A.7.9, V19-04)"
        return row
    done = subprocess.run([sys.executable, "-m", "tools.obs.probes.probe6_native", "--realloc"],
                          env=dict(os.environ, LD_PRELOAD=SHIM, PYTHONPATH=ROOT),
                          capture_output=True, timeout=300, cwd=ROOT)
    stdout = done.stdout.decode()
    try:
        data = json.loads(stdout.splitlines()[-1] if stdout.strip() else "{}")
    except json.JSONDecodeError:
        data = {}
    peak = int(data.get("peak") or 0)
    checks = {
        "child_exit_ok": done.returncode == 0,
        "realloc_returned_null": data.get("returned_null") is True,
        "errno_enomem": data.get("errno") == errno_module.ENOMEM,
        "first_block_byte_identical": data.get("content_intact") is True,
        "first_block_still_writable": data.get("writable_after_failure") is True,
        "second_block_allocated": data.get("second_block") is True,
        "peak_counts_both_blocks": peak >= REALLOC_FLOOR,
        "peak_within_ceiling": peak <= REALLOC_CEILING,
    }
    row["peak"] = peak
    row["pass"] = all(checks.values())
    row["detail"].update({"checks": checks, "child": data, "returncode": done.returncode,
                          "stderr_tail": done.stderr.decode()[-400:]})
    return row


def child(stage: str) -> int:
    """Child entry: build the fixture and the client context FIRST, then measure ONLY the stage's region."""
    if stage not in STAGES:
        print(f"unknown stage {stage!r}; expected one of {STAGES}", file=sys.stderr)
        return 2
    primed = stage.startswith("warm_")
    kind = stage.split("_", 1)[1]
    lib = ctypes.CDLL(None)
    lib.alloc_peak_peak.restype = ctypes.c_size_t
    lib.alloc_peak_map_peak.restype = ctypes.c_size_t
    client = None
    if kind != "connect":
        cert, _ = material()
        client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cert)
    server, port = start_server(kind)
    try:
        if primed:
            run_stage(kind, port, client)            # throwaway: pays the one-time dynamic loading
        lib.alloc_peak_reset()                       # baseline AFTER the fixture, the context and the priming run
        received = run_stage(kind, port, client)
        peak = int(lib.alloc_peak_peak())
        map_peak = int(lib.alloc_peak_map_peak())
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    print(json.dumps({"stage": stage, "kind": kind, "primed": primed, "peak": peak, "map_peak": map_peak,
                      "bytes_received": received}))
    return 0


def inventory() -> dict[str, dict[str, int]]:
    """One child per stage; the total is `full`, and the items are differences of these rows (A.5.8)."""
    rows: dict[str, dict[str, int]] = {}
    for stage in STAGES:
        data = interposed_peak(stage)
        if not data or "peak" not in data:
            raise SystemExit(f"probe6: stage {stage!r} could not be measured under the interposer: {data}")
        rows[stage] = {"peak": int(data["peak"]), "map_peak": int(data["map_peak"])}
    return rows


def main() -> list[dict]:
    global _PAYLOAD
    _PAYLOAD = PAYLOAD
    cert, _ = material()
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cert)
    server = _serve(tls=True)                        # in-process server for the mallinfo2 series only (reported)
    try:
        before = sample()
        received, samples = request_once(server.server_address[1], client)
        after = sample()
    finally:
        server.shutdown()
        server.server_close()
    peak = max(samples.values()) - before
    rows = inventory()
    full = rows["cold_full"]
    return [{
        "probe": "native_headroom",
        "peak": peak,
        "bound": None,
        "detail": {
            "instrument": "mallinfo2(uordblks+hblkhd) max over 6 sample points; LOWER BOUND (A.5.3)",
            "bytes_received": received,
            "after_minus_before": after - before,
            "samples": {str(k): v - before for k, v in sorted(samples.items())},
            "interposed": {"peak": full["peak"], "map_peak": full["map_peak"]},
            "inventory": rows,
        },
    }, realloc_regression()]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--serve" in args:
        index = args.index("--serve")
        size = int(args[index + 1]) if len(args) > index + 1 else 65536
        secure = (args[index + 2] if len(args) > index + 2 else "tls") == "tls"
        cert = args[index + 3] if len(args) > index + 3 else ""
        key = args[index + 4] if len(args) > index + 4 else ""
        raise SystemExit(serve_forever_child(0, secure, size, cert, key))
    if "--child" in args:
        index = args.index("--child")
        raise SystemExit(child(args[index + 1] if len(args) > index + 1 else "full"))
    if "--realloc" in args:
        raise SystemExit(realloc_child())
    print(C.canonical(main()))
