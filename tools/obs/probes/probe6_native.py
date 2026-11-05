"""Probe 6 - native memory around ONE local-TLS request (Appendix A.5; direct-mmap fence A.5.7, V18-03).

Three instruments, all reported, none interchangeable:
  * mallinfo2 at six sample points -> max(uordblks + hblkhd) since the first sample. A LOWER BOUND (A.5.2/A.5.3):
    it is a net difference, blind to allocations that live and die inside the window, blind to other threads'
    arenas, and (for uordblks alone) blind to mmapped blocks - so hblkhd is added.
  * alloc_peak.so via LD_PRELOAD -> the true peak live-minus-baseline MALLOC bytes in the child that actually
    performs the request, across all malloc arenas and threads (A.5.4).
  * the same shim's direct-mmap counter -> the peak live anonymous-private MAPPING bytes since the same reset
    (A.5.7): the channel a malloc-only interposer cannot see, because Python's object allocator mmaps its arenas.
The gate NEVER treats the mallinfo2 delta as an upper bound.

The TLS fixture is the repository's `tests/fixtures/tls/localhost.pem` when present; otherwise an ephemeral
self-signed certificate is generated with `openssl` in a temporary directory, so a clean clone can run the gate
without committing key material (A.1, probes/README.md).
"""
from __future__ import annotations

import atexit
import ctypes
import http.server
import json
import os
import shutil
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
PAYLOAD = C.body(64 * 1024)          # a modest body: the native term is per-connection, not per-byte

_MATERIAL: tuple[str, str] | None = None


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


def _libc():
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.mallinfo2.restype = _Mi
    return libc


def sample() -> int:
    """In-use native bytes visible to the calling thread's arena(s): arena in-use + mmapped in-use."""
    info = _libc().mallinfo2()
    return int(info.uordblks) + int(info.hblkhd)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:                                   # noqa: N802 - http.server API
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *args: object) -> None:
        return


def _serve() -> http.server.ThreadingHTTPServer:
    cert, key = material()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def request_once(port: int, client: ssl.SSLContext) -> tuple[int, dict[int, int]]:
    """The client MUST run on the main thread: mallinfo2 reports only the calling thread's arena(s) (A.5.2)."""
    samples: dict[int, int] = {}
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        samples[0] = sample()                                   # before the handshake
        with client.wrap_socket(raw, server_hostname="localhost") as sock:
            samples[1] = sample()                               # after the handshake
            sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
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


def interposed_peak() -> dict[str, object] | None:
    """Re-run the same request in a child with alloc_peak.so; the child reports its own two peaks."""
    if not os.path.exists(SHIM):
        return None
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report = handle.name
    env = dict(os.environ, LD_PRELOAD=SHIM, ALLOC_PEAK_FILE=report, PYTHONPATH=ROOT)
    done = subprocess.run([sys.executable, "-m", "tools.obs.probes.probe6_native", "--child"],
                          env=env, capture_output=True, timeout=300, cwd=ROOT)
    if done.returncode != 0:
        return {"error": done.stderr.decode()[-400:]}
    data = json.loads(done.stdout.decode() or "{}")
    try:
        os.unlink(report)
    except OSError:
        pass
    return data


def child() -> int:
    """Child entry: build the fixture FIRST, reset the shim, then measure only the request region."""
    lib = ctypes.CDLL(None)
    lib.alloc_peak_peak.restype = ctypes.c_size_t
    lib.alloc_peak_map_peak.restype = ctypes.c_size_t
    cert, _ = material()
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cert)
    server = _serve()
    try:
        lib.alloc_peak_reset()                       # baseline AFTER the SSL context and the listener exist
        received, _ = request_once(server.server_address[1], client)
        peak = int(lib.alloc_peak_peak())
        map_peak = int(lib.alloc_peak_map_peak())
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({"peak": peak, "map_peak": map_peak, "bytes_received": received}))
    return 0


def main() -> list[dict]:
    cert, _ = material()
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cert)
    server = _serve()
    try:
        before = sample()
        received, samples = request_once(server.server_address[1], client)
        after = sample()
    finally:
        server.shutdown()
        server.server_close()
    peak = max(samples.values()) - before
    return [{
        "probe": "native_headroom",
        "peak": peak,
        "bound": None,
        "detail": {
            "instrument": "mallinfo2(uordblks+hblkhd) max over 6 sample points; LOWER BOUND (A.5.3)",
            "bytes_received": received,
            "after_minus_before": after - before,
            "samples": {str(k): v - before for k, v in sorted(samples.items())},
            "interposed": interposed_peak(),
        },
    }]


if __name__ == "__main__":
    if "--child" in sys.argv[1:]:
        raise SystemExit(child())
    print(C.canonical(main()))
