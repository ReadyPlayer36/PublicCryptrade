# Appendix A probe suite (`tools/obs/probes/`)

Physical, runnable form of the memory protocol in *OBS-01/02 Session Runner and Evidence Writer — Architectural
Blueprint* (Appendix A). The document's A.7 listings and this directory are the SAME bytes: A.0 records a byte size and
SHA-256 for every file (including `expected.json`), and `expected.json` itself pins every OTHER file in this directory.
If a listing and a file ever disagree, the file is what runs and the document is wrong (G-V18-02).

These probes measure the runner's three transient phases (§6.5), the runner's seal byte-equality (§5.1.1), the native
cost of one loopback TLS request split into its consumers (A.5.8) and the integrity of the direct-`mmap` channel under
concurrency (A.5.9). They do NOT contact any exchange, use any network beyond `127.0.0.1`, or import anything outside
the standard library.

## Run

```sh
cd <repository root>
cc -shared -fPIC -O2 -Wall -Wextra -Werror -o tools/obs/probes/alloc_peak.so tools/obs/probes/alloc_peak.c
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --check
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --self-test
```

Exit status: `0` every recorded value reproduced, every bound held, every inventory item inside its derived bound, and
every file matching `expected.json`; `1` a measurement mismatch (printed on stderr); `2` refused — the suite does not
match `expected.json` (a file was modified, added or deleted), the interpreter is not the pinned CPython 3.12.3, or
`openssl` is missing.

The pass line names three DIFFERENT counts (V21-02): every suite file is inventoried (14), `expected.json` pins every
other one (13), and `expected.json` itself is pinned by §A.0 of the design document, because a file cannot contain its
own digest. v2.1 printed a single number ("14 files pinned by expected.json") and was wrong on two of the three.

Other modes:

```sh
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --self-test        # the integrity REFUSALS, as negative cases (CI)
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --record           # new measurements array (REVIEWED revisions only)
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --manifest         # path/bytes/sha256 for EVERY suite file (A.0)
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --update-manifest  # rewrite expected.json's manifest (REVIEWED only)
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --check --report artifacts/probes/report.json   # CI artifact
```

## The manifest is the gate (V19-05)

`expected.json` carries a `manifest` block listing every other file in this directory with its byte size and SHA-256.
The block is validated as DATA before it is trusted (V20-14): canonical `tools/obs/probes/<name>` paths only, no duplicate
paths or basenames, `bytes` a non-negative integer, `sha256` 64 lowercase hex, no unknown fields, no row for
`expected.json` itself and none for the `alloc_peak.so` build artifact — a malformed entry is a refusal to run.
`--check` verifies it BEFORE measuring anything and refuses (exit 2) on a modification, an addition or a deletion, so
the code that produces a number is exactly the code that was reviewed. `expected.json` cannot contain its own digest;
A.0 pins it against the document instead, and `--manifest` prints its digest too.

Every suite file is checked by IDENTITY as well as by name (V21-01). The inventory refuses any entry that is not a
regular file — a symlink pointing inside the suite, one pointing outside it, a dangling link, a directory, a FIFO, a
socket or a device — and every compared file is opened ONCE with `O_NOFOLLOW`, `fstat`ed and matched against its
`lstat`, so a path swapped for a link after the inventory is refused instead of hashed. `--self-test` runs those
refusals as negative regression cases, with a CONTROL that an honest tree is still accepted, and CI runs it before
the gate.

Nothing here is imported by PATH (V22-01). `--check` reads each suite file once, hashes that buffer against
`expected.json` and KEEPS it; only after every row matches does the driver `compile()` those buffers into fresh module
objects (`types.ModuleType`, registered in `sys.modules`) and execute them, so the code that produces a number is the
code a reviewer verified. Nothing the driver executes is re-read from disk and no `.pyc` is consulted for it, a file
that fails the check contributes no executable source at all, and the interposed child (`--interpose`) verifies and
binds the same tree by the same route before it measures. One path is deliberately outside this binding and is named
instead of implied: `run_all.py` itself, which the interpreter imports before any check can run (A.0 pins it;
`--manifest` prints its digest). The CHILDREN are inside it as of v2.4 — see the next section.

## A child starts from the same bytes (V23-01)

Under v2.3 the measured children (probe6's server, stage and `--realloc` children, probe8's mmap child) were started
with `python -m tools.obs.probes.<probe>`: the parent had verified the bytes, but the CHILD opened the file, in a
process that never read the manifest — the hole V23-01 reported, and the same defect V22-01 closed in the parent.
Every child is now started from the parent's retained buffers through `probe_common.spawn_suite_child` /
`run_suite_child` / `run_program`: the source goes over a PIPE, one frame per module carrying the SHA-256
`expected.json` PROMISES for that file, and the child recomputes it and refuses (exit 86, `obs-child: REFUSED: …`)
rather than execute a frame that does not match. The child's bootstrap is bound by its own digest — the parent passes
`sha256(bootstrap)` and the child hashes the `-c` argument it was actually started with (`sys.orig_argv`) — and its
`tools.obs.probes` package is CLOSED (`__path__ = []`), so a module the parent did not send cannot be imported from
disk there even though the file exists. Dependencies are not assumed: the closure is read with `ast` from the verified
sources, so `probe_common` travels ahead of every probe that imports it, and a child that starts its own children
(every probe6 stage) hands on the same buffers and the same digests.

What is preserved is what decides the numbers: a fresh interpreter per child, still counted by the shim from exec, so
Python startup remains inside the native peak; the same `cwd`; the same `sys.argv[0]` (`-m` gives the module path and
the parent passes that path); the same resets inside the measured regions; and the module still executed as
`__main__`. What the bootstrap costs the child is allocator state before its reset, and it moved two recorded
figures: `native_headroom.interposed` 214,120 → 217,072 B (against `HTTP_HEADROOM` 262,144) and `realloc_accounting`
8,398,608 → 8,398,528 B. Both are re-pinned with that reason in `expected.json`; both remain inside their bounds.
Running a probe on its own (`python -m tools.obs.probes.probe6_native`) has no registered suite and refuses to start
a child, instead of silently falling back to `-m`.

`--self-test` counts outcomes separately (V22-03): `23 passed, 0 failed, 1 skipped (24 cases)` rather than folding
skips into passes (`24 passed` where the device-node case can run). A case this host cannot run (no `CAP_MKNOD`, no
`O_NOFOLLOW`) prints as `skip` and never counts as a pass; the exit status depends only on failures. Its cases
include a real inode swapped between `lstat()` and `open()` (V22-02), so `samestat`'s refusal is demonstrated rather
than argued, and six of them start REAL children (V23-01): a frame whose digest does not match is refused instead of
executed, a child runs the bytes it was sent while the path it names holds different source, a swapped bootstrap and
a truncated payload are refused, and an unverified sibling cannot be imported from disk.

After a REVIEWED change: `--update-manifest` (this directory), then regenerate A.0/A.7 from the document (D44).

## Files

| File | Role |
|---|---|
| `probe_common.py` | constants (mirroring §12), the deterministic worst-case fixtures, the shim's getters, and the verified child transport — bootstrap, payload framing, `run_suite_child` (V23-01) |
| `probe1_phase1.py` | phase 1 — request path: 64 KiB chunked scratch accumulation, then `bytes(scratch)` |
| `probe2_seal.py` | phase 2 — §5.1.1 seal order, plus the BANNED retain-the-chunk variant (must fail its bound) |
| `probe3_decode.py` | phase 3 — the §5.1.2 `decode_pass` release order on ONE line at `MAX_LINE` |
| `probe4_decode_fresh.py` | phase 3 — the same order fed from a real `readline(MAX_LINE + 2)` buffer |
| `probe5_byte_equality.py` | §5.1.1 streaming writer byte-equality over the full session budget |
| `probe6_native.py` | native memory around one loopback TLS request: `mallinfo2` samples, both interposed channels, the five-stage / cold-vs-warm inventory (A.5.8), and the GATED `realloc`-failure regression (`--realloc`, A.5.4 V20-11/V20-12) |
| `probe7_structure.py` | phase 3 — the `scan_structure` pass (parse, key-check, DISCARD) |
| `probe8_mmap_threads.py` | A.5.9 — partial unmap, `mremap`, 8-thread concurrency and the fail-closed capacity abort |
| `alloc_peak.c` | `LD_PRELOAD` shim: malloc-family peak and a locked, range-aware direct-`mmap` peak |
| `run_all.py` | driver: `--check`, `--self-test`, `--record`, `--manifest`, `--update-manifest`, `--report`, `--interpose`; verified-byte module execution and child binding (V22-01, V23-01) |
| `expected.json` | the file manifest (size + SHA-256) AND the recorded values, bounds and inventory derivations |
| `README.md` | this file |

## Instruments, and what each one cannot see

Three instruments, none interchangeable; the document's A.5 fences each one explicitly.

* **`tracemalloc`** — Python-object bytes by allocation site. Blind to C-level and allocator-internal memory.
* **`alloc_peak.c` malloc counter** — live `malloc`/`calloc`/`realloc`/`free` bytes across every malloc arena and
  thread, peak since `alloc_peak_reset()`. Counts blocks that glibc serves with `mmap` (they arrive through
  `malloc`), and counts allocations that live and die inside the region. Blind to memory obtained by calling `mmap`
  DIRECTLY — which is exactly how CPython's own object allocator obtains its 1 MiB arenas. A `realloc` that returns
  `NULL` for a non-zero size leaves the old block valid and owned by the caller, so the shim moves NO accounting there
  (`realloc(p, 0)` is a free); subtracting the old size on failure would under-count a live block forever.
* **`alloc_peak.c` mmap counter** — live `MAP_ANONYMOUS|MAP_PRIVATE` mapping bytes, same reset/peak discipline, with a
  locked range table: partial unmaps subtract only the overlap, `mremap` is remove+add, adjacent ranges coalesce, and a
  table overflow ABORTS rather than dropping an entry, and so does a subtraction larger than the tracked total
  (`map_fail_underflow`, V20-13): clamping at zero would preserve a small, plausible, permanent under-count, which is the
  one failure this instrument exists to prevent (V19-01). `probe8` proves all four properties — and its overflow check is deliberately not "a child with capacity 1
  must abort": the interpreter's own startup mappings fill such a table first, so an abort proves nothing. It requires
  the EXACT diagnostic line with the numbers the child itself printed, flushed `MAPPED` lines showing the abort followed
  the intended mapping, the table filled to exactly its capacity, and a NEGATIVE CONTROL that reaches `SURVIVED` with the
  capacity untouched.
* **`mallinfo2()` samples** — REPORTED ONLY, never gated. A difference of two samples is a LOWER BOUND (A.5.2/A.5.3):
  it misses buffers that live and die between samples, sees only the calling thread's arena(s), and `uordblks` alone
  excludes mmapped blocks.

Arena-scale `mmap` reservations are not added to a `tracemalloc` figure for the phases (§A.5.7): a reservation is
address space, and the Python objects inside a touched pool are already counted by `tracemalloc`. Adding both would
double-count. The fence is applied where the two channels describe disjoint consumers: the native request region.

## The native inventory (A.5.8)

`probe6 --child <stage>` measures ONE stage per child process, with the loopback SERVER in its own process, so the
region is the client path only:

| Stage | What it does | Role |
|---|---|---|
| `cold_connect` | first TCP connect in a fresh process | prices the one-time dynamic loading (resolver/NSS), A.5.8 |
| `cold_full` | first TLS request in a fresh process | the GATED worst case (a one-request session) |
| `warm_connect` | connect after a throwaway run | baseline for the deltas |
| `warm_handshake` | TLS handshake only | TLS-session consumers |
| `warm_empty` | TLS + request, zero-length body | HTTP staging consumers |
| `warm_full` | TLS + request, 64 KiB body | adds the body-staging consumer |
| `warm_big` | TLS + request, 1 MiB body | SCALING control: only the body term may move |

`run_all.py` compares each item against the bound derived for it in `expected.json` (`inventory.items`), so a consumer
that outgrows its derivation fails the gate instead of hiding inside a tolerance.

## TLS fixture (probe6)

`probe6` uses `tests/fixtures/tls/localhost.pem` when it exists (a combined certificate + key PEM; that is what the
repository's transport tests use). When it is absent — a clean clone — the probe generates an ephemeral self-signed
certificate with `openssl` in a temporary directory and deletes it on exit, so no key material is committed and the
gate still runs. The certificate is passed to the server process, so both halves of the loopback pair share it. To pin
the exact recorded values, commit the fixture:

```sh
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj /CN=localhost \
  -addext subjectAltName=DNS:localhost -keyout key.pem -out cert.pem
cat cert.pem key.pem > localhost.pem
```

An ephemeral certificate changes the handshake's certificate chain size, which moves the request-region peak by a few
kilobytes; `expected.json` records a 20 % tolerance for that reason, and the analytic constant has ~48 KiB of slack.

## What the gate asserts

1. every file matches `expected.json` (size and SHA-256) and no file was added or deleted;
2. every recorded `tracemalloc` peak, within its tolerance, and every phase bound;
3. the banned retain-the-chunk variant FAILS its bound (a mutation that must be killed);
4. the interposed malloc peak for each phase, within its tolerance, and inside the same bound;
5. byte equality of the streaming seal over the full session budget;
6. the native request region: malloc peak and direct-`mmap` peak each measured, and their SUM inside
   `HTTP_HEADROOM = 262,144 B`, PLUS every A.5.8 inventory item inside its derived bound;
7. the direct-`mmap` channel under concurrency: exact partial unmaps, exact `mremap`, 8 threads whose simultaneity is
   provable from the recorded peak, a range table that returns to its baseline, and a fail-closed abort on overflow;
8. interpreter identity (`3.12.3`) and a complete, unmodified file set — a partially copied suite refuses to run rather
   than silently narrowing the protocol.

A new interpreter, a new `MAX_BODY_BYTES`, a changed writer/reader or a new receipt schema invalidates every recorded
value: re-run `--record` inside a REVIEWED revision and record the numbers in A.2/A.3 in the same commit (D34/D42).
