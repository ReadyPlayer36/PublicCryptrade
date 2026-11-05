# Appendix A probe suite (`tools/obs/probes/`)

Physical, runnable form of the memory protocol in *OBS-01/02 Session Runner and Evidence Writer — Architectural
Blueprint* (Appendix A). The document's A.7 listings and this directory are the SAME bytes: A.0 records a SHA-256 for
every file, and `--manifest` prints the table to diff against it. If a listing and a file ever disagree, the file is
what runs and the document is wrong (G-V18-02).

These probes measure the runner's three transient phases (§6.5), the runner's seal byte-equality (§5.1.1) and the
native cost of one loopback TLS request (§6.6/A.5). They do NOT contact any exchange, use any network beyond
`127.0.0.1`, or import anything outside the standard library.

## Run

```sh
cd <repository root>
cc -shared -fPIC -O2 -o tools/obs/probes/alloc_peak.so tools/obs/probes/alloc_peak.c   # once per machine
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --check
```

Exit status: `0` every recorded value reproduced and every bound held; `1` a mismatch (printed on stderr); `2`
environment refused (interpreter is not the pinned CPython 3.12.3, the suite is incomplete, or `openssl` is missing).

Other modes:

```sh
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --record     # new expected.json body (REVIEWED revisions only)
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --manifest   # {path: sha256} for every suite file (A.0)
```

## Files

| File | Role |
|---|---|
| `probe_common.py` | constants (mirroring §12) and the deterministic worst-case fixtures; the shim's two getters |
| `probe1_phase1.py` | phase 1 — request path: 64 KiB chunked scratch accumulation, then `bytes(scratch)` |
| `probe2_seal.py` | phase 2 — §5.1.1 seal order, plus the BANNED retain-the-chunk variant (must fail its bound) |
| `probe3_decode.py` | phase 3 — the §5.1.2 `decode_pass` release order on ONE line at `MAX_LINE` |
| `probe4_decode_fresh.py` | phase 3 — the same order fed from a real `readline(MAX_LINE + 2)` buffer |
| `probe5_byte_equality.py` | §5.1.1 streaming writer byte-equality over the full session budget |
| `probe6_native.py` | native memory around one loopback TLS request: `mallinfo2` samples + the interposer's two channels |
| `probe7_structure.py` | phase 3 — the `scan_structure` pass (parse, key-check, DISCARD) |
| `alloc_peak.c` | `LD_PRELOAD` shim: malloc-family peak and direct anonymous-`mmap` peak |
| `run_all.py` | driver: `--check`, `--record`, `--manifest`, `--interpose` |
| `expected.json` | the recorded values, their bounds and tolerances (A.2/A.3) |
| `README.md` | this file |

## Instruments, and what each one cannot see

Three instruments, none interchangeable; the document's A.5 fences each one explicitly.

* **`tracemalloc`** — Python-object bytes by allocation site. Blind to C-level and allocator-internal memory.
* **`alloc_peak.c` malloc counter** — live `malloc`/`calloc`/`realloc`/`free` bytes across every malloc arena and
  thread, peak since `alloc_peak_reset()`. Counts blocks that glibc serves with `mmap` (they arrive through
  `malloc`), and counts allocations that live and die inside the region. Blind to memory obtained by calling `mmap`
  DIRECTLY — which is exactly how CPython's own object allocator obtains its 1 MiB arenas.
* **`alloc_peak.c` mmap counter** — live `MAP_ANONYMOUS|MAP_PRIVATE` mapping bytes, same reset/peak discipline. This
  closes the channel above for the native region: `probe6` reports it and the gate requires
  `malloc peak + mmap peak <= HTTP_HEADROOM`.
* **`mallinfo2()` samples** — REPORTED ONLY, never gated. A difference of two samples is a LOWER BOUND (A.5.2/A.5.3):
  it misses buffers that live and die between samples, sees only the calling thread's arena(s), and `uordblks` alone
  excludes mmapped blocks.

Arena-scale `mmap` reservations are not added to a `tracemalloc` figure for the phases (§A.5.7): a reservation is
address space, and the Python objects inside a touched pool are already counted by `tracemalloc`. Adding both would
double-count. The fence is applied where the two channels describe disjoint consumers: the native request region.

## TLS fixture (probe6)

`probe6` uses `tests/fixtures/tls/localhost.pem` when it exists (a combined certificate + key PEM; that is what the
repository's transport tests use). When it is absent — a clean clone — the probe generates an ephemeral self-signed
certificate with `openssl` in a temporary directory and deletes it on exit, so no key material is committed and the
gate still runs. To pin the exact recorded values, commit the fixture:

```sh
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj /CN=localhost \
  -addext subjectAltName=DNS:localhost -keyout key.pem -out cert.pem
cat cert.pem key.pem > localhost.pem
```

An ephemeral certificate changes the handshake's certificate chain size, which moves the request-region peak by a few
kilobytes; `expected.json` records a 20 % tolerance for that reason, and the analytic constant has 50 KiB+ of slack.

## What the gate asserts

1. every recorded `tracemalloc` peak, within its tolerance, and every phase bound;
2. the banned retain-the-chunk variant FAILS its bound (a mutation that must be killed);
3. the interposed malloc peak for each phase, within its tolerance, and inside the same bound;
4. byte equality of the streaming seal over the full session budget;
5. the native request region: malloc peak and direct-`mmap` peak each measured, and their SUM inside
   `HTTP_HEADROOM = 262,144 B`;
6. interpreter identity (`3.12.3`) and a complete file set — a partially copied suite refuses to run rather than
   silently narrowing the protocol.

A new interpreter, a new `MAX_BODY_BYTES`, a changed writer/reader or a new receipt schema invalidates every recorded
value: re-run `--record` inside a REVIEWED revision and record the numbers in A.2/A.3 in the same commit (D34/D42).
