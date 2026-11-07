# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v2.5 (NORMATIVE)

Status: design only. No live request is authorized by this document. Milestone 1 remains **BLOCKED** until the reviewer
accepts the protocol and a separately reviewed Step-2 implementation commit. This revision **supersedes v1.9**: it resolves
all five blocking findings of the v1.9 review (V19-01…V19-05, §1.0) and restates every affected section at implementation
granularity. Four changes of substance: the native instrument's direct-`mmap` channel is now THREAD-SAFE, RANGE-AWARE and
FAIL-CLOSED — one lock around the range table, true atomic read-modify-write totals, exact partial-unmap arithmetic,
`mremap`, and an abort instead of a silently dropped entry (A.5.4, A.5.9); the native headroom is no longer a four-row
assertion but an ALLOCATION INVENTORY whose every term is derived from a protocol constant and checked against a measured
stage, with the unenumerated remainder quantified (A.5.8); the probe suite is gated in CI on a freshly compiled interposer
with its raw outputs archived as an artifact (G-V19-04); and `expected.json` is a MACHINE-ENFORCED manifest — a modified,
added or deleted file refuses the run before any number is produced (A.0, G-V19-05). Where v1.9 and this document
disagree, this document governs, and sections not restated here remain normative as written in v1.9. The
v1.8/v1.7/v1.6/v1.5/v1.4/v1.3 maps are retained unchanged as §1.1–§1.6.

**v2.2 status (retained).** v2.2 supersedes v2.1 and closes the three findings of the v2.1 review (V21-01…V21-03,
§1.0c). It changes no measurement, no bound and no protocol constant: the protocol, §6.5's budgets, the allocation
inventory and all ten recorded readings stand exactly as reviewed. Three things change, and all three are about what the
EVIDENCE is worth: the gate now trusts the IDENTITY of a file rather than its name, so a symlink cannot stand in for a
probe and a path swapped mid-run is refused (V21-01); the run line and the report separate the three file counts that
v2.1 collapsed into one wrong sentence — 14 inventoried, 13 pinned by `expected.json`, and `expected.json` pinned by A.0
(V21-02); and the lineage claim is now an exact-SHA, exact-run statement rather than a working-tree disclaimer
(V21-03).

**v2.5 status (this revision).** v2.5 supersedes v2.4 and closes the v2.4 review's single blocking finding (V24-01,
§1.0e). v2.4 bound a child's PAYLOAD — every byte a child executes is a frame the parent verified against
`expected.json` — but the child INTERPRETER itself was still started `python -c <bootstrap>`, so its STARTUP was
unprotected: `site` imports `sitecustomize` from the environment, `PYTHONPATH` entries are searched, and for `-c` the
working directory is `sys.path[0]`, so a planted hook, or a shadow `hashlib.py` (the module the payload verification
itself calls), could run before the bootstrap's first line. Every child is now started `python -I -S -c <bootstrap>`
— isolated, site-free, no `PYTHON*` environment, no working directory on `sys.path` — and the bootstrap refuses
(exit 86) if it was started any other way, so a dropped flag fails closed. Four new self-test cases prove it in a
working directory holding a hostile `sitecustomize.py`, `hashlib.py` and `ssl.py`, including a CONTROL that the same
plant DOES run when the flags are removed. It changes no measurement, no bound and no protocol constant: all ten
gated readings stand exactly as recorded in v2.4.

**v2.4 status (retained).** v2.4 superseded v2.2 and folded in two review rounds: the v2.2 review's three
findings (V22-01…V22-03, §1.0c) and the v2.3 review's single blocking finding (V23-01, §1.0d). It changes no
measurement, no bound and no protocol constant — the protocol, §6.5's budgets, the allocation inventory and every
gated reading stand as reviewed — and it changes what the evidence is WORTH in four ways: the bytes a number comes
from are the bytes that were hashed, in the parent AND in every child interpreter (V22-01, V23-01); the race those
checks exist for is now INJECTED and demonstrated rather than argued (V22-02); the self-test reports passed, failed
and skipped as three separate numbers (V22-03); and no child process is started from a path any more (V23-01). Two
recorded native figures moved because a child's startup path changed — `native_headroom.interposed` 214,120 →
217,072 B and `realloc_accounting` 8,398,608 → 8,398,528 B — both re-pinned in `expected.json` with that reason and
both still inside their bounds. v2.3 was reviewed as a CODE revision before this document was revised; its correction
is recorded here rather than as a document of its own, and A.0 pins THIS revision's tree.

**v2.1 status (retained).** v2.1 superseded v2.0 and closed the five findings of the v2.0 review (V20-11…V20-15,
§1.0b). It re-opens nothing that v1.9 resolved: the protocol, §6.5's constants, the allocation inventory and every budget
stand exactly as reviewed. What it changed was the EVIDENCE CHAIN, in four places and one honesty rule: the `realloc`-failure
case of A.5.4 is now a gated measurement instead of a documented anecdote (V20-11/V20-12); the map live total aborts on
underflow instead of clamping at zero (V20-13); the manifest is validated as DATA — canonical paths, no duplicates,
typed fields — before any byte of it is trusted (V20-14); and this document no longer claims a passing run at a tree
where the gate did not pass (V20-15).

Anchor: repository `ReadyPlayer36/PublicCryptrade`, branch `main`, commit
`e30ef37011af7cc073fa13c8ee5384ae080995b5` (this revision's anchor: v2.1 as merged to `main`, and the tree that GitHub
Actions run `42208989835` gated). Its lineage is `impl-obs-step1` → `f337862e52dada43f425cee05154e18f212987aa` →
`dbfe53cecaea63b0a5128a756f5ede0c12c3ca6f` → `673f9a2ace30a449267adace9af0f9d94865bda1` →
`11ff12535e42639e3bab53304651e3ea2b5cd6b3` → `7b1493e` → `f0c0ad0` → `109a0d3` (v1.9) → `e30ef37` (v2.1), and it
carries every prior review. This document is reviewed against the actual Step-1 code in `tools/obs/` at `109a0d3`; those
citations stand unchanged because no probe change reaches that package. Branch-sync result re-established for this
revision: at `e30ef37` the `tools/obs/probes/` suite is byte-identical to the files A.0 pins — that run's
`run_all --manifest` step printed all thirteen digests, and they are the digests this appendix records (G-V21-03) — so
every number below is reproduced from those bytes rather than inherited as prose. Hard citations re-verified at
`109a0d3` (byte-identical to `f0c0ad0` and `7b1493e`): `audit.py` 70–86 (`abort_condition_seq`), 289–296 (check (g):
`wrapper_count` must be a caller-supplied integer — the "independent egress counter"), 619–631 (`audit_run` reloads the
run via `load_run` at 626); `runstore.py` 35/39–42 (format + frozen key sets), 45 (`ManifestError(ValueError)`), 172/217
(`_canonical`/`_lines`), 194–201 (`_parse_json` dialect: `_no_duplicate_keys`, `parse_constant` rejection), 206–209
(`record_to_json` base64-encodes the body), 221–244 (`write_run`: path opens, no fsync), 246–250 (`_read`), 253–258
(`load_manifest` fails closed without a 64-hex pin), 279–286 (`_jsonl`: whole-file split, truncation first), 291–346
(field validators), 348–357 (`_record_from_json` decodes `body_b64` from a str first), 370–388 (`load_run`); `eventlog.py`
50–58 (digest-line format; `bytes(r.body)` is `r.body` — probe-verified identity, so bodies hash in place). Phase memory
numbers in §6.5 and Appendix A are measurements over the exact normative sequences on CPython 3.12.3 (`tracemalloc`,
worst-case inputs); methodology, raw values, the native-instrumentation boundaries, the allocation inventory and the
probe sources are Appendix A. Those probes ARE repository code at `tools/obs/probes/` (fourteen files; A.0 records size
and SHA-256 for each, `expected.json` pins every other file, and the CI job compiles the interposer, proves the
integrity refusals and runs the gate — G-V19-04/G-V19-05/V20-14/V21-01). Hard citations re-verified at `109a0d3` (byte-identical to
`f0c0ad0` and `7b1493e`): `audit.py` 70–86 (`abort_condition_seq`), 289–296 (check (g): `wrapper_count` must be a
caller-supplied integer — the "independent egress counter"), 619–631 (`audit_run` reloads the run via `load_run` at 626);
`runstore.py` 35/39–42 (format + frozen key sets), 45 (`ManifestError(ValueError)`), 172/217 (`_canonical`/`_lines`),
194–201 (`_parse_json` dialect: `_no_duplicate_keys`, `parse_constant` rejection), 206–209 (`record_to_json` base64-encodes
the body), 221–244 (`write_run`: path opens, no fsync), 246–250 (`_read`), 253–258 (`load_manifest` fails closed without a
64-hex pin), 279–286 (`_jsonl`: whole-file split, truncation first), 291–346 (field validators), 348–357
(`_record_from_json` decodes `body_b64` from a str first), 370–388 (`load_run`); `eventlog.py` 50–58 (digest-line format;
`bytes(r.body)` is `r.body` — probe-verified identity, so bodies hash in place). Phase memory numbers in §6.5 and Appendix A
are measurements over the exact normative sequences on CPython 3.12.3 (`tracemalloc`, worst-case inputs); methodology, raw
values, the native-instrumentation boundaries, the allocation inventory and the probe sources are Appendix A. Those probes
ARE repository code at `tools/obs/probes/` (fourteen files; A.0 records size and SHA-256 for each, `expected.json` pins
every other file, and the CI job compiles the interposer, proves the integrity refusals with `--self-test` and runs the gate —
G-V19-04/G-V19-05/V20-14/V21-01).

**What v2.2 claims, and where it is evidenced (V21-03).** v2.1 could report only a working-tree result, and said so
in the same sentence. That gap closed when the tree became a commit: `e30ef37011af7cc073fa13c8ee5384ae080995b5` on
`main`, GitHub Actions run `42208989835` (`CI` #180, attempt 1, `push`), job `Appendix A probe suite (native memory gate)`
`127862655167`, conclusion **success**. That job's gate step ran
`PYTHONPATH=$PWD python -m tools.obs.probes.run_all --check --report artifacts/probes/report.json`, printed
`report written to artifacts/probes/report.json` and
`PASS: 10 measurements, 14 files pinned by expected.json`, and exited 0; its `--manifest` step printed all thirteen
pinned digests, which are the digests A.0 records; and it uploaded `gate.log`, `manifest.json`, `report.json`, `build.log`
and the built interposer as `probe-suite-evidence` / `alloc-peak-so`. The ten measurements in this appendix are therefore
a claim about a COMMIT — those bytes, CPython 3.12.3, gcc 13.3.0.
What is still NOT claimed, and is stated instead of blurred: (i) the line this revision PRINTS is not the line that run
printed — V21-02 corrects the count wording, so v2.2's line is
`PASS: 10 measurements; 14 suite files inventoried, 13 pinned by expected.json, expected.json pinned by Appendix A.0`,
demonstrated on the working tree this appendix pins, with the next pipeline run as its exact-SHA confirmation;
(ii) `alloc_peak.so` is compiled on the runner and never committed; (iii) a claim about a DIFFERENT commit needs a
different run.

Imperative key words MUST, MUST NOT, SHALL, SHOULD, SHOULD NOT are normative. "§n" refers to a section of this document;
"protocol §n" refers to `docs/obs-protocol.md` v0.5. Code identifiers in `monospace` refer to real symbols in `tools/obs/`
unless explicitly marked *runner* (Step-2 code that this document specifies).

## 0. Scope, artifact inventory and verification anchors

0.1 In scope: the session runner (the entity that drives a whole OBS-01 or OBS-02 session through the validated `Pacer`),
the evidence writer (staging → seal → self-verify → publish → receipt), the refusal journal, the terminal-state resolver
(`observe()`), signal handling, and the memory budgets of the runner process. Out of scope: the analysis function, golden
vectors GV-1…GV-9, and everything already validated in Step-1 (`pacer.py`, `transport.py`, `watchdog.py`, `admission.py`,
`estimator.py`, `audit.py`, `eventlog.py`, `runstore.py`, `specs.py`, `clock.py`, `params.py`).

0.2 The runner SHALL use only these validated building blocks with their existing semantics; this document never permits a
relaxed check in them. Where Step 2 extends a Step-1 entry point (**four** places exist: the dynamic-target admission
parameter of `execute`, §3.1, the chunked body-read path, §6.4, the evidence writer `write_run`, §5.1/§5.1.1 (added by
v1.5 for V14-01/V14-02), and — added by v1.6 for V15-02 — the evidence reader `load_run`, §5.1.2), the extension MUST
preserve every observable outcome of the current implementation (record shapes, error strings, error precedence,
counters, and for `write_run` the exact bytes it writes / for `load_run` the exact accept-reject set, error precedence
and `LoadedRun` contents — the `load_run` contract is made exact by v1.7 for V16-05 and is VERSIONED by v1.8 for V17-01 as the `obs-loader/2`
contract: Step-1's error precedence and JSON dialect are reproduced verbatim, with the `MAX_LINE` cap as the sole
documented acceptance divergence — an explicit, derived, versioned bound with its own registry, size table, precedence
position, differential corpus and, since v1.9 (V18-01), an explicit REJECTION POLICY: a line above the cap is refused by
design even where Step-1 would accept it, because Step-1 enforces no string length at all (§5.1.2.0–§5.1.2.6,
D35/D38/D39/D43)) and
land with the regression tests named in §11.

0.3 Persisted artifacts (all names are exact):

| Artifact | Format tag | Written by | Written when |
|---|---|---|---|
| `records.jsonl`, `events.jsonl`, `manifest.json` | `obs-run-manifest/1` | `runstore.write_run` (Step-2: §5.1.1 replacement) | SEALING, once, exclusive create, fsync F1–F4 |
| `<run_id>.refusal.json` | `obs-refusal/1` | *runner* `RefusalWriter` | pre-flight refusal, once, exclusive create |
| `<run_id>.receipt.json` (sibling of the run dir) | `obs-outer-index/1` | *runner* `ReceiptPublisher` | CP3, once, no-replace publication |
| `manifest.json` SHA-256 pin | (bare hex) | emitted by `write_run` return value | before CP1, out-of-band (§10.1) |
| `<run_id>.receipt.json` SHA-256 | (bare hex) | emitted by `ReceiptPublisher` after CP3e content re-proof (V17-02) | out-of-band (§10.1, V14-05) |
| `<run_id>.refusal.json` SHA-256 | (bare hex) | emitted by `RefusalWriter` after step 5 | out-of-band (§10.1, V14-05) |
| `transport.sent` decimal count | (bare decimal) | emitted by the runner beside the manifest pin, before CP1 | out-of-band (§10.1, V15-03) |

0.4 Directory layout under `RUN_ROOT` (a single directory on the evidence filesystem; `RUN_ROOT` is a plan parameter):

```
RUN_ROOT/
  <run_id>.refusal.json          # refusal journal, sibling of run dir (T0/T2 input)
  <run_id>/                      # FINAL run dir: records.jsonl, events.jsonl, manifest.json  (created only by renameat2)
  .<run_id>.staging/             # STAGING dir: same three files, plus seal-time fsync bookkeeping
  <run_id>.receipt.json          # outer index receipt (obs-outer-index/1)
  <run_id>.unverified/           # quarantine: any non-committed staging after failure (T5)
```

`run_id` matches `[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}`, is assigned at plan load (before pre-flight), and is never reused.
Staging and final names are single path components relative to `RUN_ROOT` (never contain `/`; the leading `.` of staging is
part of the name, so the staging name still contains no `/`).

0.5 Verification anchors used throughout: `tools/obs/audit.py::abort_condition_seq` (branch order, §3.3), `audit_pace`
checks (a)–(g) of `audit_pace`, `validate_missed_window_decision` + `validate_decision_evidence` (§4), `pacer.py::Pacer.execute`
(single-flight, record append, `abort_seq` convention), `watchdog.py::run_with_deadline` (absolute deadline + 1 s
cancellation allowance), `runstore.py` (manifest 8-key set, exclusive create, pin), `params.py` (all numeric constants).

## 1. Revision maps — V19 findings resolved in v2.0; V18/V17/V16/V15/V14/V13 findings retained

### 1.0 V19 findings resolved in v2.0

| ID | Finding (v1.9 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V19-01 | `alloc_peak.c`'s direct-`mmap` table was a single-writer array with no lock (`map_tab`/`map_used`), `map_untracked` decremented the live total with a load-then-store pair (a lost update under two cores), and a FULL table silently dropped the entry — which turns `map_peak` into an under-count, the one failure mode the instrument exists to prevent, in a region that runs a `ThreadingHTTPServer` and worker threads | §A.5.4 (concurrency and accounting contract), §A.5.9 (properties A–D), §A.7.9 (`alloc_peak.c`), §11 (G-V19-01), D46 | The range table and every live total are mutated under ONE spinlock; the totals use true atomic read-modify-write (`fetch_add`, and a CAS-decrement loop for subtraction — never a load/store pair); the peak is published with a compare-exchange loop so a second thread crossing the high-water mark cannot overwrite a higher value; and exhaustion of the table ABORTS with a diagnostic instead of dropping an entry (`ALLOC_PEAK_MAP_SLOTS` may only REDUCE the capacity, which is how the abort path is tested). Probe8 runs 8 threads × 64 iterations of map/partial-unmap/mremap/unmap and requires the peak to see all 8 MiB simultaneously AND the table to return exactly to its baseline |
| V19-02 | The same table tracked only `(addr, len)` pairs with an all-or-nothing `munmap` match: a PARTIAL unmap was ignored (the entry stayed, over-counting), `mremap` was not interposed at all (a moved or grown mapping was invisible), `MAP_FIXED` over an existing tracked range double-counted, and nothing coalesced adjacent ranges, so a page-by-page workload could exhaust a 512-slot table and — under V19-01's silent drop — lose bytes | §A.5.4 (range arithmetic), §A.5.9 (A/B), §A.7.9, §11 (G-V19-02), D47 | Bookkeeping is RANGE-based: `[start, start+len)`; a partial `munmap` subtracts exactly the overlap and keeps one surviving piece or SPLITS into two; `mremap` (incl. `MREMAP_MAYMOVE`, `MREMAP_FIXED` and `MREMAP_DONTUNMAP`) is accounted as remove(old) + add(new), and a source the shim never tracked is never started into the count; an `mmap` that replaces tracked bytes subtracts them first; adjacent ranges coalesce so the table is bounded by the number of DISJOINT regions, not by the number of calls. Probe8 asserts the exact byte counts (12,288 → hole → 8,192 in two ranges → 0; 8,192 → `mremap` → 32,768 → 0) |
| V19-03 | A.5's headroom was a four-row table of ASSERTED bounds ("TLS record buffers 32,768", "OpenSSL per-connection state 65,536") with no derivation, no per-consumer measurement, and the unenumerated remainder left as "× 2, covering unenumerated consumers" — a factor, not a bound | §A.5.8 (new: allocation inventory), §A.5.5 (restated), §A.2/A.3 (measured), §11 (G-V19-03), D48 | The request path is decomposed into an INVENTORY: five stages measured in separate children (the loopback server moved into its own process, so the region is the client path only), cold vs warm to separate the one-time dynamic loading from the per-request cost, and each consumer bounded as `unit × count` from a protocol constant (16,384 B TLS record, 16,384 B handshake/server state, 8,192 B `socket.makefile` buffer, 65,536 B `CHUNK_BYTES`, 8,192 B of allocator headers) and CHECKED against its stage by the gate. Measured: TLS session 77,864 B ≤ 98,304; HTTP staging 69,992 B ≤ 86,016; body staging 0 B ≤ 65,536; scaling control 0 B for a 1 MiB body; per-request bounds sum to 258,048 B ≤ 262,144 B; the one-time loading is 168,048 B and is charged to `HARNESS_FIXED_BUDGET_BYTES` rather than to a request |
| V19-04 | Nothing in CI compiled the interposer or ran the probe gate: the numbers in A.2/A.3 could drift, or the .so could fail to build on the runner, without any workflow failing — the suites' claims were reviewable but not enforced | §11 (G-V19-04), `.github/workflows/ci.yml` (`probe-suite` job), §A.1, D49 | A dedicated job pins CPython 3.12.3, asserts `cc`/`openssl`, compiles `alloc_peak.c` with `-Wall -Wextra -Werror`, runs `python3 -m tools.obs.probes.run_all --self-test` (V21-01's negative cases, archived as `self-test.log`) before `python3 -m tools.obs.probes.run_all --check --report artifacts/probes/report.json`, and uploads `gate.log`, `manifest.json`, `report.json`, `self-test.log`, `build.log` and the built shim as `probe-suite-evidence`/`alloc-peak-so` on EVERY outcome; the step preserves the gate's exit status through the pipe (`PIPESTATUS`) and mirrors the outcome into the job summary |
| V19-05 | A.0 pinned thirteen digests in the DOCUMENT, but the driver only checked that files EXISTED: a modified probe, an added file or a deleted one could still run, so the digest table was advisory and a reviewer's diff was the only enforcement | §A.0 (manifest chain), §A.7.12 (`expected.json`), `run_all.py` (`check_manifest`), §11 (G-V19-05), D50 | `expected.json` now carries a machine-readable `manifest` block (path, bytes, SHA-256) for every other file in the directory, and `--check` verifies it BEFORE measuring: a modification (size or digest), an ADDITION (a file not in the manifest) and a DELETION (a manifest entry with no file) each exit 2 with a per-file diagnostic. `expected.json` cannot hash itself, so A.0 pins IT against the document, `--manifest` prints its digest, and `--update-manifest` is the only writer — a reviewed-revision tool |

### 1.0b V20 findings resolved in v2.1 (retained)

v2.1 exists because the v2.0 review found the evidence chain unsound in three places, the instrument silently lossy in a
fourth, and the manifest gate red in CI. Every row is closed by a mechanism a reviewer can RUN; the numbers below are
measurements from the working tree A.0 pins.

| Finding | Defect as reviewed | Where it is closed | Mechanism |
|---|---|---|---|
| V20-11 | The `realloc`-failure rule of A.5.4 existed only as PROSE and a hand measurement (8,396,768 B vs the pre-fix 4,198,384 B). No probe asserted it, so a regression in `alloc_peak.c` would have changed no gate: the rule was reviewable, not enforced — the same defect class as V19-05 | §A.5.4 (realloc paragraph), §A.5.8 (the suite's measurements), §A.7.11 (`probe6_native.py`), §11 (G-V20-01), D52 | `probe6_native.py` gains a `--realloc` child and a GATED `realloc_accounting` measurement: 4 MiB with a known pattern, `realloc(p, SIZE_MAX)` must return NULL with `errno == ENOMEM`, the block must be byte-identical (SHA-256 taken through the buffer protocol) and still writable, a second 4 MiB block must be allocated, and the interposed peak must show BOTH blocks. Floor 8,388,608 B, ceiling 12,582,912 B. Measured on the v2.1 shim: **8,398,608 B**; with the A.5.4 guard REMOVED, the same child reports **4,200,608 B** and the gate fails. The 4 MiB blocks are allocated through `CDLL(None)`, i.e. the PRELOADED wrapper, because a handle on `libc.so.6` dlsyms glibc's `malloc` directly and would bypass the counter under test |
| V20-12 | The regression above needs a measurement that survives being re-run, and a manifest entry that closes: v2.0's `probe6_native.py` and `expected.json` were recorded for a file set that the same commit did not contain | §A.0 (size + SHA-256 rows), §A.7.11, `expected.json` manifest, D52 | `realloc_accounting` is a first-class row of `expected.json` (`bound` = the ceiling, `tolerance` 0.02 against the recorded peak) so a drifting figure fails `--check` instead of passing silently; `probe6_native.py` is re-pinned in A.0 and A.7 at its final size and digest, and A.0/A.7 are generated from the files rather than typed. The instrument's own symbol lookup is documented as a measurement hazard (previous row) |
| V20-13 | `map_live_sub()` clamped a subtraction larger than the tracked total (`cur > n ? cur - n : 0`). A clamped total is an under-count: it is small, plausible, permanent, and no later sample can reveal it — the one error the instrument exists to prevent (V19-01's silent drop, restored through arithmetic) | §A.5.4 (accounting contract), §11 (G-V20-03), D53 | The live total is never clamped: an underflow means the range table and the total disagree, so `map_fail_underflow()` writes `alloc_peak: FATAL: mmap accounting underflow: %zu B to subtract, %zu B tracked (regions %zu): refusing to clamp to zero` and calls `abort()`, under the same lock discipline as the capacity refusal. Demonstrated with a fault-injected build (one 4 MiB range silently lost from the table: `SIGABRT`, `4202496 B to subtract, 2121728 B tracked (regions 3)`), while the shipped build is unaffected. The path is NOT reachable from a correct shim, so it is verified once by fault injection rather than shipped as a test hook |
| V20-14 | `check_manifest()` indexed rows by BASENAME (`os.path.basename(row["path"])` into a dict), so two rows could share a name with one silently overwriting the other, a row naming `probe3_decode.py` or `/etc/x` still bound to the file in this directory, `bytes`/`sha256` of the wrong type were trusted until compared, and rows for `expected.json` or `alloc_peak.so` surfaced as a DELETION instead of the malformed entry they are. That is how a manifest can be green in review and red — or wrong — in CI | §A.0 (manifest chain), §A.7.12 (`expected.json`), `run_all.py` (`check_manifest`), §11 (G-V20-02), D54 | The manifest is validated as DATA before it is trusted: `manifest` must be an object with only `algorithm`/`files`, `algorithm` must be `sha256`, `files` must be a non-empty array of objects whose ONLY fields are `path`/`bytes`/`sha256`; `path` must be the canonical `tools/obs/probes/<name>`, duplicate PATHS and duplicate BASENAMES are refused, `bytes` must be a non-negative `int` (booleans excluded), `sha256` must be 64 lowercase hex; a row for `expected.json` (it cannot pin itself) and a row for the build artifact are refused BY NAME; unknown fields fail closed at row and block level. Twenty-three malformed manifests (duplicate path, duplicate basename under another directory, bare basename, absolute path, `"1234"`, `-1`, `true`, short/uppercase/missing digest, unknown field, non-object row, self-pin, artifact pin, `md5`, stray block field, `files` not a list, empty `files`, wrong size, wrong digest, deleted row, missing or invalid block) each produced exit-2 with a per-entry diagnostic, and the real manifest still validates — G-V20-02 exercises exactly that |
| V20-15 | The document claimed a passing run at the v2.0 revision ("`run_all --check` exits 0") that CI did not reproduce, and A.0/A.7 lagged the files they described — a review-lineage defect, not a code defect: a claim with no tree behind it | §1.0b (this table), the anchor paragraph of the preamble, §A.0 (regenerated), §A.7 (regenerated), §11 (G-V20-02), D55 | Every gate claim in this revision names its TREE: the working tree that produced A.0's digests, on the pinned interpreter, `PASS: 10 measurements, 14 files pinned` (v2.2 corrects THAT LINE'S COUNT — §1.0c V21-02 — because `expected.json` pins thirteen files, not fourteen). The v2.0 claim is WITHDRAWN in place (not deleted) with what CI actually reported, and A.0/A.7 are regenerated from the files by script at review time (not by CI — G-V18-02 b), so this revision's appendix matches its tree. A claim about a commit is left to the pipeline that can make one |

### 1.0c V21 findings resolved in v2.2 (retained)

v2.2 exists because the v2.1 review found the evidence chain trusting NAMES where it needed IDENTITIES, reporting a count
that was true of neither link in the chain, and still leaning on a working-tree claim after that tree had become a commit.
No measurement moved: `--check` still compares ten measurements against the same recorded values, on the same interpreter.

| Finding | Defect as reviewed | Where it is closed | Mechanism |
|---|---|---|---|
| V21-01 | The inventory and the manifest check followed symbolic links. `suite_files()` listed names and treated anything that was not a directory as a file; `check_manifest()` asked `os.path.isfile()` (which follows links and answers "yes" for a link to a regular file), took `os.path.getsize()` and then opened the path a SECOND time to hash it. A link named `probe6_native.py` — pointing at another probe, at a file outside the repository, or at `/dev/null` — was hashed as if it were that probe; a FIFO or a device in the directory was accepted as a suite file; and a path swapped between the size check and the hash was never noticed. The manifest pinned NAMES, and a name is not a body | §A.0 (identity paragraph), §A.7.10 (`run_all.py`), §11 (G-V21-01), D56 | Enumeration uses `os.scandir` with `lstat` semantics and REFUSES any entry that is not a regular file — link (inside the tree, outside it, dangling), directory, FIFO, socket, device — before a single measurement. Every compared file is opened ONCE with `O_NOFOLLOW\|O_CLOEXEC`, `fstat`ed and required to be the SAME inode (`os.path.samestat`) as the `lstat`, then required to have the size it was hashed at, so a post-enumeration substitution is refused rather than hashed; `expected.json` itself is read through the same helper. `--self-test` proves fourteen cases including a CONTROL that an honest tree is ACCEPTED (so "refuse everything" cannot pass): links inside / outside / added-after-the-inventory / dangling / to-a-device, a directory, a FIFO, a real character device (`/dev/null`), a direct `opened_regular` call on a link, `open(O_NOFOLLOW)` failing with `ELOOP`, a modified file still refused, and a regular file still hashing to its own bytes. CI runs `--self-test` before the gate |
| V21-02 | The success line read `PASS: 10 measurements, 14 files pinned by expected.json`, and `report.json` carried only the 14-row manifest. `expected.json` pins THIRTEEN files — it cannot contain its own digest — so the sentence was false about the thing it named, and a reader had to infer which of the two counts a number belonged to. In an evidence chain that is not cosmetic: a count that is off by one tells the reviewer which link they may skip | §A.7.10, §A.7.11 (`README.md`), §11 (G-V21-02), D57 | `coverage()` names all three counts and both outputs use it: `inventoried` (14 = A.0's rows, `expected.json` included), `pinned_by_expected_json` (13 = the manifest block) and `self` (`expected.json`, whose digest is PRINTED with `self_pinned_by` = Appendix A.0). The run line is `PASS: 10 measurements; 14 suite files inventoried, 13 pinned by expected.json, expected.json pinned by Appendix A.0`, followed by `expected.json sha256 <digest> (compare with A.0)`; `report.json` carries the same object; `--update-manifest` reports "13 files pinned (expected.json excluded…)". The v2.1 line is recorded as WRONG here rather than edited away |
| V21-03 | The preamble claimed a working-tree result — honest, but weaker than the evidence that existed, because `e30ef37` carried exactly those bytes and its pipeline was green. A reader could not name the run that produced the numbers, and "not demonstrated on a commit" became false the moment CI passed | the preamble ("What v2.2 claims"), §A (preamble), §11 (G-V21-03), D58 | The claim is stated with its exact identifiers: commit `e30ef370…`, run `42208989835`, job `127862655167`, conclusion `success`, the exact command, the exact lines it printed, and the artifact names; A.0's digests are the digests that run's `--manifest` step printed. The claim is SCOPED to what the run printed: the corrected reporting line of V21-02 is a working-tree result until the next run prints it, and that is written down instead of implied |

### 1.1 V18 findings resolved in v1.9 (retained)

### 1.0d V22/V23 findings resolved in v2.3–v2.4 (retained)

The v2.2 review asked whether the code that produced a number was the code that had been verified; the v2.3 review
showed the answer was still "not in the child processes". Both rounds are about one property — a reviewed digest must
describe bytes that RUN — so their rows are kept together and each states its own evidence. A figure that moved is
named in the row that moved it, and re-pinned in `expected.json` rather than in prose alone.

| ID | Defect | Where | Resolution and evidence |
|---|---|---|---|
| V22-01 | The manifest verified bytes the driver then did not execute: suite modules were imported by PATH after `check_manifest`, so an import re-opened the file (or a `.pyc` built from another version of it) and the digest described bytes other than the ones that ran | §A.0, §A.7.1, §A.7.10, §11 (G-V22-01), §12 | Nothing the driver runs is imported by path. `check_manifest(keep=…)` retains the buffer it HASHED, `load_verified_modules()` compiles those buffers (`compile(data, path, 'exec')`) into `types.ModuleType` objects registered in `sys.modules` before execution, and a module whose bytes are absent is a refusal — never a re-read. `--interpose` binds the same way before it measures; `grep -c import_module run_all.py` is 0 and a self-test case enforces it | 
| V22-02 | The `samestat` refusal of V21-01 was argued, not demonstrated: no case ever changed an inode between `lstat()` and `open()` | §A.0, §A.7.10, §11 (G-V22-01) | `--self-test` injects the race deterministically: a one-shot `os.open` hook writes a different file beside the target and `os.replace`s it into place between the two calls, and the case requires the refusal, a genuinely different `(st_dev, st_ino)` AND that the hook fired (so it cannot pass vacuously). Reported as `TOCTOU: an inode swapped between lstat() and open() is CAUGHT by samestat` with both inode numbers |
| V22-03 | The self-test folded skips into passes: a case this host could not run (no `CAP_MKNOD`) was counted as a pass, so a green run could hide what was not exercised | §A.7.10, §A.7.11, §11 (G-V22-03) | Outcomes are counted separately and the summary states all three: `PASS: 23 passed, 0 failed, 1 skipped (24 cases)` on a host without `mknod` (`29 passed` where the device-node case can run), followed by `skipped cases are NOT passes: each names the capability this host lacked`. Exit status depends only on failures |
| V23-01 | The parent executed verified buffers, but its CHILD interpreters did not: probe6's server/stage/`--realloc` children and probe8's mmap child were started with `python -m tools.obs.probes.<probe>`, so the child's interpreter opened the module FILE after the parent's check, in a process that never read the manifest — a tree substituted in that window ran unverified code inside a gated measurement | §A.0, §A.5.4, §A.5.8, §A.7.1, §A.7.7, §A.7.10, §A.7.14, §A.7.11, §11 (G-V23-01) | Every child is started from the parent's retained buffers: `probe_common` sends the source over a pipe, one frame per module with the SHA-256 `expected.json` promises for that file, and the child recomputes it and refuses (exit 86) instead of executing a mismatch. The bootstrap is bound by digest (`sys.orig_argv` vs the parent's `sha256(BOOTSTRAP)`), the child's suite package is CLOSED (`__path__ = []`), and dependencies travel by an `ast` closure of the verified sources. probe8's inline capacity program goes through the same pipe. Measurement semantics are preserved and stated (fresh interpreter counted from exec, same `cwd`, same `sys.argv[0]`, same resets, module run as `__main__`); the two figures the bootstrap moved are re-pinned above |

Retained verbatim: these rows describe what v1.9 did. Where a FIGURE changed in v2.0 (the native request region is now
client-only and measures 214,120 B with a 0 B direct-`mmap` channel, A.5.8), §1.0 and the section it cites govern.

### 1.0e V24 finding resolved in v2.5 (this revision)

The v2.4 review accepted the payload binding of V23-01 and found the remaining hole one layer down: the child PROCESS
was bound to verified bytes, the child's INTERPRETER STARTUP was not. v2.4 launched `python -c <bootstrap>` with no
`-I` and no `-S`, so `site` imported `sitecustomize` from the environment, `PYTHONPATH` entries were searched, and the
working directory sat at `sys.path[0]` for a `-c` command — all before the bootstrap's first statement. v2.5 closes it
at the launcher and again inside the child, and changes no measurement.

| ID | Defect as reviewed | Where it is closed | Mechanism |
|---|---|---|---|
| V24-01 | Child interpreters were launched without startup isolation: v2.4 started every child as `python -c <bootstrap>`, so `site` imported a `sitecustomize` from `PYTHONPATH`/the environment, `PYTHONPATH` was searched, and the working directory was `sys.path[0]` for `-c`. A planted `sitecustomize.py`, or a working-directory `hashlib.py` shadowing the module the payload verification itself calls, ran BEFORE the bootstrap's first line — outside every digest check | §A.7.1 (`probe_common.py`: `BOOTSTRAP`, `CHILD_FLAGS`, `child_command`, `child_env`), §A.7.10 (`run_all.py` self-test), §A.7.11 (`README.md`), §11 (G-V24-01), §12 | Every child is now `python -I -S -c <bootstrap>`: `-I` drops the `PYTHON*` environment, the user site directory and the working directory from `sys.path`; `-S` skips `site`, so neither `sitecustomize` nor `usercustomize` is imported and no working-directory module can resolve ahead of the standard library. The bootstrap does not trust its launcher: `isolated()` runs before it reads the parent's request and refuses (exit 86) unless `sys.flags.isolated`, `no_site`, `ignore_environment` and `no_user_site` are all set, no startup hook is in `sys.modules`, and no `sys.path` entry is the working directory. Four self-test cases prove it with REAL children in a working directory holding a hostile `sitecustomize.py` plus `hashlib.py`/`ssl.py` shadows: the hook never runs, `hashlib.__file__` is still the standard library's, the payload digest still verifies, a child started without the flags is refused — and a CONTROL shows the same plant DOES run when the flags are removed, so no case can pass vacuously. No measurement moved: the child is still counted by the shim from exec, so startup remains inside the native peak, and all ten gated readings are unchanged |


| ID | Finding (v1.8 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V18-01 | §5.1.2 called the over-long-line class "impossible under the frozen schema" and "proved unreachable for schema-valid artifacts". That claim is unproven and false in the general case: Step-1 validates NO string length — `_jsonl` splits on `b"\\n"` with no upper bound (runstore.py:279–286), `_record_from_json` bounds only three integer ranges (348–357), and `_req_str`/`_req_headers` accept arbitrarily long strings (304–331) — so a Step-1-ACCEPTED legacy artifact can exceed `MAX_LINE`, and `/2` would reject it silently as a side effect of a budget constant rather than as a stated policy | §5.1.2.6 (new: rejection policy), §5.1.2.0 R-1/R-6, §5.1.2.1 (predicate split), §5.1.2.4 (D-21…D-23), §5.1.2.5 (rewritten), §0.2, §11 (G-V18-01), D43 | `obs-loader/2` now states an EXPLICIT REJECTION POLICY: a line whose CONTENT exceeds `MAX_LINE` is rejected BY DESIGN with the deterministic P-6 message, whatever `/1` would have done with it. The impossibility claim is WITHDRAWN and replaced by two named predicates — CONFORMING (written by §5.1.1: the bound is a theorem) and LEGACY-ADMITTED (accepted by `/1`: the bound is NOT a theorem, and the artifact is refused with its line number) — the reachability evidence is cited line by line, and the corpus now ASSERTS reachability: the frozen `/1` oracle must ACCEPT fixture D-21 and `/2` must REJECT it with the cap message, so the case fails if it ever becomes vacuous. No flag, no tolerance, no truncation, no silent skip; verifying oversize legacy evidence requires a reviewed `obs-loader/3` |
| V18-02 | The Appendix A probe suite existed only as listings inside A.7: a reviewer could read it but not RUN it, nothing bound the printed numbers to bytes that exist, and a drift between a listing and the code it claims to be was undetectable | §A.0 (file manifest: path, role, size, SHA-256), §A.1, §A.2/A.3 (values from this run), §A.7 (mirrors regenerated from the files), `tools/obs/probes/` (13 files), §11 (G-V18-02), D44 | The suite is repository code at the paths the appendix names — `run_all.py`, `alloc_peak.c`, `expected.json`, `README.md` and `probe6_native.py`, plus the six other probe modules, `probe_common.py` and `__init__.py` that they import — and was executed from the repository root for this revision (`python -m tools.obs.probes.run_all --check` exits 0, twice). A.0 records size + SHA-256 per file, `run_all --manifest` prints the same table (G-V18-02 diffs them), the driver REFUSES to run when a file is missing, and A.7 is generated from the files, so a listing can no longer drift from the code it documents |
| V18-03 | A.5.4 asserted that `alloc_peak.c` "sees every arena and every thread" — but it wrapped only `malloc`/`calloc`/`realloc`/`free`. CPython's object allocator obtains its 1 MiB arenas with a DIRECT `mmap` that the shim never sees, and A.5 offered no argument bounding what an uninstrumented path could hide, so the headroom constant rested on an unexamined channel | §A.5.4 (interception inventory + fenced limits), §A.5.7 (new: direct-`mmap` fence and the allocator-independence proof), §A.2/A.3 (measured channels), §6.6, §11 (G-V18-03), D45 | The over-claim is withdrawn and the channel is closed by MEASUREMENT: `alloc_peak.c` now also interposes `mmap`/`mmap64`/`munmap` for `MAP_ANONYMOUS\|MAP_PRIVATE` and exposes a second peak — 16,384 B in the native request region and 0 B in each measured phase — and the gate requires `malloc peak + mmap peak ≤ HTTP_HEADROOM` (measured 195,184 + 16,384 = 211,568 ≤ 262,144). A.5.4 itemises every allocator that is and is not intercepted; A.5.7 proves the four-term constant bounds each consumer independently of which allocator serves it, page-rounding included |

### 1.2 V17 findings resolved in v1.8 (retained)

| ID | Finding (v1.7 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V17-01 | `MAX_LINE` was documented only as a "sole acceptance divergence" buried inside §5.1.2: no contract identity, no version, no statement that Step-2's bounded reader *supersedes* Step-1's unconstrained `_jsonl` string split, no exact size arithmetic beyond one formula line, no defined position in the error ladder, and no differential corpus — so the loader could evolve silently and the divergence was unenforceable | §5.1.2.0 (registry), §5.1.2.1 (bounds + boundary table), §5.1.2.2 (precedence ladder P-0…P-13 + the P-9a terminator rule), §5.1.2.3 (pseudocode), §5.1.2.4 (differential corpus D-01…D-23), §0.2, §12, D38/D39, G-V17-01 | New `obs-loader/2` contract with a named registry that SUPERSEDES `obs-loader/1` (Step-1, kept only as a hash-pinned test oracle), no negotiation and no fallback; `MAX_LINE` derived (`4 × ⌈MAX_BODY_BYTES/3⌉ + 512 = 5,592,920 B`) with an import-time assertion, a four-case boundary table (cap inclusive), a two-predicate split (CONFORMING is a theorem, LEGACY-ADMITTED is a refusal — the "impossible under the frozen schema" claim is withdrawn in v1.9, V18-01) and a measured framing allowance; a 14-row precedence ladder that places the cap in Step-1's pre-parse slot (after both digests, truncation first, before every parse error); and a reviewable 23-class differential corpus asserting identical messages, identical positions and identical `LoadedRun` against legacy records — which also fixed a real message-drift defect (v1.7 parsed the terminator-inclusive buffer, reporting `line 2 column 1` where Step-1 reports `line 1 column 6`) |
| V17-02 | Receipt publication step 5 compared `st_dst` against `st_src` — the PRE-SYSCALL stat of the staging NAME — so a substitution landing inside the stat→`renameat2` window published the impostor and SATISFIED the proof (`st_dst == st_src == impostor`): the "post-rename identity proof" was vacuous in exactly the window it claimed to close | §5.2 steps 3/5 (explicit `identity_source = CREATION`), §5.2.4 (new steps 1–9 incl. CP3e), §7.5 CP3, §10.1, D40, G-V17-02 | Destination verification now compares `(st_dst.st_dev, st_dst.st_ino)` **directly against `expect`**, the creation identity captured by `fstat(tmp_fd)` before close (and, for the run directory, by `fstat` of the `O_DIRECTORY` descriptor opened immediately after `mkdir`); `st_src` is demoted to a pre-syscall gate only, and quarantine moves — whose source identity cannot be known in advance — are the sole `OBSERVED` mode; a new CP3e re-proof re-reads the published receipt through the same descriptor-relative snapshot and requires its digest to equal the digest written, and the out-of-band `receipt_pin` is printed only after it |
| V17-03 | `observe()` handled the receipt as a sequence of independent looks: `receipt_exists()` before the read, `read_bytes(receipt_path)` by PATH, a sha256 of a buffer it then re-parsed, and a SECOND `receipt_exists()` after the audit — so a receipt swapped between the checks could flip T4↔T6/T3, a symlink/FIFO/non-regular substitution was reachable, and "presence" and "content" were never the same object | §9.2.0 (read discipline), §9.2.1 (`snapshot`), §9.2.2 (rewritten `OBSERVE`), §9.3, §10.2, D41, G-V17-03 | Every receipt (and journal) fact now comes from ONE descriptor-relative `snapshot(pfd, name, max_bytes)`: a single `O_RDONLY\|O_NOFOLLOW\|O_CLOEXEC\|O_NONBLOCK` open decides existence, one bounded read yields immutable `bytes`, and `sha256` is computed over exactly those bytes — so presence, content, authentication against the mandatory `receipt_pin` and parsing all bind the SAME object; the classifier branches on frozen facts only (`ABSENT` / `FAULT(kind)` / `Snapshot`), a second presence check is impossible by construction, and path-based reads plus any post-snapshot re-check are BANNED in `observe()` |
| V17-04 | A.5 presented Δ`mallinfo2().uordblks` as though it bounded the native peak: a before/after difference cannot see a buffer allocated and freed inside the window, `uordblks` excludes mmapped regions and every non-main arena, and the "the ceiling does not depend on rounding the headroom term down" claim therefore over-claimed certainty; the probe scripts also stayed outside the repository, so the numbers were unverifiable by a reviewer | Appendix A.0–A.7 (rewritten), §6.5 phase 1, §6.6, §12, D42, G-V17-04 | A.5 states the sampling boundary item by item (`uordblks` vs `hblkhd`, `MMAP_THRESHOLD`, per-thread arenas, allocator reuse, arena granularity, kernel socket buffers, amortised OpenSSL state), RETRACTS the v1.7 over-claim, and replaces inference with measurement: six sample points reported as a lower bound, an `LD_PRELOAD` peak interposer (`alloc_peak.c`) that counts real peak bytes across all arenas and threads (measured 8,396,848 / 147,848 / 11,186,544 B for the three phases, and 227,128 B for the request region against `HTTP_HEADROOM = 262,144`), plus the analytic four-term table (≤ 131,072 B, ×2) that explains the constant; A.0/A.7 specify the complete suite (9 Python modules + 1 C shim + `expected.json` + `README.md`) as repository files, and the whole suite was executed here: `run_all --check` exits 0 |

### 1.3 V16 findings resolved in v1.7 (retained)

| ID | Finding (v1.6 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V16-01 | The resolver treated `journal_pin`/`receipt_pin` as optional (`if pin is not None and sha256(raw) != pin`): a refusal authenticated only by its recomputable self-digest classified authoritative T0, and a receipt with no `receipt_pin` could accept T1/T6 — self-digests are tamper-evidence any same-UID writer can forge, so they granted authoritative status | §9.1, §9.2 rules R2/R3, §9.3 T0/T1/T3/T6 rows, §2.4, §10.1, D31, G-V16-01 | All three pins mandatory and fail closed: T0 requires `journal_pin` supplied ∧ byte-SHA-256 match; T1/T6 require `receipt_pin` supplied ∧ byte-SHA-256 match; pin absent or mismatched → T3 (never T0/T1/T6); self-digest recheck retained as necessary but not sufficient |
| V16-02 | `observe()`'s two quarantine calls were naked: `EEXIST` (`PublishConflict`) and `EPERM`/`EIO`/`ENOSYS`/`EXDEV`/`ENOSPC` (`PublishUnavailable`/`OSError`) escaped `observe()` as exceptions instead of resolving terminal states — the resolver could raise, breaking its exactly-one-T-row contract | §9.2 `try_quarantine` (both branches), §9.3 T5 row, D32, G-V16-02 | New `try_quarantine` helper that NEVER raises (`PublishConflict` → CONFLICT; `PublishUnavailable`/`PublishIdentityMismatch`/`OSError` → QUARANTINE-FAILED): final-branch QUARANTINE-FAILED → T5 immediately (final + unmovable stale staging fails closed), staging-branch → T5 on every outcome; seal-time step 5 stays strictly fatal (D28) |
| V16-03 | §7.5/K10–K12/T4 promised automatic T4→T6 receipt reconstitution ("`observe()` may complete CP2+CP3"), but the receipt's complete field set (admitted decisions, skip summaries, memory/diagnostics, pins, `wrapper_count`) exists only in the in-memory draft that dies with the process — no CP1-durable draft exists, so reconstitution is impossible | §5.3, §7.5, §8.5 K10–K12, §9.2, §9.3 T4 row, D14/D33, G-V16-03 | T4 made a TERMINAL incomplete state requiring operator review: no code path may write/fsync/publish a receipt after CP1, K10–K12 resolve T4 only, `observe()` is idempotent on T4; T4 still requires `pin` + full audit pass incl. check (g) with `egress_count` |
| V16-04 | The 12 MiB ceiling rested on quoted numbers with no reproducible measurement record in the document: probe methodology, raw CPython 3.12.3 values and the derivation of the 262,144 B native `HTTP_HEADROOM` term were external to the review artifact | new Appendix A, §6.5, §12, D34, G-V16-04 | New Appendix A: environment and protocol (CPython 3.12.3, `tracemalloc` over the exact normative sequences, worst-case inputs, fixed seeds), probe inventory (probe1–probe7), raw phase and banned-pattern tables (all values re-measured for this revision), and native-headroom accounting over a real local-TLS request via glibc `mallinfo2` (native-arena peak 277,120 B; conservative phase-1 total 8,739,616 ≤ 8,781,824 B) — the NATIVE half of this row is SUPERSEDED by V17-04/§1.1 and A.5: a Δ`uordblks` sample is a lower bound and is no longer offered as evidence |
| V16-05 | §5.1.2 interleaved structure and body-decode per line (line 1's bad body masked line 5's bad keys — Step-1 validates ALL lines' structure before decoding ANY body, runstore.py:375–379) and parsed with plain `json.loads`, accepting duplicate keys and `NaN`/`Infinity` that Step-1's `_parse_json` rejects; the §0.2 exact accept-reject/error-precedence contract was therefore not met | §5.1.2 rewritten, §0.2, §6.5 phase 3, D24/D35, G-V16-05 | Five bounded stages with Step-1's exact precedence (both digests → records structure for ALL lines → records decode for ALL lines → events structure → events decode → count), Step-1's JSON dialect (`_no_duplicate_keys`, `parse_constant` rejection, verbatim messages, normalization net), structure dicts discarded and decode re-reads (O(1) memory, two reads per file); sole documented acceptance divergence: lines longer than `MAX_LINE` — REACHABLE for `/1`-accepted legacy evidence, since Step-1 validates no string length (V18-01), and REFUSED by explicit policy with the P-6 message (§5.1.2.6/D43) because accepting them unbounded would violate the same review's budget |
| V16-06 | Resolver↔audit check (g) drift: `wrapper_count` could reach `audit_run` as `None`/non-int (failing only by incident), an UNAUTHENTICATED receipt's count could feed check (g) because `receipt_pin` was verified after the audit, and T4's precondition of an independent integer count == `len(records)` was implicit | §9.2 restructured (authenticate receipt → resolve `wc` → mirror check (g) → audit), §9.3 T4 row, D36, G-V16-06 | Receipt authenticated (R3) before ANY of its fields is used; `wc` sourced only from `egress_count` or authenticated `receipt.wrapper_count`; check (g)'s three tests (supplied, int-not-bool, `== len(records)`) mirrored explicitly and failed closed to T3/T5 BEFORE `audit_run`; T4/T1/T6 rows each state their count precondition |
| V16-07 | §5.2.4 published the receipt with `expect = None`: between writing `.<run_id>.receipt.tmp` and `renameat2` a same-UID process could substitute the temp file; neither step 3 nor step 5 pinned its inode, so foreign bytes could be published as the receipt | §5.2.4, §5.2 step 3, D37, G-V16-07 | `st_tmp = os.fstat(tmp_fd)` captured on the creation descriptor BEFORE close and passed as `expect` into `publish_file()`: step 3 pins `(st_dev, st_ino)` pre-syscall, step 5 proves post-rename identity (type relative to `st_src`, so files publish too); substitution → step-3 require aborts before the syscall, or step-5 `PublishIdentityMismatch` after it → CP3 fails → T4 (or T3 when foreign bytes stand under the final name — `receipt_pin` never matches) — terminal, never T6 |

### 1.4 V15 findings resolved in v1.6 (retained)

| ID | Finding (v1.5 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V15-01 | `stream_records` called `record_to_json(r)` twice per record (head and tail), each call base64-encoding the whole body (≤ 5,592,408 B string ×2 per record) — the seal's own framing destroyed even v1.4's declared 131,072 B phase-2 bound; it also mis-stated `body_b64`'s canonical position (it sorts FIRST, before `boundary_ms`, not between `boundary_ms` and `end_ns`), its head/tail byte joins produced invalid JSON, and the JSONL line terminator was never written | §5.1.1, §6.5 phase 2, D25, G-V15-01 | New metadata-only `record_meta_json(r)` (11 keys, never touches `r.body`; `record_to_json` banned from the writer), corrected `{`-head / `",`-tail framing proven byte-equal to `_lines([record_to_json…])` incl. a 4 MiB body (probe-verified), seal peak ≤ 151,552 B (measured 148,113 B) |
| V15-02 | `load_run` (runstore.py:370–388) reads whole files (`_read` → `read_bytes`) and splits them in memory (`raw.split(b"\n")`) holding every parsed record — verification of a 50 MiB session peaks at ≥ 139.8 MB, not 12 MiB; §6.5 phase 3 assumed an incremental reader that no code specified | new §5.1.2, §6.5 phase 3, §0.2, D24, G-V15-02 | New §5.1.2 incremental `load_run`: 64 KiB chunk reads, digest pass first (Step-1 error precedence preserved), `MAX_LINE`-capped line reader, decode → release → parse → release → encode → release → `b64decode(bytes)` record decoding (measured 11,188,261 B ≤ 11,202,224 B); declared the fourth Step-2 extension point with a byte-exact contract (v1.6's implementation of this row did NOT in fact preserve Step-1's precedence — found by V16-05, see §1.1) |
| V15-03 | §9.2 passed `wrapper_count = receipt.outer_count or structurally-derived`: `outer_count` is not a receipt key (`wrapper_count` is), `receipt` was referenced before it was parsed, and any value derived from the record stream makes audit check (g) tautological (audit.py:289–296 requires an INDEPENDENT counter, 623–624) | §9.2, §2.4, §10.1, §10.2, D26, G-V15-03 | `wrapper_count` sourced only from (1) the out-of-band `egress_count` print (`transport.sent`, flushed beside the manifest pin) or (2) `receipt.wrapper_count` (minted from `transport.sent` at CP3); disagreement → T3; absent both → check (g) fails → T5/T3; structural derivation explicitly banned |
| V15-04 | `load_run(final, pinned = pin if pin else receipt_pin(final))` called `receipt_pin` (a hex string, not a function) as if it produced a manifest pin; without `pin`, Step-1's `load_manifest` fails closed anyway (runstore.py:255–258), so v1.5's "structural verification still runs" was unimplementable for finals | §9.2, §9.3 T3/T4 rows, §7.5, §10.1, D27, G-V15-04 | `pin` mandatory to verify or recover a final: `pin` absent + final present → T5/T3 (fail closed, never T4/T6, no CP2/CP3 recovery); recovery (CP2+CP3) only with the independently supplied manifest pin; `receipt_pin` never used as a manifest pin |
| V15-05 | §5.2 step 5 swallowed a failed impostor quarantine (`except PublishUnavailable: pass`), leaving the impostor standing under `<run_id>` while the comment claimed T3; `PublishConflict` (EEXIST) escaped unhandled; `observe()`'s own quarantine calls could raise out of the resolver | §5.2 step 5, §5.2.5, §9.2, D28, G-V15-05 | Quarantine failure strictly fatal: no `pass`, every branch raises `PublishIdentityMismatch` with the cause chained, the runner dies before CP1b/CP2/CP3 so no receipt can exist; `observe()` catches quarantine failures and still returns exactly one T-row; classification-level guarantee with the residual stated |
| V15-06 | §5.2.5 bounded the mode (`& 0o022 == 0`) but never stated the UID trust boundary: no owner check (`st_uid`), no explicit statement about same-UID processes (which can rename inside `RUN_ROOT` without taking the flock) | §5.2 step 1, §5.2.5, D29, G-V15-06 | Owner validation `st_pfd.st_uid == os.geteuid()` at lock time; explicit two-tier boundary: different-UID writers kernel-prevented (owner-only mode + `O_NOFOLLOW` + identity re-proof), same-UID writers detected-not-prevented (step-5 inode proof, CP1b, pins → quarantine/T3/T5), §10.1 residual restated |
| V15-07 | The 12 MiB budget was asserted with formula-only phase peaks that did not match the code those paths would run (v1.5 phase 2 assumed 124,928 B while its own `record_to_json` calls cost ~11 MB; phase 3's `+1,024` term was 757 B short of measurement; no measured evidence) | §6.1, §6.5, §12, G-V13-04, G-V14-03, G-V15-07, D30 | Official `TRANSIENT_BUDGET_BYTES = 12,582,912` (D30) with per-instant measured proofs: peak₁ ≤ 8,781,824 (measured 8,724,640), peak₂ ≤ 151,552 (measured 148,113), peak₃ ≤ 11,202,224 (measured 11,188,261); budget = max ≤ 12,582,912, margin 1,380,688 B (12.3 %); banned patterns measured: `b64decode(str)` 15,381,335, `json.loads(bytes)` held 16,781,149, retained chunks 5,656,645 |

### 1.5 V14 findings resolved in v1.5 (retained)

| ID | Finding (v1.4 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V14-01 | Branch sync: the doc anchored to `f337862e…` while the branch tip is `dbfe53c…`, and it asserted `write_run` fsyncs/streaming behavior the actual code does not perform (no fsync anywhere; `_lines()` materializes whole files), while §0.2 named only two Step-2 extension points | Anchor, §0.2, §5.1, §5.1.1, §6.5 | Re-anchored to `dbfe53c…` with byte-identity proof (no code drift); third extension point declared: `write_run` is REPLACED by a descriptor-relative, streaming, fsync-safe writer, with an explicit code-versus-design reconciliation |
| V14-02 | Evidence-writer durability had no implementation source: the current `write_run` (runstore.py:221) performs zero fsyncs (file or directory) and opens by path, so the K2–K7 crash-resilience claims were unbacked | §5.1.1, §5.3, §7.5, §8.5 | Normative write sequence — `O_EXCL` dir-fd create, streamed per-record bytes, `fsync(file)×3`, `fsync(staging dir)`, later CP2 `fsync(pfd)` — mapped row-by-row to K2–K7 |
| V14-03 | §6.5's "largest transient = one base64 line ≈ 5.46 MiB, none concurrent" was wrong: `bytearray→bytes` doubles the body (2×`MAX_BODY_BYTES`), base64 string and JSON line coexist (≈ 11.19 MB), the actual seal materializes the whole file (≥ 2×4/3×50 MiB), and `json.loads` holds line + parsed string (2×max line) | §6.1, §6.4, §6.5, §12, E6, D13, D19, G-V13-04, G-V14-03 | Phase-by-phase simultaneous-peak arithmetic; streaming seal (48 KiB slices) and a single-copy verify rule; correct bound established: `TRANSIENT_BUDGET_BYTES = 12,582,912` (12 MiB, 12.5 % margin) |
| V14-04 | Pseudocode called a non-existent `clock.sleep_until(wait)` — wrong method name, and a duration where `Clock.sleep_until_ns` takes an absolute instant | §3.1.3 | `clock.sleep_until_ns(now + wait)` with the absolute-target note; conformance gate G-V14-04 |
| V14-05 | The outer receipt (`obs-outer-index/1`) and the refusal journal (`obs-refusal/1`) had no integrity mechanism — post-publication tampering was undetectable | §0.3, §9.1, §10.1, §10.2, D20, G-V14-05 | `journal_digest`/`receipt_digest` self-digests (manifest discipline) plus an out-of-band SHA-256 printed at publication and verified by `observe()` when supplied; forgery limits stated |
| V14-06 | Resolver pseudocode and the T0–T6 table disagreed: the quarantine artifact was never tested by the pseudocode (T5 unreachable for quarantine-only state), torn receipts were unhandled, an unknown `receipt.outcome` fell through to T6, and refusal+quarantine / K8 final+quarantine combinations were undefined | §9.2, §9.3, D23, G-V14-06 | Pseudocode re-derived over a five-artifact entry snapshot with explicit precedence; every table row has exactly one path and vice versa; exhaustive argument rewritten |
| V14-07 | TOCTOU: the step-3 `stat(staging)` → `renameat2` window was closed only by a post-hoc assert that aborted *after* publishing an impostor; no `RUN_ROOT` permission/symlink boundary; no content re-proof after rename | §5.2 steps 1/3/5, new §5.2.5, §7.5 CP1b, G-V14-07 | Absolute `RUN_ROOT`, `O_NOFOLLOW` open, owner-only mode check; pre-syscall re-stat; identity mismatch → quarantine the published name (never left standing); CP1b content re-verification against the pin before CP3; residual limits stated |
| V14-08 | The 250 ms second-signal deferral had no enforcement mechanism: a main-thread handler cannot run while the main thread is inside a blocking synchronous syscall | §2.1, §7.4, §8.4 E3, D22, G-V14-08 | Named daemon watchdog thread `obs-watchdog` arms once from the handler and exits the process via `os._exit` at the bound; deferred exit point after syscall + bookkeeping; EINTR/PEP-475 and D-state limits stated |

### 1.6 V13 findings resolved in v1.4 (retained)

| ID | Finding (re-audit) | Where resolved | Resolution in one line |
|---|---|---|---|
| V13-01 | v1.3's incident ladder listed `CANCEL_FAILED` before non-200 and folded memory aborts into the streak branch; that order does not match `audit.abort_condition_seq` branch-for-branch | §3.3 | Normative ladder reproduces the audit's four branches in the audit's exact order; memory/response ladders are separate post-ladder branches with a proven audit-compatibility rule |
| V13-02 | `renameat2(RENAME_NOREPLACE)` given as prose; syscall arguments unspecified | §5.2 | Exact argument list (both dirfds = locked `pfd`, component names, `flags = 1`), ctypes signature, errno contract |
| V13-03 | Directory-FD-relative handling, identity checks and fallback ban unspecified | §5.2 steps 1–5, §5.2.1–§5.2.4, §5.3 | `fstat(pfd)` vs `stat(path)` identity, staging inode pin, post-rename inode proof, component-name validation, fail-closed on `ENOSYS/EINVAL/EXDEV`, explicit ban of `os.rename`/`os.replace`/`link`+`unlink` |
| V13-04 | Memory domains not quantitative; chunk-level check and offline decompression bounds vague | §6 | Domains A (50 MiB session / 4 MiB response), B (`TRANSIENT_BUDGET_BYTES = 6 MiB` with arithmetic), C (bounded by construction); per-chunk aggregate check before retaining; `MAX_DECOMPRESSED_BYTES` + 1000:1 offline ceiling |
| V13-05 | v1.3 stated invariants as one-line summaries; no complete pseudocode for the execute loop, dynamic target re-evaluation or single-read admission | §3.1, §3.2, §4, §9.2, §5.2 | Complete normative pseudocode for every loop, with the single clock read that satisfies the admission predicate recorded verbatim as `start_ns`, and `D(X)` re-evaluated at every wake |

The v1.3 map (R1–R12, V12-01…V12-08) is superseded: R1/V12-01 → §3.3; R2/V12-08 → §3.4; R3/V12-05 → §3.1; R4 → §3.1.3;
R5/R6/V12-04 → §6; R7/V12-02/V12-03 → §5.2; R8/V12-06 → §9.1–§9.3, §10.2; R9 → §5.5; R10/V12-07 → §7; R11 → §8; R12 → §9.2–§9.3.

## 2. Components, threads and state

2.1 Process threads (exactly two long-lived worker threads plus — v1.5, V14-08 — one long-lived watchdog thread):

* **Orchestrator thread (main).** Owns: all pacing/admission clock reads, the admission predicate (§3.1), the incident
  ladder (§3.3), `decide_admission` calls, the event log, `retained_total`, lifecycle state, signal-flag checks, sealing,
  publication and the receipt. It is the only caller of `Pacer.execute`.
* **`obs-request` worker (`threading.Thread`, daemon=True, created inside `run_with_deadline`).** Performs socket I/O only.
  It reads the monotonic clock **only** for PACE-8 absolute-deadline enforcement (`over()` at worker entry, before connection
  setup, and inside `guarded_send` immediately before the write — the three points Step-1 tests pin). It never reads the
  clock for pacing, admission, target or record timestamps, and it never writes records, the event log or the budget's
  committed total.
* Signal handlers run on the orchestrator thread (Python semantics) and only set flags (§7.2).
* **`obs-watchdog` thread (daemon=True, v1.5).** Created before PRE-FLIGHT; it never touches the filesystem, never takes
  the publish lock and never raises — it only reads `time.monotonic_ns()` and calls `os._exit`. It exists solely to
  enforce the 250 ms second-signal bound when the orchestrator is inside a blocking checkpoint syscall (§7.4).

2.2 Runner objects and ownership:

```
SessionPlan      # loaded from the reviewed plan file; digest pinned in the receipt
Pacer            # existing; single-flight, records, abort_reason/abort_seq, streak
HttpTransport    # existing; sent counter (PACE-5 (g) wrapper_count), permanent disablement
OffsetEstimator  # existing; add(sample) from every recorded /time body
EventLogWriter   # existing; append_decision (skips only), append_timeline_end (§4.3; seal sequence §5.1)
SessionBudget    # runner; sole owner of retained_total (§6.2), mutated under single-flight only
Seal / Publish / ReceiptPublisher / RefusalWriter / observe()   # runner, §5, §7, §9
```

2.3 Lifecycle states (persisted in the receipt; `observe()` re-derives the terminal state independently):

```
PRE-FLIGHT → RUNNING → STOPPING → SEALING → VERIFYING → COMMITTING → COMMITTED
     │           │          │          │           │           │
     └───────────┴──────────┴──────────┴───────────┴───────────┴──→ EMERGENCY (second signal, §7.4)
```

* PRE-FLIGHT: plan load, allow-list self-check, cooldown file check, sync adequacy; refusals here write `obs-refusal/1` (§9.1).
  The only egress before RUNNING is the initial `/time` sync group (role `T`, group `sync`, ≥ 10 calls, protocol §5.3);
  `SYNC-INADEQUATE-AT-START` refuses after it (§9.1 reasons list).
* RUNNING: `execute()` invocations; boundary/group loop of §4.
* STOPPING: no new request may start (§7.3); current in-flight request completes and is recorded; then seal.
* SEALING: `write_run` (staging); VERIFYING: `load_run` + `audit_run` on staging (§5.4); COMMITTING: CP1–CP3 (§7.5).
* COMMITTED: terminal; `observe()` resolves T6/T1.

2.4 A run attempt produces exactly one terminal state from §9.3 (invariant M): successfully published and verified,
quarantined (`<run_id>.unverified/`), or entirely absent — never a partial run directory. Strict success predicate:

```
S ⟺ phase = COMMITTED
  ∧ receipt published AND parses AND its manifest_sha256 equals the pin of manifest.json
  ∧ receipt_pin supplied AND sha256(receipt bytes) = receipt_pin (V16-01: T1/T6 never accept an unauthenticated receipt)
  ∧ observe() re-verification passes (load_run with pin + audit_run with wrapper_count from an independent egress
    source — live: transport.sent; observe(): egress_count, else the authenticated receipt.wrapper_count; never
    structurally derived, V15-03)
  ∧ PACE-5 (g) egress equality holds: jsonl_count = wrapper_count = manifest_count
  ∧ PLAN_TERMINAL: every planned boundary is recorded or carries a verified skip reason (boundary_skips /
    group-level MISSED-WINDOW evidence), and the event log ends with TIMELINE_END covering every record
```

## 3. Normative `execute()` loop, single-read admission, incident ladder

3.1.0 **Admission predicate (normative).** A request may start at `now` iff all hold, evaluated from ONE clock read `now`:

``(now ≥ pacer.earliest_start_ns())`` (records-only: `max(last.end_ns, last.start_ns + spacing, release_ns(...))`),
and — only for the FIRST request of a group — ``now ≥ ceil_ns(D(target_X, now))``,
and no STOPPING/EMERGENCY flag is pending (§7.3), and the pacer is not aborted, and the transport is not disabled.

3.1.1 **Dynamic target re-evaluation (V13-05).** `D(X) = X − theta_lo(now)` (protocol §5.2) is a moving deadline:
`theta_lo` decreases through the `delta·(now − a_j)` widening, so `D` moves **later** while the runner waits, and the
retained sample set is re-evaluated at each read (600 s retention by completion time, 60 s fallback). The target SHALL be
re-computed from the estimator **at every admission read**; a target computed once and passed as a static instant is
non-normative (it can start a request up to `earliest − target` stale). This is the fixed-point wake loop of GV-6/GV-7:
sleep to `ceil(D(now))`, wake, re-read, recompute, repeat, until `now ≥ ceil(D(now))`; with GV-6's single sample the loop
wakes at 300,000 ms and 300,030 ms and starts at exactly `300,030,003,001 ns`. A target applies ONLY to the first request of
a group (S1 of g0…ref, resync's first call, sync's first call, and the OBS-01 probe pacing profile has no server target);
group-internal requests pass `target = None` and start at `earliest` (PACE-6).

3.1.2 **Single-read commit (V13-05).** Each admission iteration performs exactly one `clock.now_ns()` read. That read is used
simultaneously to test the predicate and — when the predicate passes — to become `start_ns`, recorded verbatim in the
record. There is no second read between decision and record; a design that reads the clock, decides, and reads again for the
timestamp is non-normative (the two reads could straddle a watchdog cancellation or an interrupt flag set).

3.1.3 **Normative loop.** This is the Step-2 `execute()`; it runs entirely under the pacer's single-flight discipline
(`_flight.acquire(blocking=False)` → `ConcurrentExecution` changes nothing). The dynamic target is supplied as a callable
`target_fn(now_ns) -> Fraction | None` (Step-2 extension of `Pacer.execute`; the static `target_ns` path remains for
requests without an estimator target). `ceil_ns(x) = -(-x // 1)` for `Fraction` `x`.

```
function EXECUTE(spec, target_fn | None) -> RequestRecord:            # normative, V13-01/V13-05
    if not flight_lock.acquire(blocking=False):
        raise ConcurrentExecution("another request is in flight")     # nothing sent, nothing recorded
    try:
        return _EXECUTE_UNDER_LOCK(spec, target_fn)
    finally:
        flight_lock.release()

function _EXECUTE_UNDER_LOCK(spec, target_fn) -> RequestRecord:
    if pacer.abort_reason is not None:            raise PacerAborted(pacer.abort_reason)
    if transport.disabled_reason is not None:     raise TransportDisabled(transport.disabled_reason)
    validate_spec(spec)                           # allow-list refusal BEFORE any socket (specs.validate_spec)
    loop:                                         # ---- single-read admission ----
        if stop_flag.pending or interrupt_flag.pending:               # §7.3: no start mid-interrupt
            raise InterruptedBeforeStart                               # handled by STOPPING, no record
        now = clock.now_ns()                       # THE one read of this iteration
        earliest = pacer.earliest_start_ns()       # derived from records only; no clock read
        deadline = 0
        if target_fn is not None:
            deadline = ceil_ns(target_fn(now))     # D(X, now) RE-EVALUATED at every wake (3.1.1)
        start_at = max(earliest, deadline)
        if now >= start_at:
            start_ns = now                         # predicate read == recorded timestamp (3.1.2)
            break
        wait = min(start_at - now, INTERRUPT_POLL_NS)      # INTERRUPT_POLL_NS = 100 ms (§7.3)
        clock.sleep_until_ns(now + wait)          # V14-04: Clock exposes sleep_until_ns(target_ns) — an ABSOLUTE
                                                  # monotonic instant (clock.py), never a duration; `wait` is a
                                                  # duration, so the target is now + wait; may wake early/late,
                                                  # and the loop re-reads
    if stop_flag.pending or interrupt_flag.pending:         # re-check between predicate pass and dispatch;
        raise InterruptedBeforeStart                       # a signal after this line lands mid-flight (§7.3)
    # ---- dispatch (PACE-8: absolute deadline anchored at start_ns) ----
    cancel_failed = False
    try:
        result = transport.send(spec, deadline_at_ns = start_ns + DEADLINE_NS,     # DEADLINE_NS = 17 s
                                budget = session_budget)             # chunk path, §6.4
    except CancellationFailed:
        cancel_failed, result = True, TransportResult(None, CANCEL_FAILED)
    except BaseException:
        pacer.abort("TRANSPORT-EXCEPTION")         # fail closed; no record for an exception that produced no result
        raise
    end_ns = clock.now_ns()                        # orchestrator read AFTER completion (record field, audit (a)/(b))
    memory_abort = (result.error == INCIDENT_MEMORY)
    body = b"" if memory_abort else result.body    # over-budget bytes are never retained (§6.3)
    record = RequestRecord(seq = len(pacer.records) + 1, role = spec.role, path = spec.path,
                           start_ns = start_ns, end_ns = end_ns, status = result.status,
                           error = (INCIDENT_MEMORY if memory_abort else result.error),
                           group_name = spec.group_name, group_kind = spec.group_kind,
                           boundary_ms = spec.boundary_ms, body = body, headers = tuple(sorted(result.headers.items())))
    pacer.records.append(record)                   # appended BEFORE the ladder; egress counts stay equal (PACE-5 (g))
    if not memory_abort:
        session_budget.commit(len(result.body))    # retained_total += len(body); single owner (§6.2)
    return APPLY_LADDER(record, cancel_failed)     # §3.3; raises on abort, else returns the record
```

3.1.4 Static-path equivalence note (non-normative, for reviewers of the Step-1 diff): with `target_fn = None` and a static
`target_ns`, the loop reduces to `Pacer._execute`'s `start_at = max(earliest_start_ns(), target_ns or 0)` sleep; the only
behavioural change is that `start_ns` comes from the predicate read instead of a separate post-loop read, which is
observationally identical for a monotonic clock when no wake-lateness diagnostic is attached (V1 judges lateness from the
record, never from the read pattern).

3.2 **Wakes, lateness, no-catch-up.** The admission loop never advances `start_at` downward and never shortens a gap: a late
wake only re-reads and, if `now ≥ start_at` already, starts (recorded late; judged solely by V1 from the measured `S1`, and
diagnosed when the wake exceeded its deadline by > 500 ms — protocol §5.3). `EARLY` is impossible by construction: `start_ns`
is only assigned when `now ≥ start_at` on the same read.

3.3 **Incident evaluation ladder — exact branch-for-branch order of `audit.abort_condition_seq` (V13-01).**

The audit derives the abort position from the record stream itself, in this exact order (verbatim from
`tools/obs/audit.py`, lines 70–86):

```
def abort_condition_seq(records):            # audit; quoted for line-by-line comparison
    streak = 0
    for record in records:
        if record.status is not None and record.status != 200:
            return record.seq                                  # B1: non-200
        if record.error == CANCEL_FAILED:
            return record.seq                                  # B2: failed cancellation
        if record.status is None:
            streak += 1
            if streak >= MAX_CONSECUTIVE_NO_RESPONSE:          # 3
                return record.seq                              # B3: three consecutive no-response
        else:
            streak = 0                                         # B4: HTTP 200 resets the streak
    return None
```

The runner-side ladder SHALL evaluate the record just appended in **that same order**, with `streak` being the pacer's
persistent `_no_response_streak` counter:

```
function APPLY_LADDER(record, cancel_failed) -> RequestRecord:     # normative, branch order = audit
    # B1 — non-200 first, exactly as the audit checks it
    if record.status is not None and record.status != 200:
        pacer.abort(f"HTTP-{record.status}")               # transport already self-disabled on this status
        raise NonOkResponse(record)                        # ABORT (INCIDENT): protocol §6 incident row
    # B2 — failed cancellation
    if record.error == CANCEL_FAILED:                      # (or the caught CancellationFailed path: same record shape)
        pacer.abort("INCIDENT-CANCEL")
        raise CancellationFailed("request still running after cancellation allowance")
    # B3 — no-response streak
    if record.status is None:
        pacer._no_response_streak += 1
        if pacer._no_response_streak >= MAX_CONSECUTIVE_NO_RESPONSE:      # 3
            pacer.abort("INCIDENT-NETWORK")
            raise NetworkIncident("3 consecutive requests without an HTTP response")
        return record                                       # streak persists; no abort yet
    # B4 — HTTP 200
    pacer._no_response_streak = 0
    # B5/B6 — runner incidents; NOT part of abort_condition_seq (see proof below)
    if record.error == INCIDENT_MEMORY:
        pacer.abort("INCIDENT-MEMORY");  raise MemoryIncident(record)
    if runner_response_validation_failed(record):           # N9: non-JSON, wrong shape, wrong open time, weight guard
        pacer.abort("INCIDENT-RESPONSE"); raise ResponseIncident(record)
    return record
```

3.3.1 **Equivalence with the Step-1 implementation (required proof).** `Pacer._execute` checks `cancel_failed` before B1.
The orders are observationally equivalent because the shapes are disjoint: the transport constructs
`TransportResult(None, CANCEL_FAILED)` only (status is `None` on that path), so no record can satisfy both B1 and B2, and
both orders therefore return/abort at the same `seq`. The audit's order above is the normative one; the implementation's
ordering is permitted only because of this disjointness, which a test MUST pin (§11, G-V13-01).

3.3.2 **Abort position convention.** `pacer.abort(reason)` sets `abort_seq = len(pacer.records)` on first call (existing
behaviour). Ladder aborts (B1/B2/B3) happen right after the record append, so `abort_seq = len(records) = derived`;
runner aborts (B5/B6 and pre-record refusals of §5.2/§6) have `derived = None` and `abort_seq = len(records)`.
`audit_pace` accepts exactly these two shapes: `derived is not None ⇒ abort_seq == derived`; `derived is None ∧
abort_seq is not None ⇒ abort_seq == len(records)`. Self-verification (§5.4) passes `abort_seq = pacer.abort_seq`;
`observe()` passes `abort_seq` re-derived from the persisted records via `abort_condition_seq` (the live pacer no longer
exists; the end-at-abort invariant `len(records) ≤ derived` is enforced by check (a) regardless).

3.3.3 **Memory/response compatibility proof (V13-01, why B5/B6 must sit after B4).** `abort_condition_seq` sees only
`status`/`error`. A memory-abort record has `status = 200`, `error = "INCIDENT-MEMORY"` → falls to B4 (streak reset),
`derived = None`; with `abort_seq = len(records)` check (a) accepts, and `_audit_groups` accepts the stream because
`aborted = abort_seq is not None` and the abort sits on the last record (`aborted and last_group[-1].seq == last_record_seq`
justifies the missing trailing groups). No branch of the audit ladder may be reordered or extended for memory — a memory
condition inside B3 (v1.3's error) would make the runner abort at a `seq` the audit does not derive, failing
`abort_seq != derived`.

3.3.4 **Streak accounting on non-record events.** An `UnsafeRequest` refusal or a `TransportDisabled` raise occurs before
any record: no record, no streak change; the runner aborts (`abort_seq = len(records)`, `derived = None`) — the only legal
shape for a pre-record abort. A watchdog DEADLINE (17 s) and socket TIMEOUT produce `status = None` records → B3 streak;
they are the protocol's "no HTTP response" family (protocol §6), which includes `DEADLINE`, `TIMEOUT`, `CONNECT_ERROR`
harness codes alike.

3.4 **`start_ns` invariants S1–S6 (record-authoritative).**
S1: `start_ns` is sampled on the orchestrator thread only (§2.1).
S2: `start_ns` is the single predicate read of §3.1.2 (never re-read afterwards).
S3: `start_ns ≥ max(earliest_start_ns(), ceil_ns(D(X, start_ns)))` whenever a target applies — the definition of admission.
S4: `deadline_at_ns = start_ns + DEADLINE_NS`; time before the transport is reached counts against it (Step-1 rule), so
`end_ns − start_ns` is the audited duration (PACE-5 (e): ≤ 18 s; DEADLINE records ∈ [17 s, 18 s]; `CANCEL_FAILED` ∈ [17 s, 19 s]).
S5: `end_ns ≥ start_ns` and starts are non-decreasing in `seq` (audit (a)); both are read on the orchestrator thread.
S6: `pre_write_ns`, if the transport ever emits it for diagnostics, is worker-observational ONLY and MUST be persisted in
the receipt (`obs-outer-index/1`), never in `records.jsonl` — the record schema is frozen at its exact 12 keys
(`_RECORD_KEYS` in `runstore.py`); adding a field is forbidden.

## 4. PACE-7 group admission — single read, event-log binding

4.1 **When:** before the first request of every boundary group (`g0…ref`), after the boundary's `resync` group has
completed — i.e. at every group boundary while the plan proceeds — using the estimator state built from recorded `/time`
bodies. Admission is evaluated **once per group**; on the first skip of a boundary, the rest of that boundary is not sent
(a single verified decision covers it — audit behaviour of `_audit_groups`).

4.2 **Normative pseudocode (single-read admission, V13-05):**

```
function ADMIT_OR_SKIP(boundary_ms, group_name, offset_ms, tol_ms) -> Decision:
    decided_at_ns = clock.now_ns()                                   # THE one read; ≥ prev record's end (program order)
    m_e_ns = max(decided_at_ns, pacer.earliest_start_ns())           # derived; no second clock read
    decision = decide_admission(estimator, m_e_ns = m_e_ns, boundary_ms = boundary_ms,
                                offset_ms = offset_ms, tol_ms = tol_ms, decided_at_ns = decided_at_ns)
        # skip iff m_e + theta_lo > T + o + tol (STRICT; equality ADMITTED; theta_hi never decides) — admission.py
        # limit_ns = (boundary_ms + offset_ms + tol_ms) * 1e6; windows: g0 (0,2500) g1 (2000,2500) g2 (10000,2500)
        #            g3 (60000,5000) ref (180000,5000) ms  (GROUP_WINDOWS_MS, audit.py)
    if decision.admitted:
        receipt.admitted_decisions.append(decision)      # protocol PACE-7 evidence — outer index ONLY (§4.4)
        return ADMIT
    events.append_decision(boundary_ms = boundary_ms, group_name = group_name,
                           decided_at_ns = decided_at_ns, m_e_ns = m_e_ns, records = pacer.records)
        # IMMEDIATELY after the preceding request completed: records_before == previous seq (audit requires it)
    skips[(boundary_ms, group_name)] = decision          # passed to audit_run as {boundary: first_skipped_group}
    return SKIP                                         # boundary terminated: no later group of this boundary is sent
```

Invariants: `decided_at_ns ≤ m_e_ns` (guaranteed by `max`); `m_e_ns = max(decided_at_ns, earliest)` **exactly** (the audit
rejects `m_e` inflated or deflated — `m_e > expected` or `m_e < expected` both fail `validate_decision_evidence`); the read
precedes the event append in program order; a `decided_at_ns` earlier than the preceding record's `end_ns` is impossible
without a clock anomaly and fails the audit.

4.3 **Event log discipline.** DECISION events are appended **only for skips** (an admitted decision logged as an event is
"unexplained" and fails check (a) — P-02). After the last record of the run, the runner appends exactly one
`TIMELINE_END(timeline_end_ns = last clock read ≥ records[-1].end_ns, records = pacer.records)`; nothing may be appended
after it. `writer.events` and `writer.head_digest` are handed to `write_run`, which persists them and the manifest head;
the head digest is bound to the out-of-band pin (§10).

4.4 **Admitted vs skipped evidence split (concrete).** Protocol PACE-7 requires "the decision is recorded (with m_e,
theta_lo, theta_hi, T+o+tol)" for every group; the audit accepts decision objects only as skip evidence (each DECISION
event must match an audited skip). Therefore: skipped decisions live in the hash-chained event log (audited, check (f));
admitted decisions live in `obs-outer-index/1` (`admitted_decisions[]`, exact fields `boundary_ms, group_name, m_e_ns,
decided_at_ns, theta_lo, theta_hi, lower_server_ns, upper_server_ns, limit_ns, reason`) — outside the audited record/event
stream, pinned by the receipt's own no-replace publication.

4.5 Whole-boundary skips (protocol §5.3): `SYNC-SKIPPED` boundaries send nothing; the runner records them in
`boundary_skips = {boundary_ms: "SYNC-SKIPPED"}` and the boundary MUST NOT appear in the records. Three consecutive
`SYNC-SKIPPED`/`MISSED-WINDOW` boundaries stop the session as `INCONCLUSIVE-TIMING` (seal and commit normally — T6 with
that outcome, §9.3). `expected_boundaries` (the plan's boundary list) is passed to `audit_run`; an expected boundary with
neither records nor a skip reason fails check (f).

## 5. Staging, directory-FD publication, self-verification

5.1 **Seal sequence (SEALING) — reconciled with the actual Step-1 code (V14-01, V14-02).** The Step-1 `write_run`
(runstore.py:221, byte-identical between `f337862e…` and `dbfe53c…`) today: (a) opens each file **by path** with mode
`"xb"` (no directory-fd anchoring), (b) performs **no `fsync` at all** — neither file nor directory — so K2–K7 durability
is not provided by it, and (c) materializes every record's base64 string and the entire joined file in memory
(`_lines([record_to_json(r) for r in records])`, runstore.py:229/217) — worst case ≥ 2 × 4/3 × `SESSION_BODY_BUDGET_BYTES`
≈ 139.8 MB, an order of magnitude above the Domain B budget. v1.4 described fsync and streaming as if they already
existed; they did not. Step 2 therefore **REPLACES** `write_run` (decision **D18**): same name, same signature, same
observable contract (three files, exclusive create, byte-identical content, returns `sha256(manifest.json)`), new
implementation per §5.1.1. The path-based whole-file body survives only as the test-side reference serializer for
G-V14-02 byte-equality; it MUST NOT seal live evidence. The manifest carries the exact 8 keys: `format, record_count,
records_file_sha256, records_digest, event_count, events_file_sha256, event_log_head, manifest_digest`. Before entering
the publication sequence, the runner emits the pin out-of-band (stdout flush + receipt draft), because after CP1 the
staging directory no longer exists to re-derive anything from. Any `OSError` (ENOSPC/EIO) from a write or an `fsync`
aborts the seal → quarantine (§5.5) → T5.

5.1.1 **Normative writer — descriptor-relative, streaming, fsync-safe (V14-01/V14-02; covers K2–K7).**

```
function WRITE_RUN(pfd, staging_name, records, events) -> str:   # normative; the runner's seal entry (replaces Step-1 write_run)
    head = events[-1].entry_hash if events else GENESIS
    verify_event_log(list(events), head, records)                # unchanged pre-check (runstore.py:226)
    sfd = os.open(staging_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd = pfd)  # mkdir'ed by the
                                                  # runner (K1); its CREATION identity (V17-02) is captured by the
                                                  # runner immediately after mkdir through this same descriptor:
                                                  #   st_stage = os.fstat(sfd)   → passed to CP1's publish_dir as
                                                  #   expect = st_stage, identity_source = CREATION (never re-derived
                                                  #   from the path). WRITE_RUN's signature and return value are
                                                  #   unchanged (§5.1.1 contract), so the identity travels beside the
                                                  #   pin in runner state, never inside the frozen manifest.
    try:
        r_fd = open_excl(RECORDS_FILE, sfd)                      # O_WRONLY|O_CREAT|O_EXCL, 0o644, dir_fd = sfd
        f_sha, d_sha = stream_records(r_fd, records)             # per-record bytes; BOTH hashers fed from the same chunks
        os.fsync(r_fd); os.close(r_fd)                           # (F1) records content durable  → K2/K3
        e_fd = open_excl(EVENTS_FILE, sfd)
        e_sha = stream_events(e_fd, events)                      # same discipline; event lines ≤ ~800 B, still streamed
        os.fsync(e_fd); os.close(e_fd)                           # (F2) events content durable   → K4
        fields = {format, record_count, records_file_sha256: f_sha, records_digest: d_sha,
                  event_count, events_file_sha256: e_sha, event_log_head: head}
        fields["manifest_digest"] = _manifest_self_digest(fields)
        m_fd = open_excl(MANIFEST_FILE, sfd)
        write_all(m_fd, canonical(fields) + "\n")                # manifest ≤ 1 KiB; written LAST (K5)
        os.fsync(m_fd); os.close(m_fd)                           # (F3) manifest content durable → K5
        os.fsync(sfd); os.close(sfd)                             # (F4) the three NAMES durable inside staging → K7 premise
    except (OSError, FileExistsError) as exc:
        raise ManifestError(...) from exc                        # → seal abort → quarantine (§5.5) → T5
    return sha256(manifest bytes)                                # the out-of-band pin (§10.1)

record_meta_json(r):                     # V15-01: METADATA-ONLY serializer (*runner*; never reads r.body)
    return {"seq": r.seq, "role": r.role, "path": r.path, "start_ns": r.start_ns, "end_ns": r.end_ns,
            "status": r.status, "error": r.error, "group_name": r.group_name, "group_kind": r.group_kind,
            "boundary_ms": r.boundary_ms, "headers": [list(h) for h in r.headers]}
        # exactly record_to_json(r) minus the "body_b64" entry — same key set, same value shapes — so canonical(lo)
        # and canonical(hi) below reconstruct _canonical(record_to_json(r)) byte for byte. record_to_json(r) itself
        # is BANNED here: it base64-encodes r.body (runstore.py:206–209) — a <= 5,592,408 B string, twice per record.

stream_records(fd, records):                # ONE record in flight; never a whole line, never the whole file
    file_sha = sha256(); rec_sha = sha256()
    for r in records:
        rec_sha.update(records_digest_line(r))    # eventlog.py:54–56 line format; bytes(r.body) is r.body (identity,
                                                  # probe-verified) — the body is hashed IN PLACE, never copied
        meta = record_meta_json(r)                # <= ~2.1 KiB canonical; V15-01: no body content is read here
        lo = {k: v for k, v in meta.items() if k < "body_b64"}   # EMPTY: under _RECORD_KEYS "body_b64" sorts FIRST
        hi = {k: v for k, v in meta.items() if k > "body_b64"}   # the other 11 keys, canonical order
        head = canonical(lo)[:-1].encode() + (b"," if lo else b"")   # drop '}'; the comma exists ONLY when lo does
        piece = head + b'"body_b64":"'          # v1.5 wrote {,"body_b64":" for empty lo — invalid JSON (V15-01)
        write_all(fd, piece); file_sha.update(piece)             # write_all = loop over os.write for partial writes
        for off in range(0, len(r.body), 49_152):                # 49_152 = 3 × 16_384: base64-aligned, no mid-line padding
            chunk = base64.b64encode(r.body[off : off + 49_152]) # slice 49,152 + chunk <= 65,536 + encoder scratch 32,768
            write_all(fd, chunk); file_sha.update(chunk)
            del chunk                         # release BEFORE the next slice: retaining chunks peaks at 5,656,645 B
        tail = (b'"' + b"," + canonical(hi)[1:].encode()) if hi else b'"' + b"}"   # close value + ',' + tail keys (drop '{')
        tail += b"\n"                        # JSONL terminator (v1.5 never wrote it — byte equality requires it)
        write_all(fd, tail); file_sha.update(tail)
    return file_sha.hexdigest(), rec_sha.hexdigest()
```

All normative: (i) **byte equality** — the output equals `_lines([record_to_json(r) for r in records])` record for
record (the framing reconstructs `_canonical`'s sort_keys order exactly; under the frozen `_RECORD_KEYS`, `body_b64`
sorts FIRST — "body_b64" < "boundary_ms" — so `lo` is empty and the head is exactly `{`; v1.5's claim that `body_b64`
sat between `boundary_ms` and `end_ns`, its `{"`/`","` joins, and its missing line terminator were all wrong and are
replaced above), so pins, digests and Step-1's serializer stay interchangeable — G-V14-02/G-V15-01 pin it on
randomized records incl. a 4 MiB body, unicode and escapes (probe-verified byte-equality, file sha and
`records_digest` all exact); (ii) **one record in flight, metadata only** — `record_to_json(r)` is NEVER called in
this path (it would allocate the full ≤ 5,592,408 B base64 string twice per record); the largest allocations are one
48 KiB slice + one ≤ 64 KiB base64 chunk + the encoder's 32,768 B working buffer + ≤ 4,096 B of digest line, head/tail
fragments and framing (seal peak ≤ 151,552 B, measured 148,113 B, §6.5 phase 2), and `chunk` is released before the
next slice; (iii) **fsync order F1→F4** — a crash at any point leaves exactly the K2–K7 state; (iv) `records_digest`
and `records_file_sha256` are computed from the same bytes written, never from a re-serialization; (v) `mkdir` of
staging remains the runner's exclusive-create step (`os.mkdir(name, dir_fd=pfd)`, `EEXIST` → K1 quarantine of the stale
tree, never a merge) — `WRITE_RUN` never mkdirs.
Failure mapping: a write `OSError` → K2/K3/K4; manifest write → K5; any `fsync` failure → K6; crash after F4 → K7
(complete durable staging, no final → quarantine, D14). The Step-1 path-based `write_run(run_dir, …)` wrapper keeps its
old behavior (mkdir-if-absent + these same bytes) so Step-1's regression tests stay green; live sealing calls the
fd-based entry with the locked `pfd`.

5.1.2 **Normative reader — the versioned `obs-loader/2` contract (V15-02, V16-05, V17-01, V18-01; the fourth Step-2 extension
point, §0.2; D24/D35/D38/D39).** The Step-1 `load_run` (runstore.py:370–388) reads each file whole (`_read` →
`path.read_bytes()`, 246–250), splits it in memory (`raw.split(b"\n")`, `_jsonl` 279–286), parses every line and holds
all records: for a 50 MiB session that peaks at ≥ 139.8 MB of transient (≥ 2 × 4/3 × `SESSION_BODY_BUDGET_BYTES` of
jsonl bytes plus every parsed `body_b64` string) — an order of magnitude above the Domain B budget — and it cannot
support §6.5 phase 3's 12 MiB verification bound. Step 2 REPLACES `load_run` (decision **D24**): same name, same
keyword-only signature, same `LoadedRun`, same `ManifestError` messages, and the same accept-reject set for every input
whose lines all fit `MAX_LINE` — the differential corpus of §5.1.2.4 (G-V17-01) pins the contract against a frozen,
hash-pinned copy of the Step-1 implementation. `audit_run` (audit.py:619–631) calls `load_run` (626) and inherits it
unchanged; `load_manifest` (runstore.py:253) is unchanged — its manifest is ≤ 1 KiB by the 8-key schema (bounded full
read) and it already fails closed without a well-formed 64-hex pin (255–258, V15-04).

5.1.2.0 **Loader contract registry (V17-01).** The reader is a NAMED, VERSIONED contract, never a bundle of local
choices, so that "which loader produced this verdict" is answerable from the document alone:

```
LOADER_CONTRACT_ID         = "obs-loader/2"     # normative for Step 2 and for every later revision of this document
LOADER_CONTRACT_SUPERSEDES = "obs-loader/1"     # Step-1 `runstore.load_run` at 7b1493e: descriptive + TEST ORACLE only
```

| Contract | Implementation | Line model | Memory | Status |
|---|---|---|---|---|
| `obs-loader/1` | Step-1 `load_run`/`_jsonl`/`_read` (runstore.py:246–286, 370–388) | `raw.split(b"\n")` — a line is any byte run with NO upper bound; the whole file is materialised first | O(file size); ≥ 139.8 MB for a 50 MiB session | DESCRIPTIVE. Frozen at `7b1493e`; used ONLY as the differential oracle (§5.1.2.4); MUST NOT verify live evidence |
| `obs-loader/2` | §5.1.2.3 (`scan_structure`, `check_lines`, `parse_line`, `decode_pass`) | `f.readline(MAX_LINE + 2)` — bounded line content `≤ MAX_LINE = 5,592,920 B` | O(1) per line; ≤ 11,202,224 B per pass (§6.5 phase 3) | NORMATIVE. Supersedes /1 for all verification, sealing self-checks and `observe()` |

Rules (all normative):

* **R-1 — supersession.** `/2` is the ONLY loader any Step-2 code path may call: `write_run`'s pre-publication
  self-check (§5.4), CP1b (§7.5) and `observe()` (§9.2). It supersedes `/1`'s unconstrained string loader: a line whose
  CONTENT exceeds `MAX_LINE` is REJECTED where `/1` would have parsed it. That is the single intended acceptance change,
  and it is an explicit POLICY, not an impossibility (§5.1.2.6, V18-01): §5.1.2.1 shows the bound is a theorem for the
  records §5.1.1 writes and for nothing else. Step-1 checks no string length anywhere, so a `/1`-ACCEPTED legacy artifact
  can exceed the cap; `/2` refuses it by design, with the deterministic P-6 message and its line number.
* **R-2 — no negotiation, no fallback.** There is no runtime switch, environment variable, keyword argument, platform
  probe or `try/except ImportError` that selects `/1`. A fallback would restore the whole-file load that D30 forbids, so
  a `/2` that cannot run FAILS CLOSED: the run resolves T3/T5 exactly like any other audit failure. Verifying live
  evidence with `/1` requires a reviewed revision of this document, not a flag.
* **R-3 — version discipline.** Any future change to `/2`'s accept set, JSON dialect, message strings, precedence or
  `LoadedRun` contents MUST mint `obs-loader/3` and update this registry, §11 (G-V17-01) and §12 in the SAME reviewed
  revision, keeping the `/1` oracle pinned. Silent evolution of `/2` is forbidden (D38).
* **R-4 — the artifact binding is DERIVED, not stored.** The contract ID is not persisted: `records.jsonl`,
  `events.jsonl`, `manifest.json` and `obs-outer-index/1` all have frozen key sets (§10.3) and adding a key would break
  §10.2/G-V14-05/§9.2's strict parser. The binding is instead proved twice: (a) at import, `MAX_LINE` MUST equal the
  §5.1.2.1 derivation (assertion; a loader whose cap drifted from `MAX_BODY_BYTES` refuses to start), and (b) every
  record line written by §5.1.1 satisfies `line content ≤ MAX_LINE` by construction, so a `/2`-conforming artifact is
  always `/1`-conforming. The converse does not hold — and that single direction IS the documented divergence.
* **R-5 — code/doc identity.** G-V17-01a asserts that the `LOADER_CONTRACT_ID` constant, the literal string in this
  section and the §1.1 map agree; a mismatch fails CI, so the version cannot drift out of the review artifact.
* **R-6 — the cap is a REJECTION BOUNDARY, not a conformance claim (V18-01).** A `/1`-accepted artifact that exceeds
  `MAX_LINE` is REFUSED, never repaired: no truncation, no line splitting, no skip-and-continue, no "oversize tolerance"
  flag, no environment variable, and no attempt to stream a single line in pieces (a partial line cannot be parsed as one
  record, and the digest that authenticates the file is over the whole file, so a subset verdict could not be defended).
  §5.1.2.6 states the policy, its reachability evidence, its terminal consequences and the only legitimate route for such
  evidence — a reviewed `obs-loader/3`, never a runtime switch.

5.1.2.1 **Exact size bounds and the derived `MAX_LINE` (V17-01).**

```
MAX_BODY_BYTES          = 4,194,304 B                     # transport.py:26 — one response body, hard cap
B64_BYTES               = 4 × ⌈MAX_BODY_BYTES / 3⌉        # 4 × 1,398,102 = 5,592,408 B — the `body_b64` VALUE of a
                                                          #   maximal body (standard alphabet, no line breaks)
FRAMING_ALLOWANCE_BYTES = 512 B                           # every non-body byte of ONE record line: keys,
                                                          #   punctuation, numbers, path, headers, error, escaping
MAX_LINE                = B64_BYTES + FRAMING_ALLOWANCE_BYTES = 5,592,920 B    # line CONTENT, terminator EXCLUDED
READLINE_SLACK_BYTES    = 2 B                             # f.readline(MAX_LINE + 2)
assert MAX_LINE == 4 * ((MAX_BODY_BYTES + 2) // 3) + FRAMING_ALLOWANCE_BYTES    # import time, fail closed (R-4a)
assert READLINE_SLACK_BYTES == 2 and MAX_LINE > B64_BYTES                       # the cap can never clip a legal line
```

`FRAMING_ALLOWANCE_BYTES` is measured, not guessed: for a record with an EMPTY body, `_canonical(record_to_json(r))`
measures 348 B with the maximum legal field widths (probe framing, A.7.1) and ≤ 384 B under the widest LEGAL values (`seq` ≤ 4 digits; `role`/`path` bounded by the reviewed plan
allow-list; `group_name` ≤ 16 B; `group_kind` ≤ 8 B; `boundary_ms` ≤ 6 digits; `status` ≤ 3 digits; `error` ≤ 64 B —
the longest incident token is 16 B, `CANCEL_FAILED` is 13 B — and ≤ 2 whitelisted header pairs ≤ 144 B; the fixed
`"body_b64":""` adds 13 B and base64 needs no escaping). 512 B therefore leaves 164 B of slack (348 B measured) for header-whitelist growth without minting a new contract:
the widest legal record line is 5,592,756 B, exactly 164 B below the cap, and G-V17-01b fails if the measured framing
ever exceeds 512 B. **Two predicates, and only one of them is a theorem (V18-01).** v1.8 wrote that lines above the cap are "impossible under
the frozen schema" and "proved unreachable for schema-valid artifacts". The schema is not the question; the VALIDATORS
are, and Step-1's validators bound no string at all. The claim is therefore withdrawn and replaced by the split below.

| Predicate | Who defines it | Is `line content ≤ MAX_LINE` a theorem? | `/2` verdict |
|---|---|---|---|
| **CONFORMING** | §5.1.1's writer: `len(body) ≤ MAX_BODY_BYTES` is enforced when the record is built, `body_b64` comes from `base64.b64encode` (no line breaks), and the other 11 keys are bounded by the reviewed plan and header whitelist | YES — `len(body_b64) ≤ B64_BYTES` ⇒ `≤ MAX_LINE` by the arithmetic above, with 164 B of slack | ACCEPT |
| **LEGACY-ADMITTED** | Step-1's `load_run` accepting the bytes: `_jsonl` splits on `b"\n"` with no upper bound (runstore.py:279–286), `_req_str` accepts any string (304–308), `_record_from_json` bounds only `seq`/`start_ns`/`end_ns`/`status`/`boundary_ms` (348–357) | NO — `body_b64`, `path`, `error`, `role`, header names and values, `group_name` and `group_kind` are unbounded strings | REJECT (P-6) if any line exceeds the cap — policy §5.1.2.6 |

So the inequality is proved for what Step 2 Writes and is not proved for what Step 1 Accepted. Fixture D-18 re-proves it
on the archive that exists (every run under `evidence/`, written by the same `record_to_json` with transport-capped
bodies) — that is evidence about those bytes, never a claim about all legacy data — and D-21…D-23 construct the
counter-examples that make the reachability explicit and executable.

**The cap is INCLUSIVE and the read is EXACT.** `f.readline(MAX_LINE + 2)` returns at most `MAX_LINE + 2` bytes, so a
conforming line (content ≤ `MAX_LINE` plus its `\n`) is never split, and any read that fills the buffer without a
terminator is over-cap by construction. The four boundary cases are normative and executable (G-V17-01c):

| Case | Line content | Bytes in file | What `readline` returns | Fact the reader records | Verdict |
|---|---|---|---|---|---|
| A | 5,592,756 (the WIDEST legal record: a 4 MiB body plus 348 B of measured framing) | 5,592,757 | the whole line, ends `\n` | `len(raw) − 1 = 5,592,756 ≤ MAX_LINE` | ACCEPT |
| B | 5,592,920 (`MAX_LINE` exactly) | 5,592,921 | the whole line, ends `\n` | `len(raw) − 1 = MAX_LINE`, which is not `> MAX_LINE` | ACCEPT (cap inclusive) |
| C | 5,592,921 (`MAX_LINE + 1`) | 5,592,922 | the whole line, ends `\n` | `len(raw) − 1 > MAX_LINE` → `over_cap` | REJECT (P-6) |
| D | ≥ 5,592,922 | ≥ 5,592,923 | `MAX_LINE + 2` bytes, NO `\n` | `len(raw) > MAX_LINE`, no terminator → `over_cap` | REJECT (P-6) |

Case D also sets the FILE-level truncation fact when the over-cap line is the file's LAST line, and truncation then
wins (P-5) — the same message Step-1 gives for any unterminated file, so the two loaders still agree there.

5.1.2.2 **Error precedence (normative; V16-05's precedent, formalised by V17-01).** Step-1's `load_run` evaluates the
records statement — `_jsonl`'s truncation check, then per-line parse, then per-line key check — to COMPLETION before
mapping `_record_from_json` over it, and completes the records statement before the events statement begins
(runstore.py:375–379). The observable order is therefore the ladder below. `/2` reproduces it branch for branch; the
three `/2`-only rows (P-6, P-11 and the P-9a terminator rule) are marked, and they are the ONLY rows `/1` cannot
produce.

| # | Stage (evaluation order) | Trigger | Message (verbatim) | In `/1`? |
|---|---|---|---|---|
| P-0 | manifest | any `load_manifest` failure (pin missing/malformed, digest, key set, format, field types, self-digest) | unchanged from Step-1 (runstore.py:253–258) | yes |
| P-1 | records read | `OSError` opening/reading `records.jsonl` | `records.jsonl is missing or unreadable: records.jsonl` | yes |
| P-2 | events read | same for `events.jsonl`, evaluated AFTER the records read (`records_raw, events_raw = _read(...), _read(...)`, 375) | same shape with `events.jsonl` | yes |
| P-3 | records digest | `sha256(all bytes)` ≠ `manifest.records_file_sha256` | `records.jsonl does not match the manifest digest (altered or substituted)` | yes |
| P-4 | events digest | same for events | `events.jsonl does not match the manifest digest (altered or substituted log)` | yes |
| P-5 | records truncation | file non-empty ∧ its FINAL byte ≠ `\n` | `records.jsonl is truncated (no final newline)` | yes |
| P-6 | records cap | the FIRST line whose content exceeds `MAX_LINE`; its line number is reported | `records.jsonl line {n} exceeds the maximum line length` | **/2 only** |
| P-7 | records line structure | per line ascending; within one line the JSON parse precedes the key-set check; the FIRST offending line wins | `records.jsonl line {n} is not valid JSON: {exc}` ∨ `duplicate JSON key {k!r}` ∨ `records.jsonl line {n}: {c} is not allowed` ∨ `records.jsonl line {n}: unexpected or missing keys` | yes |
| P-8 | records decode + fields | ALL records, line order, `body_b64` decoded FIRST within each record | `records.jsonl line {n}: invalid body: …`, then every `_req_*` message (291–346, 348–357) | yes |
| P-9 | events truncation | as P-5 for `events.jsonl` | `events.jsonl is truncated (no final newline)` | yes |
| P-10 | events cap | as P-6 | `events.jsonl line {n} exceeds the maximum line length` | **/2 only** |
| P-11 | events line structure | as P-7 | as P-7 with `events.jsonl` | yes |
| P-12 | events decode + fields | as P-8 (`_event_from_json`) | as P-8 with `events.jsonl` | yes |
| P-13 | count | `len(records) ≠ manifest.record_count ∨ len(events) ≠ manifest.event_count` (386–387) | `record or event count does not match the manifest` | yes |

Read the ladder exactly as Step-1 does, in three ways that a naive reading gets wrong:

* **Line order dominates; JSON-before-keys is only INTRA-line.** A bad key set on line 3 is reported before a JSON
  error on line 5 (and before a bad body on line 5 — v1.6's interleaving defect), while a JSON error on line 1 is
  reported before a key-set error on line 3. `/2` reproduces this by keeping the FIRST structure error in one pass.
* **File-level facts precede every parse error** — exactly as Step-1 puts the truncation test before its parse loop.
  The cap (P-6/P-10) joins truncation in that pre-parse slot, so in a file that is both over-cap at line 9 and
  malformed at line 3, `/2` reports the CAP error (line 9) and `/1` reports the line-3 error. That is a precedence
  divergence co-extensive with the acceptance divergence, it is stated here rather than hidden, and the corpus asserts
  it explicitly (D-20).
* **Digests precede file-level facts, which precede parsing.** A digest mismatch with a malformed line 1 is P-3, not
  P-7; an events digest mismatch with a malformed records line is P-7, not P-4 (the records statement completes first).

**P-9a — the terminator rule (V17-01 correctness fix).** `/2` parses the line CONTENT, i.e. `raw[:-1]` when `raw` ends
with `\n`, and NEVER `raw`. Step-1 splits on `b"\n"`, so its `_parse_json` has never seen a terminator, and passing one
through changes JSON error POSITIONS: `{"a":` reports `Expecting value: line 1 column 6 (char 5)` while `{"a":\n`
reports `Expecting value: line 2 column 1 (char 6)` — the same bytes would therefore produce a different message under
`/2` than under `/1`, breaking the exact-message contract. v1.7's pseudocode parsed `raw` and had precisely this drift;
`parse_line(line_content(raw), what)` with `line_content(raw) = raw[:-1] if raw.endswith(b"\n") else raw` is now
normative, and fixture D-07 pins it (D39).

5.1.2.3 **Normative implementation (a v1.8 restatement of v1.7's five stages with the cap and terminator rules made
explicit).**

```
function LOAD_RUN(run_dir, *, pinned_manifest_sha256) -> LoadedRun:      # obs-loader/2; REPLACES Step-1 load_run
    manifest = load_manifest(run_dir/manifest.json, pinned_sha256 = pinned_manifest_sha256)   # P-0: unchanged; V15-04
    rec = scan_structure(records.jsonl, _RECORD_KEYS)   # P-1: read OSError (verbatim) + sha256 over ALL bytes + line facts
    ev  = scan_structure(events.jsonl,  _EVENT_KEYS)    # P-2: read OSError second, matching Step-1's read order
    if rec.hex != manifest.records_file_sha256:         # P-3: digests BEFORE any parse — outside the net, as Step-1
        raise ManifestError("records.jsonl does not match the manifest digest (altered or substituted)")
    if ev.hex != manifest.events_file_sha256:           # P-4:
        raise ManifestError("events.jsonl does not match the manifest digest (altered or substituted log)")
    try:                                                # Step-1's normalization net span (381–385), verbatim types:
        check_lines(rec, "records.jsonl")               #   P-5 truncation, THEN P-6 cap (file-level, pre-parse)
        if rec.struct_err is not None: raise rec.struct_err        # P-7: first offending record line
        records = decode_pass(records.jsonl, _RECORD_KEYS, rec.hex)  # P-8: body decode + fields for ALL records
        check_lines(ev, "events.jsonl")                 # P-9/P-10: events file-level facts only AFTER records decode
        if ev.struct_err is not None: raise ev.struct_err          # P-11
        events = decode_pass(events.jsonl, _EVENT_KEYS, ev.hex)     # P-12
        if len(records) != manifest.record_count or len(events) != manifest.event_count:
            raise ManifestError("record or event count does not match the manifest")   # P-13: verbatim (386–387)
    except ManifestError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ManifestError(f"persisted run artifact is malformed: {exc!r}") from exc   # verbatim (384–385)
    return LoadedRun(tuple(records), tuple(events), manifest)

scan_structure(path, keys) -> Scan2:       # *runner*: ONE bounded read — hash + line facts + FIRST structure error
    h = sha256(); n = 0; over_cap = None; struct_err = None; last = b""
    with open(path, "rb") as f:             # OSError → verbatim "{what} is missing or unreadable: …" (P-1/P-2)
        while True:
            raw = f.readline(MAX_LINE + 2)  # CAP by API: ≤ MAX_LINE + 2 bytes per read — bounded by construction (§5.1.2.1)
            if raw == b"": break
            n += 1; h.update(raw)           # hash the FILE bytes, terminator INCLUDED → records_file_sha256
            last = raw[-1:]
            if raw.endswith(b"\n"):
                content = raw[:-1]                                       # P-9a: the CONTENT, never `raw`
                if len(content) > MAX_LINE and over_cap is None: over_cap = n          # case C
            else:
                content = raw
                if len(raw) > MAX_LINE and over_cap is None: over_cap = n              # case D (capped read)
            if struct_err is None:          # parse structure ONLY until the first error; afterwards just hash
                try:
                    obj = parse_line(content, f"{path.name} line {n}")   # Step-1 JSON dialect (below)
                except ManifestError as exc:
                    struct_err = exc        # DEFERRED: P-3…P-6 must run first, exactly as Step-1 defers digests
                else:
                    if not isinstance(obj, dict) or set(obj) != keys:
                        struct_err = ManifestError(f"{path.name} line {n}: unexpected or missing keys")  # verbatim 284
                    del obj                 # DISCARD — no body decoded, nothing retained: O(1) memory per line
            del raw, content
    return Scan2(hex = h.hexdigest(), truncated = n > 0 and last != b"\n",
                 over_cap = over_cap, struct_err = struct_err)

check_lines(scan, what):                    # P-5/P-6 (and P-9/P-10): file-level facts, in Step-1's truncation-first slot
    if scan.truncated: raise ManifestError(f"{what} is truncated (no final newline)")                # verbatim 280–281
    if scan.over_cap:  raise ManifestError(f"{what} line {scan.over_cap} exceeds the maximum line length")   # /2 only
    # Truncation outranks the cap: it is the same defect Step-1 reports first (its `_jsonl` tests the final byte before
    # parsing anything). The cap outranks EVERY parse error: both are pre-parse file facts. Both are subordinate to
    # P-3/P-4, which Step-1 also evaluates first.

parse_line(content, what) -> dict:          # Step-1 `_parse_json` dialect (runstore.py:194–201), memory-ordered
    try:
        text = content.decode("utf-8"); del content  # the ONLY deviation from calling `_parse_json` verbatim: release
        return json.loads(text,             # the line bytes BEFORE parsing (holding line + text + parsed = 16,781,149 B,
              object_pairs_hook = _no_duplicate_keys,      # measured, banned by §6.5 phase 3). It changes NO
              parse_constant = lambda c: (_ for _ in ()).throw(  # observable outcome: the bytes are already copied into
                  ManifestError(f"{what}: {c} is not allowed")))  # text; G-V17-01 differential-tests both.
    except ManifestError:                   # duplicate keys / NaN / Infinity — verbatim, unwrapped (Step-1 195–196)
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{what} is not valid JSON: {exc}") from exc                   # verbatim (197–201)

decode_pass(path, keys, expected_hex) -> list:  # *runner*: SECOND read — body decode + fields; re-hashes (P-3 TOCTOU)
    out = []; h = sha256(); n = 0
    with open(path, "rb") as f:
        while True:
            raw = f.readline(MAX_LINE + 2)
            if raw == b"": break
            n += 1; h.update(raw)           # re-hash while decoding: closes the two-pass mutation window (R-2 narrowing)
            content = raw[:-1] if raw.endswith(b"\n") else raw                       # P-9a again
            if (len(content) if raw.endswith(b"\n") else len(raw)) > MAX_LINE:
                raise ManifestError(f"{path.name} line {n} exceeds the maximum line length")   # mid-read swap only
            tag = f"{path.name} line {n}"
            obj = parse_line(content, tag); del raw, content
            if not isinstance(obj, dict) or set(obj) != keys: raise ManifestError(f"{tag}: unexpected or missing keys")
            try:
                value = obj.pop("body_b64")  # removes the ≤ 5,592,408 B str from the dict FIRST (P-8 body_b64 first)
                if isinstance(value, str):
                    raw2 = value.encode("ascii"); del value  # ASCII copy, THEN release the str (encode peak 11.18 MB)
                else:
                    raw2 = _req_str(value, f"{tag} body_b64")  # always raises: verbatim message (304–307)
                body = base64.b64decode(raw2, validate=True); del raw2   # BYTES in — b64decode(str) would peak at
            except ValueError as exc:        # 15,381,335 B (banned, §6.5); ManifestError IS a ValueError (45)
                raise ManifestError(f"{tag}: invalid body: {exc}") from exc  # so _req_str errors re-wrap exactly as 352–353
            out.append(assemble_record(obj, body, tag))   # field half of _record_from_json UNCHANGED (354–357)
    if h.hexdigest() != expected_hex:
        raise ManifestError(f"{path.name} does not match the manifest digest (altered or substituted)")  # TOCTOU
    return out
```

Why each stage exists and how memory stays bounded (§6.5 phase 3): the structure stage parses one line, checks its key
set and DISCARDS the dict — a suspended generator or a retained list would keep every `body_b64` string alive (Step-1's
own 139.8 MB failure); the decode stage is the line's sole owner at every instant, with the normative release order
(decode → release → parse → release → encode → release → `b64decode(bytes)`), peaking at the same ≤ 11,202,224 B bound
(measured 11,188,520 B decode / 11,188,600 B fresh-buffer / 11,188,520 B structure, Appendix A.3). Two reads per
file (hash+structure, then decode)
≈ 3 × `records.jsonl` + 3 × `events.jsonl` ≈ 205 MB of sequential I/O for a full session — offline verification, O(1)
memory either way.

5.1.2.4 **Differential contract against `obs-loader/1` and the legacy corpus (V17-01; gate G-V17-01).** The divergence
claim in §5.1.2.0 R-1 is only meaningful if it is measured, so the acceptance change is pinned by a corpus, an oracle
and a monotonicity property.

**Oracle.** `tests/tools/obs/legacy_loader.py` is a VERBATIM copy of Step-1's `load_run`, `_jsonl`, `_read`,
`_parse_json`, `_record_from_json`, `_event_from_json`, `_req_*` and `_HEX64` at `7b1493e`, frozen and never edited; the
test asserts `sha256(legacy_loader.py) == LEGACY_ORACLE_SHA256` (a constant recorded in the test), so the oracle cannot
follow the implementation. `tests/tools/obs/test_loader_differential.py` runs BOTH loaders over every fixture and
asserts, per fixture: (1) the outcome class (ACCEPT vs `ManifestError`), (2) the EXACT message string, (3) on ACCEPT,
`tuple(records)`, `tuple(events)` and every `AuthenticatedManifest` field are equal and `records_digest` recomputes
equal, and (4) which loader rejected when both do.

**Corpus.** Fixtures are files under `tests/fixtures/loader/<id>/` together with a `manifest.json` listing each file's
sha256, the expected outcome and the expected message for each loader, produced by the deterministic (network-free)
`tests/fixtures/loader/generate.py` — so the corpus is reviewable and regenerable. D-18 runs against COPIES of archived
runs, never the evidence originals.

| ID | Fixture (constructed bytes) | `/1` | `/2` | Assertion |
|---|---|---|---|---|
| D-01 | clean run: 1,000 records, mixed bodies incl. one `MAX_BODY_BYTES` response | ACCEPT | ACCEPT | identical `LoadedRun`, manifest and digests |
| D-02 | clean minimal run: 0 records, 0 events (both files empty, manifest counts 0) | ACCEPT | ACCEPT | identical empty tuples; proves the empty-file branch (no truncation) |
| D-03 | one valid line whose content is EXACTLY `MAX_LINE` | ACCEPT | ACCEPT | case B: the cap is inclusive |
| D-04 | one valid line whose content is `MAX_LINE + 1` | ACCEPT | REJECT | `/1` accepted (asserted), `/2` raises `records.jsonl line {n} exceeds the maximum line length` — the DOCUMENTED divergence |
| D-05 | one valid line whose content is ≥ `MAX_LINE + 2` | ACCEPT | REJECT | same message, same line number (case D path) |
| D-06 | final line unterminated | REJECT | REJECT | identical `is truncated (no final newline)` |
| D-07 | `{"a":` at line 1 (valid line 2) AND at line 5 (valid lines 1–4) | REJECT | REJECT | identical message INCLUDING the `line 1 column 6 (char 5)` position — proves P-9a; mutation: parse `raw` → `line 2 column 1` → killer fails |
| D-08 | duplicate key `{"seq":1,"seq":2,…}` | REJECT | REJECT | identical `duplicate JSON key 'seq'` |
| D-09 | `NaN` in a numeric field | REJECT | REJECT | identical `…: NaN is not allowed` |
| D-10 | invalid UTF-8 (`0xFF`) inside a string | REJECT | REJECT | identical `is not valid JSON: 'utf-8' codec can't decode byte …` |
| D-11 | bad key set at line 3 + bad body at line 5 | REJECT | REJECT | identical line-3 key message (all-lines structure before ANY decode) |
| D-12 | bad body at line 1 + bad key set at line 5 | REJECT | REJECT | identical line-5 key message (v1.6's interleaving defect, still pinned) |
| D-13 | records digest mismatch + a malformed line | REJECT | REJECT | identical digest message (P-3 outranks P-7) |
| D-14 | events digest mismatch + malformed records line | REJECT | REJECT | identical records message (P-7 outranks P-4: the records statement completes first) |
| D-15 | count mismatch only | REJECT | REJECT | identical `record or event count does not match the manifest` |
| D-16 | record field invalid (`"status":"200"`) | REJECT | REJECT | identical `status must be an integer, got str` |
| D-17 | events truncated + records count mismatch | REJECT | REJECT | identical events truncation message (P-9 outranks P-13) |
| D-18 | LEGACY CORPUS: every archived run under `evidence/` (copies) plus fixtures written by Step-1's `write_run` reference serializer | ACCEPT | ACCEPT | `LoadedRun`, manifest, `records_file_sha256` and `records_digest` all equal; proves legacy records load byte-identically under `/2` |
| D-19 | DETERMINISTIC FUZZ: 2,000 seeded mutations of D-01 (single-byte flips, truncations, line duplications, inserted `\n`, oversized padding) | mixed | mixed | monotonicity: `accept(/2) ⇒ accept(/1)`; wherever BOTH reject, identical `(message, position)`; the only permitted asymmetry is a `/2`-only rejection carrying the cap message (D-04/D-05 class) |
| D-20 | over-cap line at line 9 + malformed line at line 3 | REJECT (line 3) | REJECT (cap, line 9) | asserts the STATED precedence divergence: `/2` reports P-6 and `/1` reports P-7 — documented, not accidental |
| D-21 | ONE otherwise-valid record whose `body_b64` holds 5 MiB — written by Step-1's own `write_run` — producing a line of content 6,990,684 B (1,397,764 B over the cap) | ACCEPT (asserted) | REJECT | V18-01 REACHABILITY: the frozen `/1` oracle MUST accept this fixture and `/2` MUST reject it with `records.jsonl line 1 exceeds the maximum line length`; if `/1` ever rejects the fixture the test FAILS as vacuous |
| D-22 | ONE record with a 6 MiB `error` string and an EMPTY body (line content 6,291,630 B, 698,710 B over the cap — no body bytes at all) | ACCEPT (asserted) | REJECT | the class is any unbounded string, not just `body_b64`: no body bytes are involved and the message is the same |
| D-23 | 4 MiB body at line 1 + over-cap line at line 2 | ACCEPT (asserted) | REJECT (cap, line 2) | the cap is a FILE-level pre-parse fact: P-6 outranks P-8, so no body is decoded at all |

D-21…D-23 exist because V18-01 is a REACHABILITY finding, not an arithmetic one: they are the fixtures that would have
failed had v1.8's "impossible" claim been left in place. Their `/1` column is an assertion about the ORACLE — the test
runs the frozen copy first and fails loudly if it rejects the fixture — so the rejection policy can never decay into an
untested belief that oversize legacy artifacts do not exist.

D-19's generator is a fixed `random.Random(20261105)` seeded loop, so the corpus bytes are reproducible; no fixture
requires network access, a live clock or a filesystem race. G-V17-01 fails if any fixture's recorded message changes
without a `/3` revision.

5.1.2.5 **What the divergence costs and why it is safe (normative summary).** `/2`'s accept set is a STRICT SUBSET of
`/1`'s for stable inputs. It loses exactly one class — a line whose content exceeds `MAX_LINE` — and that class is
REACHABLE for `/1`-accepted legacy evidence (§5.1.2.1, §5.1.2.6): it is refused deliberately, because accepting it would
break the phase-3 bound within 6,852 B of tolerance and the 12 MiB budget within 697,196 B (§5.1.2.6 P3), and because a
partially read line cannot be authenticated by a whole-file digest. `/2` additionally rejects mid-read mutations that
`/1` cannot observe at all (R-2). Every rejection is fail-closed and lands in the existing vocabulary — digest,
truncation, cap, structure, decode, count — so `observe()` resolves T3/T5 and a seal aborts to quarantine (§5.5) exactly
as before; no new terminal state, message family or receipt/journal field is introduced (D39/D43).

5.1.2.6 **Rejection policy for over-cap artifacts (V18-01; normative).** This subsection is the contract for the one
input class `/2` refuses and `/1` accepts. It exists because v1.8 justified the rejection with an impossibility claim
(§5.1.2.1) that the Step-1 code does not support.

**P1 — What is rejected.** A file whose line CONTENT exceeds `MAX_LINE = 5,592,920 B` — in `records.jsonl` (P-6) or
`events.jsonl` (P-10) — is rejected as a whole. "Content" means the bytes of the line with its `\n` terminator removed
(case A–D of §5.1.2.1). The rejection is a property of the artifact, not of a caller's preference, and it applies identically
to evidence produced by Step 1, by an older harness, by a third party, or by hand.

**P2 — Why the class is reachable (evidence, not assertion).** Step-1 enforces NO length bound at any layer:
`_jsonl` splits the whole file on `b"\n"` with no cap (runstore.py:279–286); `_req_str` returns any `str` unchanged
(304–308); `_req_headers` bounds neither the number of pairs nor the length of a name or value (320–331);
`_record_from_json` range-checks five integers and type-checks the rest (348–357); `record_to_json` writes whatever
`r.body` holds (206–209). The only cap in Step 1 lives in `transport.py` at FETCH time (4 MiB per response), which
constrains what Step-1's own writer could have produced in a compliant run — not what an artifact on disk may contain, and
not what a `/1`-accepting verifier will happily parse. The counter-examples are therefore constructible and are constructed:
D-21 (5 MiB body), D-22 (6 MiB `error`, empty body), D-23 (over-cap line after a maximal body). Both line lengths above were
MEASURED for this revision: the artifacts were written by Step-1's own `write_run` and then accepted by Step-1's own
`load_run` (with the manifest pin it returned), which is the shortest possible demonstration that a `/1`-admitted artifact can
exceed the cap. The corpus asserts the same for the frozen oracle, so the reachability claim is tested rather than argued.

**P3 — Why rejection, and not tolerance, is the only safe verdict.** A single line of L bytes costs at least 2L at parse
time (line bytes + decoded text, then the parsed `body_b64` string): the measured peak for L = 5,592,920 B is
11,188,520 B = 2L + 2,680 B. Two consequences follow from the constants this document already gates:
`peak₃ ≤ 11,202,224 B` permits L ≤ 5,599,772 B — **6,852 B above the cap** — and `TRANSIENT_BUDGET_BYTES = 12,582,912 B`
permits L ≤ 6,290,116 B. There is no room for "a little over": the first 6.9 KiB of tolerance would break the very bound
that G-V14-03 and G-V17-04 enforce. Two further reasons are independent of arithmetic: a whole-file digest cannot
authenticate a line that was never fully read, and a partial line is not a record, so any "best effort" reading would produce
a verdict about a file that is not the file the manifest pins.

**P4 — What rejection looks like (terminal, and already in the vocabulary).** `/2` raises
`records.jsonl line {n} exceeds the maximum line length` (or the `events.jsonl` form) naming the FIRST offending line, before
any parse error — P-6/P-10 precede P-7/P-8. Because §5.1.1's writer cannot produce such a line (CONFORMING, §5.1.2.1),
every occurrence is foreign or legacy evidence: during sealing the self-check fails and the run is quarantined before
publication (§5.4/§5.5, never a partial final); in `observe()` `load_run` fails structurally, so the resolver returns T5 when
a stale sibling or quarantine forces the conflict branch and T3 otherwise — never T4 and never T6. No receipt, no journal
entry and no terminal state is minted for this class; it reuses D24/D39 exactly.

**P5 — What is NOT permitted.** Truncating, splitting, skipping or "repairing" the offending line; an oversize-tolerance
flag, environment variable, keyword argument or lenient mode (R-2/R-6); verifying a SUBSET of the records and presenting it as
verification of the artifact; re-writing the artifact under its own name; and any fallback to `/1`, which would restore the
139.8 MB whole-file class that D30 forbids. A reviewer who wants any of those is asking for a different loader, which is
`obs-loader/3`.

**P6 — The legitimate route for oversize legacy evidence.** If such evidence must be verified, the options are (a) a reviewed
`obs-loader/3` that changes the cap AND the phase-3 bound AND `TRANSIENT_BUDGET_BYTES` together, in one revision, with a
re-measured Appendix A; or (b) an offline conversion that produces a NEW run directory with its own manifest, pin, digests and
provenance — a new evidence object that references the old one, never a reinterpretation of it. Neither is a runtime switch,
and neither is implemented by Step 2.

**P7 — Enforcement.** G-V18-01 replays D-21…D-23 in the order oracle-then-implementation, asserts ACCEPT-then-REJECT with the
exact message and line number, and asserts that no code path in the load chain can reach `/1` (AST gate, G-V17-01f). The
PROSE is gated too: this document must contain no claim that the class is impossible, and a CI grep asserts that the tokens
"impossible under the frozen schema" and "proved unreachable" do not reappear outside a quotation marked as retracted.

5.2 **Publication — exact `renameat2(RENAME_NOREPLACE)` contract (V13-02, V13-03).** This sequence publishes either a run
directory, the quarantine directory, or the receipt file; the normative unit is `publish_dir()`/`publish_file()`,
thin wrappers over `PUBLISH_COMPONENT` that supply `identity_source = CREATION` (runner-created names, `expect` mandatory)
or `OBSERVED` (quarantine moves only). On Linux,
Python 3.12 exposes **no** `os.RENAME_NOREPLACE` (verified on the target interpreter); the syscall is reached through
`ctypes`, and a missing libc symbol is a fail-closed error, never a fallback.

```
function PUBLISH_COMPONENT(pfd, src_name, dst_name, expect: Stat | None,
                           identity_source: CREATION | OBSERVED) -> Stat:            # normative (V17-02)
    # `identity_source` decides WHICH identity step 5 must prove — the distinction is the whole of V17-02:
    #   CREATION — MANDATORY for every name the RUNNER itself created and owns: the receipt temp
    #              (expect = os.fstat(tmp_fd), §5.2.4) and the staging run directory (expect = os.fstat of the
    #              O_DIRECTORY descriptor opened immediately after mkdir, §5.1.1). `expect` MUST be that creation
    #              fstat and MUST NOT be None. Step 5 proves dst == expect.
    #   OBSERVED — quarantine moves ONLY: the object being moved is a stale or foreign tree whose identity cannot be
    #              known in advance, and the outcome is T5/T3 whichever object stands there. `expect` MUST be None and
    #              step 5 proves dst == the pre-syscall st_src.
    # 0. Preconditions (both names are SINGLE components of the same locked parent):
    for name in (src_name, dst_name):
        require name not in ("", ".", "..") and "/" not in name and "\0" not in name      # component validation
    # 1. Identity of the locked descriptor vs the path (parent must not have been swapped) + boundary checks:
    st_pfd  = os.fstat(pfd)                                       # the descriptor we locked (§5.2.1)
    st_path = os.stat(RUN_ROOT, follow_symlinks=True)             # absolute path only (§5.2.5); what the path names now
    require (st_pfd.st_dev, st_pfd.st_ino) == (st_path.st_dev, st_path.st_ino)            # else abort, no publication
    require (st_pfd.st_mode & 0o022) == 0                         # RUN_ROOT not group/other-writable (§5.2.5 boundary)
    require st_pfd.st_uid == os.geteuid()                         # RUN_ROOT owned by THIS uid (V15-06, §5.2.5)
    # 2. Destination must not exist (advisory pre-check; renameat2 is the enforcement):
    try:      os.stat(dst_name, dir_fd = pfd, follow_symlinks = False); exists = True
    except FileNotFoundError: exists = False
    if exists: raise PublishConflict(dst_name)                    # → quarantine path (§5.5), never overwrite
    # 3. Source identity — PRE-SYSCALL GATE (V16-07; demoted to a GATE by V17-02):
    st_src = os.stat(src_name, dir_fd = pfd, follow_symlinks = False)
    if not (stat.S_ISDIR(st_src.st_mode) or stat.S_ISREG(st_src.st_mode)):
        raise PublishUnavailable(f"source {src_name} is neither a directory nor a regular file")
    if identity_source is CREATION:
        require expect is not None                   # a runner-created name MUST carry its creation fstat (V17-02)
        require (st_src.st_dev, st_src.st_ino) == (expect.st_dev, expect.st_ino)
            # A substitution that landed BEFORE this stat aborts here — nothing is published. This is only the OUTER
            # gate: a substitution that lands AFTER it makes st_src describe the IMPOSTOR, which is precisely the
            # state v1.7 failed to detect, so step 5's anchor is `expect` and never `st_src`.
    else:
        require expect is None
    # 4. THE SYSCALL — both directory fds anchored to the locked parent, RENAME_NOREPLACE:
    #      renameat2(int pfd, const char *src_name, int pfd, const char *dst_name, unsigned int flags)
    #      flags = RENAME_NOREPLACE = 1 (Linux <linux/fs.h>); names relative to pfd, NOT to the CWD, NOT to AT_FDCWD
    libc = ctypes.CDLL(None, use_errno = True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None: raise PublishUnavailable("libc has no renameat2")               # fail closed (§5.2.3)
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype  = ctypes.c_int
    rc = renameat2(int(pfd), os.fsencode(src_name), int(pfd), os.fsencode(dst_name), 1)
    if rc != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST: raise PublishConflict(dst_name)                      # raced despite step 2 → quarantine
        raise PublishUnavailable(f"renameat2 failed: errno {err}")     # ENOSYS/EINVAL/EOPNOTSUPP/EXDEV/EPERM: NO FALLBACK
    # 5. Post-rename identity proof — anchored on the IMMUTABLE CREATION IDENTITY (V17-02, replacing v1.7's
    #    st_src anchor). `rename` preserves (dev, ino), so equality proves the kernel moved the object we CREATED,
    #    not merely the object that happened to stand under the source name a moment before the syscall.
    #    The three windows, exhaustively (this is the argument the reviewer asked to be closed):
    #      W1 substitution before step 3        → step-3 require fails → abort, nothing published;
    #      W2 substitution in (step 3, syscall] → the impostor is renamed into place; step 5 compares it to `expect`
    #                                             → mismatch → quarantine + PublishIdentityMismatch (FATAL, D28);
    #      W3 mutation AFTER the syscall        → inode identity is already proved; in-place content change is caught
    #                                             by CP3e for the receipt (§5.2.4 step 8) and by CP1b for the run
    #                                             directory (§7.5) — never by an inode test, which cannot see content.
    #    A mismatch means the name now holds an IMPOSTOR. Its quarantine is ATTEMPTED UNCONDITIONALLY and every
    #    failure is STRICTLY FATAL: no `pass`, no swallowed branch, no fall-through — each path raises the single
    #    fatal type with its cause chained (consequences §5.2.4 / V15-05; classification limits §5.2.5):
    st_dst = os.stat(dst_name, dir_fd = pfd, follow_symlinks = False)
    anchor = expect if identity_source is CREATION else st_src
    require anchor is not None
    if (st_dst.st_dev, st_dst.st_ino) != (anchor.st_dev, anchor.st_ino) \
       or stat.S_ISDIR(st_dst.st_mode) != stat.S_ISDIR(anchor.st_mode):     # type RELATIVE to the anchor
        try:
            publish_quarantine_of(dst_name)            # renameat2(NOREPLACE) dst → <run_id>.unverified (§5.5),
                                                       # identity_source = OBSERVED (whatever stands there is moved)
        except BaseException as q_exc:                 # PublishConflict (EEXIST), PublishUnavailable, OSError, …
            raise PublishIdentityMismatch(dst_name) from q_exc # cause CHAINED; never `pass`; the runner dies HERE
        raise PublishIdentityMismatch(dst_name)        # mismatch fatal even when the quarantine succeeded
    return st_dst                                      # the PROVED destination stat (used by CP3e / CP1b bookkeeping)
```

5.2.1 **Locking and the parent fd.** `pfd = os.open(RUN_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)`
(the final component of the path MUST be a real directory, never a symlink — V14-07); then
`os.flock(pfd, os.LOCK_EX | os.LOCK_NB)` in a bounded retry loop (≤ `PUBLISH_LOCK_TIMEOUT_NS = 30 s`, else → E11 →
quarantine). The same fd provides the lock and the directory-relative base for every operation below — so "locked parent
descriptor" and "directory-fd-relative" are the same object: `os.stat(..., dir_fd=pfd)`, `os.open(..., dir_fd=pfd)`,
`os.mkdir(..., dir_fd=pfd)`, `os.fsync(pfd)`. The lock is held across rename, fsync and receipt (CP1–CP3) and released by
close/process death; a second publisher waits, then finds `EEXIST`.

5.2.2 **Anchored semantics.** Because `staging_name`/`final_name` are resolved against `pfd` (never against the CWD, never
against a re-opened path), a concurrent `chdir`, symlink swap of `RUN_ROOT`, or path re-resolution between lock acquisition
and rename cannot redirect the syscall: the kernel resolves both names from the locked directory inode. Step 2 of the
sequence re-proves that the locked inode still matches the path.

5.2.3 **No insecure fallback (normative ban).** On `ENOSYS` (kernel < 3.15), `EINVAL`/`EOPNOTSUPP` (filesystem without the
flag), `EXDEV` (different filesystems — impossible if the component check held, still fatal) or any other error, PUBLISH
SHALL raise `PublishUnavailable` and take the quarantine/abort path. The following are **banned** and MUST be asserted
against by test (G-V13-03): `os.rename(src, dst)` (silently overwrites on POSIX), `os.replace`, `shutil.move`,
`os.link(...)` + `os.unlink(...)` (non-atomic: link succeeds while the old name remains; a crash leaves both), copy+delete,
and any two-step check-then-rename without `RENAME_NOREPLACE`. The `EEXIST` errno — not a pre-check — is the authoritative
no-clobber guarantee.

5.2.4 **Receipt publication (V16-07 temporary-inode binding; strengthened by V17-02).** The receipt is published
under `identity_source = CREATION`, and the creation identity is captured from the descriptor that CREATED the temp —
never from a later path stat. The normative sequence, inside CP3 (§7.5), with the lock held:

```
1. tmp_fd = os.open(".<run_id>.receipt.tmp", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o644, dir_fd = pfd)
       # EEXIST → a stale temp from a crashed attempt: CP3 fails, NO pin is printed, the run stays T4 (§9.3)
2. write canonical receipt JSON through THAT descriptor, hashing the exact bytes as they are written:
       receipt_sha_written = sha256(all bytes written)        # ≤ RECEIPT_MAX_BYTES = 131,072 B (§6.6, §12)
3. os.fsync(tmp_fd)                                          # content durable BEFORE the identity is relied upon
4. st_tmp = os.fstat(tmp_fd)                                 # THE creation identity: (st_dev, st_ino)
       require stat.S_ISREG(st_tmp.st_mode) and st_tmp.st_nlink == 1
       # captured on the CREATION descriptor, before close: a value the attacker cannot manufacture, because only
       # the kernel can make the destination inode equal to the one this descriptor created
5. os.close(tmp_fd)                                          # the name may now be substituted or the inode unlinked;
                                                             # both are detected by steps 6–8, never assumed away
6. publish_file(pfd, ".<run_id>.receipt.tmp", "<run_id>.receipt.json",
                expect = st_tmp, identity_source = CREATION)
       # §5.2 steps 3/5: step 3 gates st_src against st_tmp BEFORE the syscall; step 5 proves
       # (st_dst.st_dev, st_dst.st_ino) == (st_tmp.st_dev, st_tmp.st_ino) AFTER it — so a substitution in the
       # residual stat→renameat2 window is caught by comparing the PUBLISHED inode to the CREATED inode (V17-02)
7. os.fsync(pfd)                                             # CP2' — the receipt's directory entry is durable
8. CP3e — CONTENT RE-PROOF of the published name (V17-02, new):
       snap = snapshot(pfd, "<run_id>.receipt.json", RECEIPT_MAX_BYTES)      # §9.2.1, the SAME helper observe() uses
       require snap is not ABSENT and snap is not FAULT
       require snap.sha256 == receipt_sha_written            # the bytes standing under the final name are OUR bytes
9. ONLY NOW print receipt_pin = snap.sha256 with a flush (§10.1(2)) and set phase = COMMITTED
```

Publication with `expect = None` is **BANNED** for the receipt (G-V16-07, restated by G-V17-02): steps 1–6 exist so that
the out-of-band `receipt_pin` always describes bytes that were (a) created by this process, (b) published by a rename
that provably moved that same inode, and (c) re-read from the published name and found byte-identical. Failure at any
step → CP3 fails, NO `receipt_pin` is printed, and the run stays **T4 (terminal, operator review; §7.5/D33)**; where a
foreign receipt already stands under the final name, `observe()`'s mandatory `receipt_pin` can never match it → **T3**.
T6 therefore requires an authenticated publication of THIS process's bytes, not merely the existence of a
plausible-looking receipt. A crash before step 6 leaves only the temp name (ignored by the resolver → T4); a crash
between 6 and 9 leaves a complete, correct receipt under the final name but no pin → T3 by the mandatory-pin rule
(§9.2, D31). Torn receipts under the final name are impossible by construction.

Steps 6–8 are the answer to V17-02's exact objection: v1.7's step 5 compared the destination against `st_src`, the
pre-syscall stat of the SOURCE NAME, which a same-UID writer can also control — so a substitution inside the
stat→`renameat2` window produced `st_dst == st_src == impostor`, and the proof passed. The anchor is now `st_tmp`, a
value captured before the name was ever exposed, and CP3e makes the CONTENT claim explicit as well, since inode identity
alone can never speak about bytes (see W3 in §5.2 step 5).


5.2.5 **Filesystem threat model and TOCTOU closure (V14-07; explicit UID trust boundary, V15-06).** Boundary:
`RUN_ROOT` SHALL be an **absolute** path on the evidence filesystem, opened with `O_NOFOLLOW`, not group/other-writable
(`st_mode & 0o022 == 0`) and **owned by the runner's effective UID** (`st_uid == os.geteuid()`); both properties are
checked against `fstat(pfd)` at lock time (§5.2 step 1) — either failure → `PublishUnavailable`, before any artifact
exists.

**Same-UID vs different-UID (V15-06, the trust boundary stated explicitly).** *Different-UID processes are PREVENTED,
kernel-enforced:* owner-only mode (no group/other write bit) + `O_NOFOLLOW` + the fstat/stat identity re-proof mean a
process running as another UID cannot create, rename or replace any name inside `RUN_ROOT`, cannot substitute a symlink
for a path component, and cannot make the locked descriptor disagree with the path unnoticed. *Same-UID processes are
INSIDE the trust boundary for prevention — DETECTED, never prevented:* any process running as the runner's effective UID
owns `RUN_ROOT`'s write bit and can therefore create, rename (including swapping `.<run_id>.staging` for a foreign
directory) and unlink names **without ever taking the flock** — `flock` serializes cooperating lock-holders only, and is
explicitly not a security boundary. The design does not claim to stop such a writer (it cannot, without privileges the
runner does not have); it claims that every resulting inconsistency is observable and terminal: step 5's inode proof
catches the rename swap (quarantine + strictly fatal, §5.2 step 5 / V15-05), CP1b re-verifies content against the
out-of-band pin before any receipt exists (§7.5), and every later `observe()` re-verifies the artifacts against the
manifest/receipt/journal pins (→ T3/T5, never silent success). The residual for a same-UID adversary — control of both
`RUN_ROOT` and the pin store — is `runstore`'s authentication limit of §10.1 applied to the filesystem surface, stated
under *After CP1b* below.

Cooperating publishers are serialized by the flock; a *non-cooperating* writer with access to `RUN_ROOT` is the threat
the following items close:

* **Source-identity race (stat → renameat2).** The step-3 `stat(src_name)` window can never be fully eliminated
  (`renameat2` takes names, not descriptors), so it is closed by detection *with consequence* — and, since v1.8
  (V17-02), against the right anchor: the step-5 proof compares the published inode against the **creation identity**
  captured from the creating descriptor (`fstat(tmp_fd)`, or `fstat` of the staging directory fd), NOT against the
  pre-syscall stat. Anchoring on the pre-syscall stat was vacuous in precisely this window: a substitution between
  that stat and the syscall makes the pre-syscall stat and the post-rename stat describe the same impostor. With the
  creation anchor, a substitution after step 3 is renamed into place and then fails the proof → quarantine of the
  published name + strictly fatal `PublishIdentityMismatch` (V15-05), so the impostor is moved out from under the
  final name or, if the filesystem refuses even that rename, can only ever resolve T5/T3 — never silent success. For
  the receipt the content half is proved too, by CP3e (§5.2.4 step 8).
* **Content race (verify → rename).** Inode identity does not prove content: staging files may be modified between §5.4
  self-verification and CP1. CP1b (§7.5) re-runs `load_run(final, pinned_manifest_sha256 = pin)` while the lock is
  still held, before any receipt exists; a swap in either window is caught by the pin and quarantined (→ T5).
* **After CP1b.** A concurrent writer may still edit the final directory before or after the receipt; that cannot be
  prevented without permissions, so it is *detected*: every later `observe()` re-verifies content against the out-of-band
  manifest pin (→ T3) and against the receipt/journal pins of §10.1. Stated limits: a root/filesystem-administrator
  adversary, and anyone who controls both `RUN_ROOT` and the out-of-band pin locations, are outside this design — exactly
  the `runstore` authentication limit (§10.1), now stated for the whole filesystem surface. `flock` itself only
  serializes cooperating processes; it is not claimed as a security boundary.

**V15-05 — fatal-quarantine consequences (normative).** `PublishIdentityMismatch` raised in step 5 is
unconditionally fatal: the seal aborts, the process exits non-zero, and CP1b/CP2/CP3 are NEVER reached for this
`run_id` — so no receipt can exist for an impostor, and an impostor can never classify as T4/T6 (T6 requires a valid
receipt; T4 requires an audit pass against the out-of-band manifest `pin`, which the impostor's content fails →
`observe()` resolves T3, or T5 when a staging/quarantine sibling is also present, per §9.3). In the normal case the
impostor is moved out from under the final name by the quarantine rename — the filesystem has just proven that very
`renameat2` works on this directory, so a refusal here would be the second call failing after the first succeeded.
The two remaining cases are: `PublishConflict` (`<run_id>.unverified` already exists → the impostor stands beside a
pre-existing quarantine → `observe()` sees final + quarantine = the K8 signature → T5, never success) and an
I/O/permission error (the impostor stands under the final name until an operator removes it; it still fails `load_run`
against the pin → T3, which is terminal — quarantine-or-report per reviewer, never T4/T6). Stated residual:
physically removing a directory requires this same `renameat2`; if the kernel or filesystem refuses even that, no
portable mechanism exists to move it — the guarantee is therefore classification-level (never successful, never
receipted, always reported), not removal-level.

5.3 **Post-publication persistence (v1.7, V16-03/D33):** `os.fsync(pfd)` (CP2) makes the rename durable; a failure
here halts the sequence BEFORE the receipt → **T4 — a TERMINAL incomplete state requiring operator review**: no
automatic recovery re-runs fsync or CP3, because the complete receipt draft existed only in memory and died with the
process (K11: the operator re-verifies against the out-of-band pin and decides; a rerun is a new `run_id`).

5.4 **Write-read-audit self-verification (VERIFYING), before any publication:**

```
pin = WRITE_RUN(pfd, staging_name, records, events)        # exclusive create + streamed + fsync F1–F4 (§5.1.1)
run = load_run(staging, pinned_manifest_sha256 = pin)      # strict types, digests, self-digest, chain head
abort_seq = pacer.abort_seq                                # captured from the live pacer BEFORE releasing `run`
del run                                                    # single-copy Domain A: audit_run loads its own copy
                                                           # internally (audit.py:626) — never two live copies (V15-07)
result = audit_run(staging, pinned_manifest_sha256 = pin, wrapper_count = transport.sent,
                   abort_seq = abort_seq, profile = (OBS01_PROFILE | OBS02_PROFILE),
                   skips = pacer_skips, expected_boundaries = plan.boundaries, boundary_skips = plan.boundary_skips)
require result.ok and transport.sent == len(pacer.records) and session_budget.retained_total <= SESSION_BODY_BUDGET_BYTES
```

A failure ⇒ the staging tree is quarantined (§5.5) and the run resolves T5 (or T3 if the same defect is found on a
published run by `observe()`). What gets published is the verified PERSISTED bytes (loaded and audited above, then
released): nothing is serialized from mutable state after this point, and at most one copy of the body set is loaded
at a time (§6.5 single-copy rule).

5.5 **Quarantine (`<run_id>.unverified/`).** Implemented by `publish_dir()` with the same `pfd`, flock and
`renameat2(RENAME_NOREPLACE)` sequence: staging (or stale staging, or an EEXIST loser) is atomically moved aside; never a
copy, never a partial delete; the quarantined tree keeps every byte written (evidence of the failure), and T5 is terminal
(no re-promotion — a future attempt uses a fresh `run_id`).

## 6. Memory accounting — domains A/B/C, streaming checks, offline bounds (V13-04)

6.1 **Domains (byte-exact, disjoint):**

| Domain | Contents | Budget constant | Value | Enforcement point |
|---|---|---|---|---|
| A — retained | complete response bodies held in `pacer.records` until seal | `SESSION_BODY_BUDGET_BYTES` | 52,428,800 (50 MiB) | §6.4 chunk check + §6.2 commit gate |
| A — per response | one response body | `MAX_BODY_BYTES` | 4,194,304 (4 MiB) | transport read loop (header pre-check advisory; read loop authoritative) |
| B — transient | live non-retained allocations: chunk buffer, body scratch + its `bytes` copy, HTTP internals, seal slices, verify-line parse buffers | `TRANSIENT_BUDGET_BYTES` | 12,582,912 (12 MiB) — OFFICIAL, measured proofs V15-07 (D30) | §6.5 three-phase measured bounds + allocation sites below |
| C — fixed harness | record metadata (bodies excluded), event log, plan, skips, manifest, receipt draft, `SessionBudget` scalars | `HARNESS_FIXED_BUDGET_BYTES` | 2,097,152 (2 MiB) | bounded by construction (§6.6) |

6.2 **Single owner.** `SessionBudget.retained_total` (integer bytes of Domain A) exists once, owned by the orchestrator,
and is mutated in exactly one place: `commit(n)` after the record append (§3.1.3). The chunk path (§6.4) receives the
budget read-only for its checks; because single-flight sequences worker reads strictly before the orchestrator's commit,
there is no concurrent mutation. Pre-dispatch checks (`retained_total + plan_next_body ≤ 50 MiB` from Content-Length or
OBS-01 fixture sizes) are **advisory only**; they may skip work early but never substitute for the §6.4 checks.

6.3 **Retention rule.** A body enters Domain A only as a **complete** record body. On a mid-body budget breach the scratch
is discarded whole, the record is written with `body = b""` and `error = "INCIDENT-MEMORY"`, and the run aborts (B5): partial
bodies never persist, egress counts stay equal, and the discarded length is reported in the receipt.

6.4 **Chunk-level streaming aggregate check (normative body-read path, Step-2 extension of the transport's read):**

```
CHUNK_BYTES = 65_536                                                   # 64 KiB
# inside the worker, after getresponse(), under the absolute deadline and CancellationState:
scratch = bytearray()
while True:
    chunk = response.read(CHUNK_BYTES)                                 # ≤ 64 KiB transient
    if not chunk: break
    if budget.retained_total + len(scratch) + len(chunk) > SESSION_BODY_BUDGET_BYTES:
        discard(scratch); return TransportResult(status_from_headers, INCIDENT_MEMORY, headers, b"")
        # checked BEFORE the chunk is staged: retained_total can never exceed 50 MiB by even one byte
    if len(scratch) + len(chunk) > MAX_BODY_BYTES:
        discard(scratch); return TransportResult(None, CONNECT_ERROR, headers, b"")    # E5/N8 outcome, unchanged
    scratch += chunk
body = bytes(scratch)                                      # 2×MAX_BODY peak (scratch + copy) — counted in §6.5 phase 1
```

Behavioural equivalence with the Step-1 single `read(MAX+1)`: same per-response outcome (`CONNECT_ERROR`), same headers,
same interruption semantics (socket shutdown makes `read` raise → `Cancelled` path unchanged); only the allocation pattern
changes (chunks instead of one 4 MiB+1 buffer). On `INCIDENT_MEMORY` the orchestrator sees `status` already known from
`getresponse()` (200) with the memory error → record `(200, INCIDENT-MEMORY)` → B5 (§3.3.3).

6.5 **Domain B derivation — per-phase measured bounds (v1.6/v1.7, V15-07/V16-04; V14-03 corrected v1.4's "none concurrent"
claim; v1.5's formula-only numbers did not survive measurement against the code those paths would actually run).**
Every peak below is the maximum LIVE allocation at a single instant of the normative sequences (§6.4 request path,
§5.1.1 seal, §5.1.2 verify), measured with `tracemalloc` on CPython 3.12 over worst-case inputs (a full
`MAX_BODY_BYTES` response; a record line at the `MAX_LINE` cap) and derived from the code that exists at the anchor.
The phases are sequential (single-flight; seal runs after all requests; verify runs after seal), so the budget is the
maximum phase peak, not their sum. Probe methodology, the raw CPython 3.12.3 measurement tables and the native-headroom
accounting behind `HTTP_HEADROOM` are recorded in Appendix A (V16-04).

```
Phase 1 — request (per response, §6.4): scratch may reallocate while extending (old + new ≤ 2 × MAX_BODY_BYTES),
          and `body = bytes(scratch)` holds BOTH the bytearray and the finished copy:
    peak₁ ≤ 2 × MAX_BODY_BYTES + CHUNK_BYTES + HTTP_HEADROOM + allocator margin
          = 8,388,608 + 65,536 + 262,144 + 65,536 = 8,781,824 B
    (HTTP_HEADROOM = 262,144 B: a design constant derived ANALYTICALLY in Appendix A.5 — four enumerated native
     consumers ≤ 131,072 B, doubled for the unenumerated ones (stdlib `_ssl` C objects, resolver scratch, allocator
     bookkeeping). v2.0 replaces the factor with an INVENTORY (A.5.8, V19-03): every per-request consumer is derived
     from a protocol constant and checked against a measured stage, and the derived bounds sum to 258,048 B ≤ 262,144 B
     (TLS session 98,304 + HTTP staging 86,016 + body staging 65,536 + allocator headers 8,192). It is CHECKED, not
     inferred, on TWO interposed channels (G-V17-04/G-V18-03) and against that inventory (G-V19-03): the CLIENT-ONLY
     request region measures 214,120 B of malloc plus 0 B of direct `mmap` — 214,120 B ≤ 262,144 B, 48,024 B of slack —
     and the whole phase-1 path's interposed malloc peak (8,400,920 B, mmap channel 0 B) is inside the 8,781,824 B bound.
     v1.7's claim that a Δ`uordblks` sample bounded the native peak is RETRACTED: a before/after difference is a
     lower bound, and on the probe fixture the six sample points reached 112,272–159,360 B against a
     72,272–87,088 B end delta (A.5.2–A.5.3).)

Phase 2 — seal, §5.1.1 metadata-only writer (V15-01): ONE 48 KiB body slice + ONE ≤ 64 KiB base64 chunk + the
          CPython base64 encoder's 32,768 B working buffer + ≤ 4,096 B of digest line, head/tail fragments and
          framing — all live at the `b64encode` instant; `chunk` is `del`ed before the next slice:
    peak₂ ≤ 49,152 + 65,536 + 32,768 + 4,096 = 151,552 B   (measured 148,004 B tracemalloc / 147,848 B interposed)
    (banned patterns, measured: retaining chunks across iterations 5,656,645 B; v1.5's two `record_to_json(r)`
     calls per record allocate the full ≤ 5,592,408 B base64 string twice — G-V15-01 kills both. v1.4's model
     (full base64 string + full JSON line = 11,184,816 B) and the current Step-1 write_run (≥ 139.8 MB) remain
     excluded by D18.)

Phase 3 — verify, §5.1.2 incremental `load_run` (V15-02): the reader holds at most ONE line buffer, its decoded
          text and the parsed `body_b64` string at once, plus the file object's 8 KiB buffer and json/dict
          overhead; the per-line release order is normative (read ≤ MAX_LINE+2 → decode → `del` line bytes →
          json.loads → `del` text → `.encode("ascii")` → `del` the str → `b64decode(bytes)` → `del` raw):
    MAX_LINE = 4 × ⌈MAX_BODY_BYTES / 3⌉ + 512 (framing) = 5,592,920 B
    peak₃ ≤ 2 × MAX_LINE + 16,384 = 11,202,224 B   (measured 11,188,520 B on a MAX_LINE line, 11,186,544 B
                                                      interposed; +8,192 file buffer + ~4,000 json/dict overhead
                                                      -> 11,196,712 B ≤ bound)
    (banned patterns, measured: `base64.b64decode(str)` re-encodes the whole string → 15,381,335 B;
     `json.loads(raw bytes)` with the buffer referenced → bytes + decoded str + parsed = 16,781,149 B;
     Step-1's whole-file `_read` + `_jsonl` → ≥ 139.8 MB. All three exceed the budget and are BANNED.
     The v1.7 structure pass (§5.1.2) parses + key-checks + discards with the same release order and therefore
     shares this bound; raw values: Appendix A.)

budget = max(peak₁, peak₂, peak₃) = 11,202,224 B
TRANSIENT_BUDGET_BYTES = 12,582,912 B (12 MiB); margin = 1,380,688 B (12.3 %) over the largest phase.
```

Every phase peak is a hard cap enforced at its allocation sites: phase 1 by the §6.4 checks; phases 2/3 by construction
— the writer never allocates a whole line and never calls `record_to_json`, the reader never reads a whole file and
never holds line bytes + text + parsed simultaneously (G-V14-02/G-V15-01/G-V15-02/G-V16-05/G-V13-04), with the raw
measurements and native-headroom accounting in Appendix A (G-V16-04). **Domain A single-copy
rule (verify/observe):** before `load_run` runs, the orchestrator releases the live `pacer.records` references — the
bytes are already on disk — and the explicitly loaded `run` is released (`del run`) BEFORE `audit_run` loads its own
copy (audit.py:626), so at any instant at most ONE full body set exists (≤ 50 MiB). Total process envelope: A 50 MiB +
B 12 MiB + C 2 MiB ≈ 64 MiB (runner and `observe()` alike). Any future change to `MAX_BODY_BYTES`, the writer or the
reader MUST re-derive all three phases under the Appendix A protocol before changing `TRANSIENT_BUDGET_BYTES`
(decisions D13, D19, D30, D34).

6.6 **Domain C by construction.** `RUN_RECORD_LIMIT = 2000` records (plan bound ≈ 750/day; hard stop → `INCIDENT-RECORD-LIMIT`
abort, `derived = None`, `abort_seq = len(records)`): metadata ≤ 2000 × 400 B = 800 KiB; event log ≤ 1000 × 800 B = 800 KiB;
plan/skips/admitted decisions ≤ 300 KiB; manifest + receipt draft ≤ 100 KiB; one `observe()`/CP3e snapshot
buffer ≤ `RECEIPT_MAX_BYTES` + `CHUNK_BYTES` = 196,608 B (V17-03) → ≈ 2.2 MiB ≤ budget. Exceeding any term aborts
before allocation growth matters (fail closed, B5-style: `abort("INCIDENT-MEMORY")`).

6.7 **Offline decompression bounds (never in the hot path).** The execution path never decompresses anything: bodies are
stored verbatim as received, and no `Content-Encoding` handling exists in the transport. Offline verification of compressed
evidence (archives, transferred run dirs) SHALL stream-decompress in 64 KiB chunks under BOTH bounds, enforced before each
output chunk is kept:

```
MAX_DECOMPRESSED_BYTES = 52_428_800      # 50 MiB per artifact (a larger artifact than the whole session budget is corrupt)
MAX_EXPANSION_RATIO    = 1000            # output_bytes ≤ 1000 × input_bytes, checked incrementally
```

A breach aborts the read, marks the artifact unreadable, and — for a run artifact under `observe()` — resolves T3
(fail closed; never a partial decompression presented as evidence). Decompression bombs and nested streams MUST be covered
by tests (G-V13-04).

## 7. Signal state machine, interrupt deferral, commit checkpoints CP1–CP3 (V12-07 retained, V13-05 specified)

7.1 **First signal (SIGINT or SIGTERM):** the async handler performs only flag-set operations (`interrupt_flag`,
`interrupt_signal = signal.SIGINT | SIGTERM`, plus one byte to the internal marker); all policy runs on the orchestrator
thread. The flag is checked: (i) at the top of every admission-loop iteration, (ii) between the predicate pass and
dispatch (§3.1.3), (iii) at ≤ `INTERRUPT_POLL_NS = 100 ms` bounds inside any wait (the admission wait is sliced to ≤ 100 ms
so the poll bound holds even inside a 60 s `release` sleep), and (iv) after each record append. When observed before
dispatch: no request starts → STOPPING → the in-flight request (if any) completes and is recorded → seal → self-verify →
publish → receipt, with `outcome = ABORTED`, `reason = SIGNAL-INT` / `SIGNAL-TERM` → T1, exit 130 / 143. A signal delivered
after dispatch lands mid-flight: the request completes (or the watchdog cancels it at 17 s); its record is appended; the
flag is observed on the next check. No request ever starts *after* the flag was observed.

7.2 **Signals during PRE-FLIGHT:** set the flag; the refusal/abort path runs at the next check → the refusal journal (if a
refusal condition was already being written) or an ordinary graceful STOPPING seal if records exist.

7.3 **STOPPING guarantees:** `execute()` raises `InterruptedBeforeStart` before producing a record; no group admission is
evaluated; the event log receives `TIMELINE_END` at the end of the seal.

7.4 **Second signal (EMERGENCY):** `os._exit(130 or 143)` (code of the FIRST signal) — with exactly one deferral: if the
process is inside a checkpoint sequence (§7.5), the exit waits for the current single syscall (rename/fsync) plus its
bookkeeping write to return, bounded by `CHECKPOINT_DEFER_MAX_MS = 250 ms`; beyond the bound, exit anyway. Such an exit is
permitted because each syscall is atomic in the namespace: whatever the kernel completed is the state `observe()` resolves
(K9–K12). Never defer elsewhere (mid-wait, mid-request) — that exit is immediate.

**Enforcement mechanism (v1.5, V14-08) — a main-thread handler alone cannot run while the main thread is blocked inside a
synchronous syscall, so the bound is enforced by the `obs-watchdog` thread (§2.1):**

1. **State** (orchestrator-owned, written only by handler/checkpoint code): `emergency_armed_ns: int | None` (default
   `None`), `in_checkpoint: bool`, `first_exit_code: int`.
2. **The watchdog thread** (daemon, started before PRE-FLIGHT) waits on a `threading.Event`; on set it loops on
   `time.monotonic_ns()` and calls `os._exit(first_exit_code)` when
   `now ≥ emergency_armed_ns + CHECKPOINT_DEFER_MAX_MS × 1_000_000`. It reads no filesystem state, takes no lock.
3. **Second-signal handler:** if `not in_checkpoint` → `os._exit(first_exit_code)` immediately from handler context
   (CPython runs the handler when the signal interrupts the main thread — including via EINTR, see 5). If
   `in_checkpoint` → arm the watchdog **once** (`if emergency_armed_ns is None: emergency_armed_ns = now; event.set()`)
   and return; later signals re-enter the same branch and MUST NOT extend the deadline.
4. **Deferred exit point:** checkpoint code performs `os._exit(first_exit_code)` itself immediately after the current
   single syscall and its bookkeeping write return (CP1 → CP1b → CP2 → CP3 bookkeeping, §7.5). If a syscall blocks past
   the bound, the watchdog thread exits the process anyway — the 250 ms ceiling never depends on the main thread
   returning.
5. **Stated limits:** (a) PEP 475 — CPython retries an interrupted syscall after the handler returns; safe here:
   `renameat2` is atomic per call and `fsync` is idempotent, so a retry never duplicates an effect; (b) the bound runs
   from handler execution — a kernel-uninterruptible stall (D-state), during which even SIGKILL cannot act, is outside
   the guarantee; (c) an exit during CP1–CP3 leaves exactly the K9–K12 state, which the resolver maps deterministically.

6. **Gate:** G-V14-08 (subprocess tests with an injected slow `fsync`).

7.5 **Commit checkpoints (COMMITTING), in order, all under the `pfd` flock of §5.2.1:**

```
CP1  publish_dir(pfd, ".<run_id>.staging", "<run_id>", expect = st_stage, identity_source = CREATION)
       # = renameat2(pfd, ".<run_id>.staging", pfd, "<run_id>", RENAME_NOREPLACE). st_stage is the staging
       #   directory's creation identity, captured on its descriptor right after mkdir (§5.1.1, V17-02); step 5
       #   of §5.2 proves the PUBLISHED directory's (st_dev, st_ino) against st_stage, so a staging-name swap in
       #   the stat→renameat2 window cannot publish a foreign tree and still satisfy the proof
     → phase = COMMITTING/SEALED;  pin and abort_seq were already flushed out-of-band (§5.1)
CP1b post-rename content re-verification (v1.5, V14-07; pin-only call restated V15-04), lock still held:
     run = load_run(final, pinned_manifest_sha256 = pin)   # the out-of-band MANIFEST pin of §10.1 — receipt_pin is
     NEVER used as a manifest pin, and observe() without `pin` resolves T3 (or T5), never T4/T6 — and the manifest
     digest verifies → otherwise quarantine the published final via renameat2(NOREPLACE) into
     <run_id>.unverified (§5.2.5), stop → T5; a crash here equals K10 (final, no receipt) → observe() re-verifies →
     T4 or T3 — an impostor never receives a receipt
CP2  os.fsync(pfd) returns 0                                   # namespace durable; failure → stop → T4 (K11)
CP3  receipt published under `identity_source = CREATION` (V16-07, V17-02):
     tmp_fd = os.open(".<run_id>.receipt.tmp", O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0o644, dir_fd = pfd)
     → write canonical receipt JSON, hashing the bytes written (receipt_sha_written) → os.fsync(tmp_fd)
     → st_tmp = os.fstat(tmp_fd)     # the CREATION identity (st_dev, st_ino), captured on the CREATION descriptor
                                     #   BEFORE close (V17-02); S_ISREG and st_nlink == 1 required
     → os.close(tmp_fd)
     → publish_file(pfd, ".<run_id>.receipt.tmp", "<run_id>.receipt.json",
                    expect = st_tmp, identity_source = CREATION)
         # renameat2(RENAME_NOREPLACE); step 3 gates st_src against st_tmp pre-syscall, step 5 proves
         #   (st_dst.st_dev, st_dst.st_ino) == (st_tmp.st_dev, st_tmp.st_ino) post-syscall — the destination is
         #   verified against the CREATION identity, never against the (substitutable) source stat
     → os.fsync(pfd)                 # receipt directory entry durable
     CP3e content re-proof: snap = snapshot(pfd, "<run_id>.receipt.json", RECEIPT_MAX_BYTES)
         → require snap.sha256 == receipt_sha_written     # the published bytes are OUR bytes (§9.2.1 helper)
         → ONLY THEN print receipt_pin = snap.sha256 (§10.1) and phase = COMMITTED
         → resolve (§9.2); receipt fields carry terminal_state, outcome, reason, exit_code
```

State after each crash point: before CP1 → staging exists → K7/K0 → T2 or T5; CP1/CP1b→CP2 → final exists, no receipt →
`observe()` re-verifies and classifies **T4 — TERMINAL, operator review** (v1.7 removed the old "may complete CP2/CP3"
recovery, V16-03/D33: the complete receipt draft existed only in memory and died with the process — no CP1-durable
draft exists, so no code path may write, fsync or publish a receipt after CP1; K10–K12 resolve T4 only); after CP3 →
T6. Power loss between CP1 and CP2 may lose the rename (not yet fsynced): final absent AND staging absent →
T2 — never a half-visible directory (the rename itself is atomic).

7.6 **Exit-code table:** `T6 ∧ COMPLETE-VALID → 0`; `T6 ∧ INCONCLUSIVE-TIMING → 1`; `T6 ∧ FAILED → 1`; `T0 → 2`;
`T1 → 1` (or `130/143` when the outcome reason is `SIGNAL-INT`/`SIGNAL-TERM`); `T2, T3, T4, T5 → 1`;
`EMERGENCY → 130/143` immediately. No other exit codes are permitted.

## 8. Incident and crash-persistence matrices (fully enumerated)

Columns: **D** detection (mechanism actually in the code), **C** countermeasure, **O** outcome code / classification
(protocol §6 language in quotes), **T** terminal state (§9.3), **E** evidence treatment. Rows are exhaustive for their
domain; any condition not listed by its matrix falls into the row marked `default`.

### 8.1 N — Network & transport (N1–N14)

| ID | Condition | D | C | O | T / E |
|---|---|---|---|---|---|
| N1 | connect phase (TCP+TLS) exceeds 5 s | socket timeout → `error=TIMEOUT`, `status=None` | single attempt, no retry; streak logic | no-response family (streak) | record kept; feeds B3 |
| N2 | read phase exceeds 12 s | socket timeout → `TIMEOUT` | same as N1 | no-response family | record kept |
| N3 | 17 s absolute deadline reached (PACE-8) | `run_with_deadline` cancels at `start_ns+17s`; `error=DEADLINE`; duration ∈ [17 s, 18 s] | flag + socket shutdown; nothing sent after cancel | protocol "TIMEOUT" (harness `DEADLINE`) | record; audit (e) bound pins it |
| N4 | cancellation not finished within 1 s allowance | `CancellationFailed`; `error=CANCEL_FAILED`; duration ∈ [17 s, 19 s] | transport disabled permanently; `abort("INCIDENT-CANCEL")` | `ABORT (INCIDENT-CANCEL)` | last record; audit B2 + (e) |
| N5 | any non-200 (3xx/4xx/5xx incl. 403/418/429/500) | `record.status != 200` → ladder B1 | pacer abort `HTTP-<status>`; transport self-disables; redirects never followed | `ABORT (INCIDENT)` | record last; reason in receipt |
| N6 | 3 consecutive `status=None` records | ladder B3 streak ≥ 3 | `abort("INCIDENT-NETWORK")` | `ABORT (INCIDENT-NETWORK)` | records end at 3rd; audit (a) pins |
| N7 | connection refused/reset/unreachable/TLS failure | `error=CONNECT_ERROR` | no retry (single attempt per protocol §2) | no-response family | record kept |
| N8 | response body > 4 MiB | read loop exceeds `MAX_BODY_BYTES` → `(None, CONNECT_ERROR)` | per-response cap; body discarded | no-response family (streak) | record; no body retained |
| N9 | 200 but non-JSON / wrong 12-field shape / wrong open time / weight `X-MBX-USED-WEIGHT-1M` > 600 | runner validation after append → ladder B5' (`INCIDENT-RESPONSE`) | `abort`; owner reports before rerun | `ABORT (INCIDENT)` | record unmodified (frozen); receipt carries reason |
| N10 | outbound request violates allow-list | `validate_spec` raises before socket (pacer pre-dispatch or transport pre-send) | refusal before egress; egress counter unchanged | pre-flight: refusal (T0); mid-run: abort | no record (legal pre-record abort shape, §3.3.4) |
| N11 | 3xx redirect response | status ∈ 300–399 → ladder B1 | never followed (`http.client` does not follow; allow-list path) | `ABORT (INCIDENT)` ("redirects off; any 3xx is an incident") | record last |
| N12 | `X-MBX-USED-WEIGHT-1M` > 600 | header whitelisted, inspected post-record → B5' | abort before the next send | `ABORT (INCIDENT)` | headers persisted in record |
| N13 | HTTP 418 or 429 | status non-200 → B1, plus cooldown branch | write+fsync `data/binance_cooldown.json`, then abort | `ABORT (INCIDENT)` + cooldown persisted | record + cooldown file |
| N14 | egress counters disagree (`jsonl_count ≠ wrapper_count ≠ manifest_count`) | audit (g) during self-verification | fail closed: no publication | `INVALID-PACING` (harness defect) | staging quarantined (T5); report |

default N: any transport condition not listed → `CONNECT_ERROR` record → streak path (B3), never a silent success.

### 8.2 T — Timing & clock (T1–T9)

| ID | Condition | D | C | O | T / E |
|---|---|---|---|---|---|
| T1 | monotonic regression `end_ns < start_ns` | audit (a) | impossible on CLOCK_MONOTONIC; if seen, fail closed | `INVALID-PACING` | staging quarantined (T5) |
| T2 | start timestamps decrease across `seq` | audit (a) non-decreasing rule | same as T1 | `INVALID-PACING` | T5 |
| T3 | local wall-clock jump (NTP step/settimeofday) | wall clock is never read for scheduling/measurement — only labeled diagnostics; decisions use monotonic + server time only | no wall-clock decision path exists to corrupt | no effect on records | diagnostic note in receipt |
| T4 | wake > 500 ms after its deadline | lateness measured at wake; recorded | no catch-up, no early start; only V1 judges usability | diagnostic; may yield `TIMING-INVALID` group | receipt diagnostics |
| T5 | server time goes backwards > 1 s across `/time` samples | analysis of recorded samples (protocol §6) | abort before next group | `ABORT (INCIDENT)` | sealed run T1 |
| T6 | `Theta` empty after the one 60 s fallback recompute | `OffsetEstimator.estimate → None` | boundary `SYNC-SKIPPED`; never midpoint/wall-clock fallback | skip chain → `INCONCLUSIVE-TIMING` (3 in a row stops session) | `boundary_skips` evidence |
| T7 | uncertainty `w(t) > W_max = 250 ms` at the decision instant | `estimate.adequate()` false | `SYNC-SKIPPED`, or refusal at start (`SYNC-INADEQUATE-AT-START`, T0) | `INCONCLUSIVE-TIMING` / refusal | skip evidence / refusal journal |
| T8 | spurious early/late wake of the admission or estimator sleep | every wait re-reads the clock against an absolute instant (`_wait_until`, wake loop) | re-evaluate; never trust the planned wake time | — | none (correct by re-read) |
| T9 | duration anomaly: record > 18 s, `DEADLINE` outside [17,18] s, `CANCEL_FAILED` outside [17,19] s (suspend/stall/clock source failure) | audit (e) | fail closed | `INVALID-PACING` | T5 |

### 8.3 P — Pacing & admission (P1–P8)

| ID | Condition | D | C | O | T / E |
|---|---|---|---|---|---|
| P1 | start-to-start gap < 600 ms (OBS-01: < 2 s) | audit (c), exact integer ns | `earliest_start_ns` spacing; single-flight | `INVALID-PACING` | T5 |
| P2 | > 2 starts in `(t−1s, t]` (OBS-01: > 1 in 2 s) | audit (d), open-left/closed-right bisect | `release_ns` rolling release, `max()`-combined windows | `INVALID-PACING` | T5 |
| P3 | > 60 starts in `(t−60s, t]` (OBS-01: > 30/min) | audit (d) | same as P2 | `INVALID-PACING` | T5 |
| P4 | request starts before previous completed (PACE-1) | audit (b) `end(n) ≤ start(n+1)` | single-flight lock; `ConcurrentExecution` on overlap | `INVALID-PACING` | T5 |
| P5 | early start / catch-up (`start < max(earliest, D)`) | admission predicate uses one read; (b)/(c) catch violations offline | never early, never catch up (§3.2) | `INVALID-PACING` if persisted | T5 |
| P6 | admission inequality wrong (≤ used, or `theta_hi` decides, equality skipped) | `validate_missed_window_decision`: strict `lower_server_ns > limit_ns`, `limit` recomputed from `GROUP_WINDOWS_MS` | `decide_admission` strict inequality; only `theta_lo` decides | `INVALID-PACING` (f) | T5 |
| P7 | fabricated/inconsistent skip evidence (`theta` mismatch, `m_e` inflated, missing/mismatched DECISION event, broken chain, missing TIMELINE_END) | `validate_decision_evidence` + `verify_event_log` + manifest pin | event log chained to records and authenticated manifest | `INVALID-PACING` (a)/(f) | T5 |
| P8 | static target (no per-wake re-evaluation) → start earlier than current `D(X)` | V1 on the measured `S1` at analysis; admission brackets recompute `m_e` offline | §3.1.1 fixed-point wake loop (GV-6/GV-7 pin it) | `TIMING-INVALID` group/boundary | records kept; never counted |

### 8.4 E — Execution & environment (E1–E12)

| ID | Condition | D | C | O | T / E |
|---|---|---|---|---|---|
| E1 | first SIGINT | handler flag; checks §7.1 | graceful STOPPING → sealed abort | `ABORTED (SIGNAL-INT)` | T1, exit 130 |
| E2 | first SIGTERM | same | same | `ABORTED (SIGNAL-TERM)` | T1, exit 143 |
| E3 | second signal | handler sets flags; `obs-watchdog` daemon thread enforces the bound (V14-08) | immediate `os._exit` outside checkpoints; inside CP1–CP3 the main thread exits after syscall + bookkeeping, and the watchdog exits at ≤ 250 ms even if a syscall blocks (§7.4) | immediate exit | state per K-rows |
| E4 | session aggregate > 50 MiB | §6.4 chunk check before staging | discard scratch; record `(200, INCIDENT-MEMORY, b"")`; B5 | `ABORT (INCIDENT)` memory | T1; receipt reports discarded bytes |
| E5 | one response > 4 MiB | read loop / header pre-check | `(None, CONNECT_ERROR)`; body never retained | no-response family | record (N8) |
| E6 | transient pool would exceed `TRANSIENT_BUDGET_BYTES` (12 MiB) | the three §6.5 phase bounds (request conversion, streaming seal, verify line parse) | fail closed before allocating (`INCIDENT-MEMORY`) | `ABORT (INCIDENT)` | T1 |
| E7 | ENOSPC/EIO writing staging files | `OSError` from `write_run` | abort seal; quarantine staging | `INVALID-PACING`/seal failure | T5, staging preserved |
| E8 | fsync failure during seal | `OSError` from fsync | same as E7 | seal failure | T5 |
| E9 | concurrent or re-entrant `execute()` | single-flight `acquiring(False)` → `ConcurrentExecution` | rejected; nothing sent, nothing recorded | no state change | none |
| E10 | send attempted on a disabled transport | `TransportDisabled` raised before any increment/send | permanent disable (non-200 or CANCEL_FAILED already terminal) | fail closed | prior abort governs |
| E11 | publish lock held > 30 s | bounded flock retry loop | abort publication; quarantine | seal failure | T5 |
| E12 | unexpected exception escaping the transport | `BaseException` → `abort("TRANSPORT-EXCEPTION")` | fail closed; never continue a run with unknown transport state | `ABORTED` (pre-record shape if no record) | T1 (or T2 if no artifact), receipt reason |

### 8.5 K — Staging crash persistence (K0–K12)

| ID | Crash/failure point | State left on disk | Recovery action | T | Proof obligation |
|---|---|---|---|---|---|
| K0 | before staging exists (crash mid-RUNNING or before seal) | nothing for `run_id` (only possible journal: none/torn) | none | T2 | invariant M: "entirely absent" |
| K1 | `mkdir(.<run_id>.staging)` → EEXIST (stale staging from a prior crash) | stale staging | quarantine stale atomically (renameat2), then seal anew | T5 (stale) / T6 (new attempt) | never merge or reuse staging trees |
| K2 | ENOSPC/EIO while writing `records.jsonl`/`events.jsonl` | partial file(s), no manifest | quarantine | T5 | partial trees never publish |
| K3 | crash mid `records.jsonl` write | truncated JSONL, no manifest | quarantine | T5 | `load_run` would refuse; resolver does not even try (no manifest) |
| K4 | crash/EIO mid `events.jsonl` write | events truncated, manifest absent | quarantine | T5 | same |
| K5 | crash mid `manifest.json` write | torn manifest | quarantine (pin cannot authenticate it) | T5 | exclusive-create + strict parse refuse torn bytes |
| K6 | fsync of any staging file returns EIO | files present, durability unproven | quarantine | T5 | never publish undurable evidence |
| K7 | crash after all three files durable, before renameat2 | complete staging, no final | quarantine (never complete an interrupted commit — D14) | T5 | CP1 is the commit point |
| K8 | renameat2 returns EEXIST (foreign destination under the lock) | foreign final + our staging | quarantine ours; report conflict | T5 | no-clobber by errno, not by pre-check |
| K9 | signal inside renameat2 | syscall atomic: staging XOR final | bounded deferral (§7.4); resolver takes whichever exists | T5 or T4/T6 | atomicity of one rename |
| K10 | crash after CP1 (incl. during CP1b re-verification), before CP2 fsync | final visible (process crash) or absent (power loss) | process crash → re-verify → T4 (terminal, operator review — V16-03); power loss → T2 | T4 or T2 | never partial: rename atomic; fsync gates durability; CP1b content proof precedes any receipt; T4 terminal (no CP1-durable receipt draft, D33) |
| K11 | fsync(pfd) (CP2) returns EIO | final complete, receipt absent | stop before CP3; classify T4 (terminal) — operator re-verifies against the out-of-band pin and decides; NO automatic fsync-retry/CP3 (V16-03) | T4 | receipt never precedes durable rename; the in-memory draft cannot be reconstituted (D33) |
| K12 | crash during receipt write | temp receipt only (or none) → final without receipt | temp residue ignored by the resolver (§5.2.4); classify T4 (terminal, operator review) — NO automatic receipt republication (V16-03) | T4 | temp+renameat2: no torn receipt under the final name; the complete draft died with the process (D33) |

## 9. Refusal journal, terminal-state resolver, protocol outcome mapping

9.1 **`obs-refusal/1` durability sequence (V13-05).** Pre-flight refusals (and `SYNC-INADEQUATE-AT-START`) write
`RUN_ROOT/<run_id>.refusal.json` with this exact order; the journal is durable ONLY after step 5:

```
1. fd = os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o644, dir_fd = pfd)   # EEXIST → never overwrite
2. write loop: canonical JSON (sort_keys, separators (",", ":")) of the exact key set:
   { "format": "obs-refusal/1", "run_id": str, "reason": str, "detail": str, "record_count": int,
     "exit_code": int, "created_utc": str, "pid": int, "journal_digest": str }   # V14-05: 9th key
   journal_digest = sha256(canonical of the other eight keys)         # manifest self-digest discipline
   reasons: UNSAFE-PLAN | UNSAFE-SPEC | HOST-NOT-ALLOWED | COOLDOWN-ACTIVE | COOLDOWN-CORRUPT |
            LAG-NOT-APPROVED (LAG-01) | PREREG-MISSING | PREREG-MISMATCH | SYNC-INADEQUATE-AT-START |
            INTERRUPTED-IN-PREFLIGHT | PLAN-INVALID
3. os.fsync(fd)                 # file content durable
4. os.close(fd)
5. os.fsync(pfd)                # directory entry durable — only now is the refusal authoritative
6. print sha256(the file's exact bytes) with flush — the out-of-band journal pin (§10.1, V14-05); MANDATORY for
   the T0 classification: observe() requires journal_pin supplied AND matching, else T3 (V16-01, D31)
```

Every refusal reason above aborts without egress (except `SYNC-INADEQUATE-AT-START`, which records `record_count` of the
completed sync group). A crash before step 5 leaves a torn or missing journal: the resolver MUST NOT read it as a refusal
— it resolves **T2**, never T0 (the v1.3 finding: a pre-flight crash must not masquerade as an intentional refusal). After
step 5, `record_count = 0` refusals resolve T0; with `record_count > 0` the journal still resolves T0 (no run artifacts may
exist for the `run_id`; if any do — including a quarantine — the contradiction resolves T3) — and in BOTH cases only
when `journal_pin` is supplied and matches. In `observe()` the journal is read EXACTLY as the receipt is: one descriptor-relative `snapshot()` (§9.2.1) whose
sha256 is compared with `journal_pin`, so the bytes that are authenticated are the very bytes that are parsed and
no presence check exists apart from the read (V17-03). The strict parser recomputes `journal_digest` over the other
eight keys (naive edits fail), and `observe()` COMPARES the file's byte SHA-256 against `journal_pin` **as a mandatory check
(v1.7, V16-01/D31): `journal_pin is None` → T3, mismatch → T3 — T0 is unreachable without the out-of-band pin**. The
self-digest alone is tamper-evidence, never authentication: anyone with `RUN_ROOT` write access can recompute it, so a
self-digest by itself must never grant authoritative status (v1.6's optional-pin reading is removed).

9.2 **Resolver precedence (normative `observe()`), deterministic given disk state only** (`pin`, `egress_count`,
`receipt_pin`, `journal_pin` supplied out of band). v1.7 fail-closed rules (V16-01/D31) are unchanged: **ALL THREE pins
are MANDATORY and each is checked before its target's state may be claimed** — (i) `pin` is MANDATORY to verify a final
(V15-04): `receipt_pin` is a hex string, never a manifest pin, Step-1's `load_manifest` fails closed without the pin
(runstore.py:255–258), so a present final with `pin is None` resolves `T5 if conflict else T3` BEFORE any load, and
T4/T6 are unreachable without the independently supplied manifest pin ("structural-only" verification of finals does
not exist); (ii) `journal_pin` is MANDATORY for T0 — absent or mismatched → T3 (§9.1); (iii) `receipt_pin` is MANDATORY
for T1/T6 — absent or mismatched → T3 (R3 below). Self-digests (`journal_digest`, `receipt_digest`) are re-verified as
necessary but NEVER sufficient: anyone with `RUN_ROOT` write access can recompute them (V16-01). Full forgery by an
adversary that controls records, files AND pins together stays out of scope — stated limit of `runstore`, §10.1.
Inputs are the five artifacts (refusal, staging, final, receipt, quarantine) × receipt validity × the closed outcome
enum × (`pin`, `egress_count`, `journal_pin`, `receipt_pin`) presence; every combination resolves to exactly one row of
§9.3. Six structural rules now bound the resolver:

* **R2** (V16-02) every quarantine attempt inside `observe()` goes through `try_quarantine`, which never raises.
* **R3** (V16-01/V16-06) the receipt is AUTHENTICATED before ANY of its fields is used.
* **R4** (V16-06) audit check (g) is mirrored explicitly before `audit_run`.
* **R5** (v1.8, V17-03) every artifact FACT — existence, size, bytes, digest — comes from exactly one
  descriptor-relative `snapshot()`/`stat_component()` call per name; the resulting values are FROZEN and every later
  branch reads the frozen fact. Presence checks and content reads are not two operations, so they cannot disagree.
* **R6** (v1.8, V17-03) a receipt present with NO final is a contradiction (CP3 cannot precede CP1's rename) and
  resolves T3; a receipt that cannot be read, is not a regular file, or exceeds `RECEIPT_MAX_BYTES` is a FAULT and
  resolves T3 — never T1/T6, and never "absent".

9.2.0 **Preconditions and read discipline (V17-03, normative).**

1. **Single-owner precondition.** `observe()` is invoked only for a `run_id` whose runner process is no longer alive
   (the operator's post-mortem path, §7.5/§9). It therefore does NOT take the `pfd` flock: a crashed publisher's lock is
   already released by process death, and a live concurrent publisher is a misuse of the resolver, not a state the
   classifier must encode. Under this precondition, every fact read in step 0 of §9.2.2 is a fact about a quiescent
   directory.
2. **One read per name.** `snapshot()` (content) and `stat_component()` (directory-shaped presence) are the ONLY ways
   `observe()` may learn about an artifact. Each name is opened AT MOST ONCE per observation and the result is frozen;
   `receipt_exists()` — v1.7 called it twice, once before the read and once after the audit — no longer exists as a
   concept, because "exists" is `snap is not ABSENT`.
3. **Banned in `observe()`** (asserted by G-V17-03): `Path.read_bytes`, `open(path)`, `os.path.exists`,
   `Path.exists`, `os.lstat`/`os.stat` on a PATH (as opposed to `dir_fd`-relative forms), any second presence check
   after a snapshot, any re-read or re-hash of bytes that were already snapshotted, and any parse of bytes other than
   the immutable `Snapshot.bytes`.
4. **FAULT is not ABSENT.** An `OSError` other than `ENOENT` becomes `FAULT(kind)`, which every branch maps to a single
   fail-closed terminal state; the resolver never treats "cannot read" as "not there" (v1.7's `read_bytes` could raise
   straight out of `observe()`, the same class of defect V16-02 closed for quarantine).

9.2.1 **`snapshot()` and `stat_component()` (normative helpers; both never raise).**

```
function SNAPSHOT(pfd, name, max_bytes) -> ABSENT | FAULT(kind) | Snapshot(bytes, sha256, n, st):
    # The ONLY way observe() (and CP3e) learns whether an artifact exists or what it contains (V17-03). NEVER raises:
    # every failure becomes a FAULT that the classifier maps to exactly one T-row.
    try:
        fd = os.open(name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK, dir_fd = pfd)
    except FileNotFoundError:
        return ABSENT                       # the ONE and ONLY definition of "does not exist" inside observe()
    except OSError as exc:
        return FAULT(kind(exc))             # EACCES/EIO/ELOOP/ENAMETOOLONG/… → FAULT, never ABSENT
    try:
        st = os.fstat(fd)                   # identity of the object the DESCRIPTOR pins — a value, never a path
        if not stat.S_ISREG(st.st_mode): return FAULT("NOT_REGULAR")
            # O_NOFOLLOW already refuses a symlink; O_NONBLOCK makes a substituted FIFO open instead of blocking;
            #   a directory/socket/device is refused here. No artifact of this design is anything but a regular file.
        if st.st_size > max_bytes: return FAULT("TOO_LARGE")            # advisory; the read cap below is authoritative
        h = sha256(); buf = bytearray()
        while True:
            chunk = os.read(fd, CHUNK_BYTES)                            # ≤ 65,536 B per read (Domain C, §6.6)
            if not chunk: break
            h.update(chunk); buf += chunk
            if len(buf) > max_bytes: return FAULT("TOO_LARGE")           # bounded read: memory ≤ max_bytes + CHUNK_BYTES
        if len(buf) != st.st_size: return FAULT("SIZE_CHANGED")          # grew/shrank mid-read ⇒ concurrent writer
        return Snapshot(bytes(buf), h.hexdigest(), len(buf), st)
    except OSError as exc:
        return FAULT(kind(exc))
    finally:
        os.close(fd)

function STAT_COMPONENT(pfd, name) -> ABSENT | FAULT(kind) | PRESENT(mode, st):
    # Presence/type fact only — for DIRECTORY-shaped names (final, staging, quarantine). Never used to claim content.
    try:    st = os.stat(name, dir_fd = pfd, follow_symlinks = False)
    except FileNotFoundError: return ABSENT
    except OSError as exc:    return FAULT(kind(exc))
    return PRESENT(st.st_mode, st)
```

Why this closes V17-03, point by point: (1) **existence and content are one operation** — the `open` decides presence
and the descriptor read yields the bytes, so a receipt cannot be "present" for one check and "different" for the next;
(2) **the fd pins the inode** for the whole read, so a concurrent rename or unlink cannot change what we read, and POSIX
keeps the bytes valid even after a post-read unlink; (3) **the digest is over exactly the bytes returned**, so
`snap.sha256 == receipt_pin` authenticates the very bytes that `parse_strict` then consumes (v1.7 hashed a buffer and
then parsed a path-derived object — two objects, one claim); (4) **type, symlink and size attacks** resolve to
`FAULT` → T3 rather than to a parse or a crash; (5) **the classification is frozen**: a receipt appearing or changing
after step 0 cannot flip this observation's T-row (it changes only the NEXT observation's, which is the honest
semantics), so T4↔T6 oscillation inside a single call is impossible; (6) **memory stays bounded** at
`max_bytes + CHUNK_BYTES = 196,608 B` for the receipt, inside Domain C (§6.6).

The classification helper (normative, V16-02/D32) — NEVER raises; used at EVERY quarantine site inside `observe()`:

```
function TRY_QUARANTINE(name) -> CONFLICT | QUARANTINE-FAILED:   # observe()-internal; never raises (V16-02)
    try:
        publish_quarantine_of(name)            # renameat2(NOREPLACE), identity_source = OBSERVED (§5.2): name →
                                               #   <run_id>.unverified; §5.5; whatever stands there is moved
        return CONFLICT                        # moved aside; the conflict signature now stands (K1/K8)
    except PublishConflict:
        return CONFLICT                        # EEXIST: an unverified sibling already exists — also a conflict
    except (PublishUnavailable, PublishIdentityMismatch, OSError):
        return QUARANTINE-FAILED               # EPERM/EIO/ENOSPC/EXDEV/ENOSYS/… — classified, never propagated
```

Seal-time quarantine (§5.2 step 5, D28/V15-05) is NOT routed through this helper: there a failed impostor quarantine
is strictly fatal by design. The helper covers only `observe()`'s two quarantine sites (V16-02): every outcome becomes a
deterministic fail-closed terminal state — CONFLICT keeps the conflict flag, QUARANTINE-FAILED resolves T5 — so no
`EEXIST`/`EPERM`/`EIO`/`ENOSPC` can escape `observe()` as an exception.

9.2.2 **Normative `OBSERVE()` (v1.8: one frozen snapshot per artifact; no second presence check, no path read).**

```
function OBSERVE(run_id, pin | None, egress_count | None, receipt_pin | None, journal_pin | None) -> TerminalState:
    # ---- 0. FROZEN FACT SNAPSHOT (V17-03/R5): each name is opened AT MOST ONCE; every branch below reads these ----
    snap_journal = snapshot(pfd, f"{run_id}.refusal.json", JOURNAL_MAX_BYTES)     # content: ABSENT | FAULT | Snapshot
    snap_receipt = snapshot(pfd, f"{run_id}.receipt.json", RECEIPT_MAX_BYTES)     # content: ABSENT | FAULT | Snapshot
    fin = stat_component(pfd, run_id)                                             # presence/type: ABSENT|FAULT|PRESENT
    stg = stat_component(pfd, f".{run_id}.staging")
    qre = stat_component(pfd, f"{run_id}.unverified")
    q_pre = qre is PRESENT                        # pre-existing quarantine (K8 / a prior K-row)
    # `.receipt.tmp` is DELIBERATELY not observed: a crashed pre-publication temp must never change the T-row (K12).
    # 1. refusal journal
    if snap_journal is not ABSENT:
        if snap_journal is FAULT:                        return T3     # unreadable ⇒ never T0 (§9.2.0(4))
        j = parse_strict(snap_journal.bytes)             # exact 9-key set, exact types, journal_digest verified
        if j is None or j.format != "obs-refusal/1":     return T2     # torn/invalid JSON ⇒ the crash signature
        if journal_pin is None or snap_journal.sha256 != journal_pin:
                                                         return T3     # V16-01: journal_pin MANDATORY (D31)
        if fin is FAULT or stg is FAULT or qre is FAULT: return T3     # the artifact set could not be established
        if fin is PRESENT or stg is PRESENT or q_pre or snap_receipt is not ABSENT:
                                                         return T3     # refusal ∧ artifacts/receipt/quarantine
                                                                       #   contradiction (orphan receipt: R6)
        return T0
    # 2. final run directory
    if fin is PRESENT:
        if not stat.S_ISDIR(fin.mode):                   return T3     # symlink/file under <run_id> is an impostor
        conflict = q_pre
        if stg is FAULT or qre is FAULT:                 return T3      # unverifiable sibling set ⇒ fail closed
        if stg is PRESENT:                                # stale sibling (K1/K8); T unchanged when it moves:
            qc = try_quarantine(f".{run_id}.staging")     # V16-02: NEVER raises — every outcome classified
            if qc is QUARANTINE-FAILED:                  return T5      # final + UNMOVABLE stale staging (§9.3 T5)
            conflict = True                               # CONFLICT: moved aside, or an unverified sibling exists
        # Verification-failure precedence (V14-06, restated v1.7): K8's foreign final cannot authenticate against our
        # pin and fails load/audit → T5 + conflict report; an own final failing with no conflict → T3. A final that
        # PASSES verification ignores `conflict`, so re-observation of a run whose stale sibling was quarantined stays
        # T4/T1/T6. With no out-of-band pin the two cases are indistinguishable AND unverifiable: both fail closed
        # before any load (V15-04) — stated limit (§10.1).
        if pin is None:                                  return T5 if conflict else T3
        run = load_run(final, pinned = pin)              # receipt_pin is a hex string — never passed as a pin
        if run fails structurally:                       return T5 if conflict else T3
        # ---- receipt: ONE snapshot, authenticated over the EXACT bytes that will be parsed (R3 ∧ V17-03) ----
        if snap_receipt is ABSENT:
            receipt = None                               # no receipt at all ⇒ T4 candidate (preconditions below)
        elif snap_receipt is FAULT:
            return T3                                    # unreadable / not regular / > RECEIPT_MAX_BYTES ⇒ T3
        else:
            if receipt_pin is None or snap_receipt.sha256 != receipt_pin:
                return T3                                # V16-01/D31: MANDATORY pin over the snapshot bytes;
                                                         #   self-digest alone never grants T1/T6
            receipt = parse_strict(snap_receipt.bytes)   # the SAME immutable bytes ⇒ no re-read, no drift, no TOCTOU
            if receipt is None or receipt.run_id != run_id:            return T3   # torn/foreign receipt
            if receipt.manifest_sha256 != pin:                         return T3   # content chain broken (pin non-None)
        # wrapper_count: exactly two admissible INDEPENDENT sources (V15-03) — the out-of-band `egress_count`
        # (§10.1(1b)) and `receipt.wrapper_count` from an AUTHENTICATED receipt (R3). Structural derivation is BANNED.
        wc = egress_count if egress_count is not None else (receipt.wrapper_count if receipt is not None else None)
        # R4 (V16-06/D36): mirror of audit check (g) BEFORE audit_run — supplied, integer-not-bool, == len(records)
        if not isinstance(wc, int) or isinstance(wc, bool) or wc != len(run.records):
            return T5 if conflict else T3
        result = audit_run(..., wrapper_count = wc, abort_seq = abort_condition_seq(run.records), ...)
        if not result.ok:                                return T5 if conflict else T3   # only a TOCTOU change lands here
        if receipt is None:                              return T4    # snapshot ABSENT ∧ pin ∧ audit pass ∧ wc from
                                                                     #   egress_count (V16-03/V16-06 preconditions)
        if egress_count is not None and receipt.wrapper_count != egress_count:
            return T3                                    # independent egress sources disagree (V15-03)
        if receipt.outcome == "ABORTED":                 return T1    # authenticated (R3) and count-cross-checked
        if receipt.outcome in {"COMPLETE-VALID", "INCONCLUSIVE-TIMING", "FAILED"}: return T6
        return T3                                        # outcome outside the closed enum (V14-06)
    # 3. no final
    if fin is FAULT:                                     return T3    # presence could not be established
    if snap_receipt is not ABSENT:                       return T3    # ORPHAN receipt (R6): CP3 cannot precede CP1
    if stg is FAULT:                                     return T3
    if stg is PRESENT:
        if not q_pre:
            if qre is FAULT:                             return T3
            try_quarantine(f".{run_id}.staging")         # V16-02: never raises; T5 on EVERY outcome
        return T5                                        # staging present → T5 always (K1/K7), fail closed
    if q_pre:                                            return T5    # pre-existing quarantine alone (stale K-row)
    return T2                                            # nothing trustworthy (incl. journal absent)
```

The v1.7 defects this replaces, concretely: `raw = read_bytes(receipt_path) if receipt_exists(run_id) else None`
performed a presence check and a PATH read that could disagree, authenticated a byte string that was then re-parsed
into a different object, and left a second `if not receipt_exists(run_id): return T4` AFTER the audit — so a receipt
appearing during the audit flipped T4 to T1/T6 mid-classification, and a receipt disappearing flipped T1/T6 to T4.
`snap_receipt` is now read once, before anything else, and the T4/T1/T6 decision uses that single frozen value.

9.3 **T0–T6 resolver table (exhaustive; every state is exactly one row):**

| T | Name | Defining persisted state (all conditions) | Exit | Recovery allowed |
|---|---|---|---|---|
| T0 | REFUSED | valid `obs-refusal/1` (read through ONE snapshot, §9.2.1) ∧ `journal_pin` supplied ∧ sha256(journal snapshot bytes) = `journal_pin` (V16-01) ∧ no final ∧ no staging ∧ no quarantine ∧ no receipt (an orphan receipt is a contradiction → T3, R6) | 2 | none (terminal) |
| T1 | ABORTED-SEALED | final ∧ verify+audit pass ∧ receipt valid (incl. `receipt_pin` supplied ∧ sha256(receipt bytes) = `receipt_pin`, V16-01) ∧ `receipt.outcome = ABORTED` (incident ladder, N/T/E rows, or signal reason) | 1 / 130 / 143 | none; owner reports to reviewer before rerun |
| T2 | INCONCLUSIVE-CRASH | nothing for `run_id`, or journal present, READABLE and torn/invalid JSON (`parse_strict` → None), or (power loss) rename lost before CP2 — an UNREADABLE journal is not a crash signature and resolves T3 | 1 | none automatic: rerun is a NEW `run_id` |
| T3 | FAILED-AUDIT | final present that fails verification — including a final presented with no out-of-band manifest pin, fail-closed V15-04 — with NO staging/quarantine conflict ∨ receipt invalid (snapshot FAULT: unreadable, non-regular or > `RECEIPT_MAX_BYTES`; torn/foreign; digest-or-pin mismatch; `receipt_pin` absent or mismatched V16-01; `wrapper_count` disagreement V15-03; outcome outside the enum) ∨ a receipt PRESENT with no final (orphan, R6) ∨ refusal present with `journal_pin` absent or mismatched (V16-01) or with an unreadable journal snapshot ∨ refusal ∧ artifacts/receipt/quarantine contradiction ∨ a presence FAULT that prevents establishing the artifact set (R5) | 1 | none; quarantine-or-report per reviewer |
| T4 | SEALED-UNRECEIPTED | final ∧ pin supplied ∧ verify+audit pass (incl. check (g): `egress_count` supplied, integer, `== len(records)` — V16-06) ∧ receipt snapshot ABSENT (§9.2.1 — ONE open established the absence; no pin ⇒ T3/T5, never T4 — V15-04; no admissible independent count ⇒ T5/T3, never T4 — V16-06) | 1 | NONE — TERMINAL incomplete state requiring operator review (v1.7, V16-03/D33): no CP1-durable receipt draft exists, so no code path may write/fsync/publish a receipt after CP1; a rerun uses a new `run_id` |
| T5 | QUARANTINED | staging found without final (K1/K7), or `<run_id>.unverified/` present with final absent (any K-row/`INVALID-PACING`/seal failure/E11/N14 path), or final present that fails verification while staging/quarantine is also present (K8 conflict, reported), or final present whose stale staging sibling cannot be moved aside (`try_quarantine` → QUARANTINE-FAILED, V16-02), or a final presented without its manifest pin while a conflict exists (V15-04 fail-closed) | 1 | none (fresh `run_id` for a rerun) |
| T6 | COMMITTED | S holds (§2.4 — incl. `receipt_pin` supplied ∧ sha256(receipt bytes) = `receipt_pin`, V16-01); `receipt.outcome` ∈ {COMPLETE-VALID, INCONCLUSIVE-TIMING, FAILED} | 0 / 1 / 1 | none |

Exhaustiveness argument (v1.5, V14-06; extended v1.6 for V15-03/V15-04; v1.7 for V16-01/V16-02/V16-06; v1.8 for
V17-03): the inputs are the five filesystem artifacts (refusal, staging, final, receipt, quarantine), each observed as
THREE possible facts — ABSENT / PRESENT with a frozen Snapshot / FAULT(kind) (§9.2.1) — receipt validity (torn / foreign
/ digest-or-pin mismatch / `receipt_pin` absent / valid) and the closed outcome enum (three values ∪ invalid), plus the
out-of-band inputs `pin`, `egress_count`, `journal_pin`, `receipt_pin` (present/absent each — V15-04/V15-03/V16-01)
and both quarantine outcomes (CONFLICT / QUARANTINE-FAILED, V16-02). FAULT is folded deterministically and adds NO new
state: it resolves T3 for every name except a READABLE-but-torn journal, which is the crash signature → T2. Steps 1→5 partition them: refusal present →
T0 (valid ∧ `journal_pin` present ∧ byte-matched ∧ no artifacts) / T2 (torn) / T3 (`journal_pin` absent or mismatched,
or artifacts/quarantine contradiction); refusal absent ∧ final present → T5 (staging sibling unmovable —
QUARANTINE-FAILED — or verification × conflict; `pin` absent fails closed before any load — never T4/T6) / T4 (receipt
absent ∧ pin supplied ∧ `egress_count` admits check (g)) / T1/T6 (authenticated receipt × outcome; `receipt_pin` absent
or mismatched → T3) / T3 (invalid/unauthenticated receipt, `egress_count` vs `receipt.wrapper_count` disagreement, or
enum); refusal and final absent ∧ staging present → T5 (every quarantine outcome, V16-02); only quarantine present →
T5; nothing → T2. The V15-05 residual (a final whose step-5 quarantine rename failed) is exactly a final that fails
verification → T3 (or T5 with a conflict) — never T4/T6, never a silent success. Each combination hits exactly one
`return` and maps to exactly one table row; G-V14-06 enumerates the full cross-product (all four out-of-band inputs,
both quarantine outcomes) and asserts pseudocode result == row predicate.

9.4 **Protocol v0.5 outcome → record/persisted representation mapping (concrete).**

| Protocol outcome (§6/§7.4) | Record-level representation | Receipt field | T / exit |
|---|---|---|---|
| COMPLETE-VALID | all records `status=200`, no abort (`abort_condition_seq → None`), all boundaries recorded, skips (if any) verified, TIMELINE_END present | `outcome="COMPLETE-VALID"` | T6 / 0 |
| INCONCLUSIVE-TIMING | ≥ 1 expected boundary in `boundary_skips` (`SYNC-SKIPPED`) ∧ or group-level verified `MISSED-WINDOW` decisions; kept TIMING-INVALID groups are ordinary records (judged by V1–V4 at analysis) | `outcome="INCONCLUSIVE-TIMING"` + skip counts | T6 / 1 |
| FAILED | `REFERENCE-MISSING` (ref group sent, body lacks the `+180 s` row), post-sweep mismatch, or UNBOUNDED sample — all visible in complete records/bodies | `outcome="FAILED"` + reason | T6 / 1 |
| ABORTED (incident) | records END at the abort: `derived = abort_condition_seq(records) = abort_seq = len(records)` for B1/B2/B3; `derived = None, abort_seq = len(records)` for B5/B6/N9/E12 | `outcome="ABORTED"`, `reason` ∈ {HTTP-<s>, INCIDENT-NETWORK, INCIDENT-CANCEL, INCIDENT-MEMORY, INCIDENT-RESPONSE, SIGNAL-INT, SIGNAL-TERM, TRANSPORT-EXCEPTION} | T1 / 1·130·143 |
| ABORT (INCIDENT-NETWORK) | exactly the 3rd consecutive `status=None` record as last record | `reason="INCIDENT-NETWORK"` | T1 |
| ABORT (INCIDENT) family | non-200 record (N5/N11/N13), weight/shape/open-time violations (N9/N12), server-time reversal (T5) | `reason` per row | T1 |
| TIMEOUT (protocol) at the 17 s deadline | harness `error="DEADLINE"`, duration ∈ [17 s, 18 s]; protocol TIMEOUT ≡ {DEADLINE, TIMEOUT, CONNECT_ERROR} for classification | `reason` not set (group/boundary TIMING-INVALID at analysis) | contributes to N6 streak; else T6/T1 |
| MISSED-WINDOW | NO records for the skipped group; `AdmissionDecision` + DECISION event (`decided_at_ns`, `m_e_ns`, chain-bound); rest of boundary unsent | `skips[]` summary | audit (f) verified → T6/T1 |
| SYNC-SKIPPED | NO records for the boundary; `boundary_skips[boundary] = "SYNC-SKIPPED"` | `boundary_skips` summary | T6 (or INCONCLUSIVE-TIMING) |
| SYNC-INADEQUATE-AT-START | sync group records only (`record_count > 0` in journal) | refusal `reason` | T0 / 2 |
| INVALID-PACING | audit (a)–(g) failure at self-verification (or `INVALID-PACING` found by `observe()` on a published run) | (pre-publish: quarantine note) / `reason` | T5 (pre) / T3 (post) |
| REFERENCE-MISSING | 200 record of the `ref` group whose body lacks the expected candle | analysis output in receipt | T6 with `outcome=FAILED` / 1 |
| TIMING-INVALID (group) | ordinary records; invalidity computed by the analysis function from timestamps + server bodies (V1–V4), never written into records | analysis lists group keys | T6 (never counted in lag) |

## 10. Provenance, pin, outer index

10.1 **Pin discipline and out-of-band egress count (three pins + one scalar; v1.7 / V14-05, V15-03/V15-04, V16-01).** (1) `write_run` returns `sha256(manifest.json)`; the runner
(a) prints it with a flush before CP1, (b) embeds it in the receipt at CP3, and (c) requires the operator to record it
out-of-band (committed evidence file / ticket) before review. (1b) The runner also prints, with a flush beside the manifest pin (same moment, before CP1), the
out-of-band egress count `egress_count = transport.sent` — the transport's wrapper counter, final once sealing starts.
This is the first admissible independent `wrapper_count` source for `audit_run`/`observe()` (V15-03): live runs pass
`transport.sent` directly (§5.4); `observe()` uses the printed `egress_count` when supplied, else the
AUTHENTICATED `receipt.wrapper_count` (§9.2 R3, V16-01); a count derived from the record stream is banned (audit
check (g), audit.py:289–296), and disagreement between the two independent sources resolves T3 (§9.2). (2) After CP3e (§5.2.4 step 9) the runner prints `snap.sha256` — the SHA-256 of the bytes READ BACK from the
published `<run_id>.receipt.json`, which CP3e has already proved equal to the digest computed while writing, with a
flush — the receipt pin; v1.7 printed the digest of the intended bytes at CP3 instead, before any read-back. `observe()` **REQUIRES**
`receipt_pin`: absent → T3, byte-SHA-256 mismatch → T3 — T1/T6 are unreachable without it (V16-01/D31);
`receipt_pin` is NEVER used as a manifest pin — a final without `pin` fails closed before any load (§9.2, V15-04).
(3) After refusal step 5 the runner prints `sha256(<run_id>.refusal.json bytes)` with a flush — the journal pin
(§9.1); `observe()` **REQUIRES** `journal_pin`: absent → T3, mismatch → T3 — T0 is unreachable without it
(V16-01/D31). `observe()` takes the pins as inputs; none is ever derived from the file being verified when
authentication (not mere structure) is claimed. The self-digests (`journal_digest`, `receipt_digest`) are
tamper-evidence only — anyone with `RUN_ROOT` write access can recompute them — while the out-of-band prints
are what make recomputation detectable, and v1.6's optional-pin reading (self-digest alone → authoritative T0/T1/T6)
is REMOVED: without the matching out-of-band print there is no authoritative state, only T3 (V16-01). Stated limits,
unchanged from `runstore`: whoever controls records, log, files AND pins together can forge a consistent set;
whoever controls only `RUN_ROOT` can edit files but not pins the operator recorded elsewhere.

10.2 **`obs-outer-index/1` (receipt) exact key set** (strict parse, exact types, no duplicates — same discipline as the
manifest): `format, run_id, plan_sha256, manifest_sha256, record_count, event_count, wrapper_count, abort_seq,
terminal_state, outcome, reason, exit_code, lifecycle, started_utc, ended_utc, timeline_end_ns, python_version, platform,
commit_sha, working_tree_clean, admitted_decisions, skip_summary, boundary_skips, memory {retained_total, transient_peak,
budgets}, diagnostics {late_wakes, weight_max_seen}, receipt_digest`. It is a sibling published by §5.2.4; it MUST NOT be
stored inside the run directory (it must remain individually no-replace publishable and independently stat-able for T4).
`receipt_digest = sha256(canonical of all the other receipt keys)` — the manifest self-digest discipline (V14-05):
the strict parser recomputes it, and after CP3e the runner prints the receipt's byte SHA-256 out-of-band (§10.1),
which `observe()` verifies against the SAME immutable snapshot bytes it then parses (V17-03). The key set is unchanged
by v1.8 — no version field is added (R-4) — and the file is bounded by `RECEIPT_MAX_BYTES = 131,072 B` (§12), which the
snapshot enforces before a single byte of it reaches the parser. `wrapper_count` is minted from `transport.sent` at CP3
and is the second admissible independent egress source (§10.1(1b), V15-03).

10.3 **Frozen schemas:** `records.jsonl` object keys = `_RECORD_KEYS` (12 keys, exact); `events.jsonl` keys = `_EVENT_KEYS`;
`manifest.json` keys = the 8 manifest keys; refusal and receipt keys as specified above. Any new detail belongs in the
free-form `error` string (records) or the receipt's `reason`/`diagnostics` (protocol §0/§3.3 alignment: record shapes stay
frozen under `obs-run-manifest/1`).

## 11. Gates and decisions (v1.9 adds G-V18-01–03 and D43–D45; v1.8 adds G-V17-01–04 and D38–D42; v1.7 adds G-V16-01–07 and D31–D37; v1.6 adds G-V15-01–07 and D24–D30; v1.4 additions; v1.3 G-R1–G-R12, D1–D10 remain in force where still applicable)

| Gate | Assertion | Killer-test sketch |
|---|---|---|
| G-V13-01 | ladder branch order == `abort_condition_seq` order | generate record streams hitting B1/B2/B3/B4 boundaries (non-200 mid-streak; `CANCEL_FAILED` with `status=None`; streak 2→3; 200 reset); assert runner abort `seq` == `abort_condition_seq` result; mutation: swap B1/B2 → must fail |
| G-V13-02 | exact syscall arguments | fake libc records `(pfd, b".<id>.staging", pfd, b"<id>", 1)`; component names with `/`, `..`, `\0` rejected pre-call; EEXIST → `PublishConflict` |
| G-V13-03 | identity checks + no fallback | spy asserts `os.rename`/`os.replace`/`os.link`/`shutil.move` NEVER called during publish; parent-path swap (fstat≠stat) aborts; ENOSYS/EINVAL → `PublishUnavailable` (no fallback path exists); post-rename inode mismatch quarantines the published name, then raises (V14-07) |
| G-V13-04 | budgets | chunk loop at `budget−1 / budget / budget+1` bytes; 4 MiB+1 response; §6.5 three-phase peaks pinned to ≤ 8,781,824 / 151,552 / 11,202,224 B under the 12,582,912 B budget (measured 8,396,848 / 147,848 / 11,186,544 B interposed, A.2; v1.7 campaign 8,724,640 / 148,113 / 11,196,453 B, V15-07); gzip bomb hits 1000:1 and 50 MiB ceilings; mutation: remove chunk check → killer fails |
| G-V13-05 | pseudocode conformance | instrumented clock counts reads: exactly one per admission iteration and predicate-read == `start_ns`; GV-6 loop wakes twice and starts at `300,030,003,001 ns`; interrupt flag set between iterations → no record |
| G-V14-01 | doc anchors match the branch | CI: the §0 anchor commit == HEAD of `impl-obs-harness-provenance`; `git diff <anchor> -- tools/obs/` empty for the doc-only-claim window; `audit.py:70` still opens `def abort_condition_seq` |
| G-V14-02 | streaming writer byte-equality + fsync order | randomized records (4 MiB body, unicode, escapes): §5.1.1 output == `_lines([record_to_json…])` byte-for-byte; spy asserts fsync order F1–F4 before return and that no allocation ≥ one whole line/file occurs; crash injection at each write/fsync → K2–K7 state |
| G-V14-03 | three-phase peak bounds | allocation spy: request-conversion moment ≤ 8,781,824 B, seal ≤ 151,552 B, verify line parse ≤ 11,202,224 B, budget 12,582,912 B (measured proofs §6.5, V15-07); mutation: materialize one full line at seal or one full file → killer fails; `pacer.records` released before `load_run` (single-copy Domain A) |
| G-V14-04 | clock API conformance (V14-04) | AST/grep gate: pseudocode mentions only `now_ns` / `sleep_until_ns`; instrumented Clock raises on any other name; asserted `sleep_until_ns` target ∈ [now, start_at]; GV-6 loop still starts at `300,030,003,001 ns` |
| G-V14-05 | receipt/journal integrity | flip one byte in the receipt → digest mismatch → T3; recompute digest but not the out-of-band pin → pin mismatch → T3; same for the refusal journal (torn → T2, forged-with-recomputed-digest → T3); mutation: drop the digest/pin check → killer fails |
| G-V14-06 | resolver/table agreement | property test enumerates refusal × staging × final × receipt(torn\|foreign\|digest\|pin\|valid) × quarantine × outcome enum × `pin`/`egress_count`/`journal_pin`/`receipt_pin` present/absent × quarantine outcome (CONFLICT/QUARANTINE-FAILED): pseudocode returns exactly one T and §9.3's row predicate matches; K8→T5, quarantine-only→T5, torn receipt→T3, unknown outcome→T3, refusal+quarantine→T3, final without `pin`→T3/T5 never T4/T6, refusal without `journal_pin`→T3, receipt without `receipt_pin`→T3, `egress_count`≠`receipt.wrapper_count`→T3, unmovable stale staging→T5 pinned |
| G-V14-07 | TOCTOU + filesystem boundary | `RUN_ROOT` mode 0777 → refuse; symlink final component → `O_NOFOLLOW` open fails; spy swaps the staging name between stat and renameat2 → step-5 mismatch → published final quarantined (never left standing); content swap between §5.4 and CP1 → CP1b → quarantine → T5 |
| G-V14-08 | 250 ms second-signal bound | subprocess: injected `fsync` sleeping 2 s inside CP2 + second SIGINT → exit 130 at 250 ± 50 ms, final present, no receipt → `observe()` T4; fast checkpoint → exit after bookkeeping < 250 ms → T6; non-checkpoint second signal → immediate exit; a third signal does not extend the bound |
| G-V15-01 | metadata-only seal (V15-01) | allocation spy + AST gate over a full `MAX_BODY_BYTES` record: the writer calls `record_meta_json` only — `record_to_json`/`r.body` never referenced — and never materializes `body_b64`; seal peak ≤ 151,552 B; mutation: reintroduce `record_to_json(r)` → killer fails (measured 5,592,408 B string ×2 per record) |
| G-V15-02 | incremental `load_run` (V15-02) | spy: reads ≤ 64 KiB chunks (no `read_bytes`/whole-file), lines bounded by `f.readline(MAX_LINE + 2)`, digest pass precedes parse (Step-1 error precedence), per-line release order enforced; verify peak ≤ 11,202,224 B on a `MAX_LINE` line; mutation: hold bytes + str + parsed together → killer fails (measured 16,781,149 B) |
| G-V15-03 | independent egress count (V15-03) | `wrapper_count` sourced only from the `egress_count` print or `receipt.wrapper_count`; mutation: derive it from the record stream → check-(g) tautology detector kills; injected disagreement → T3; neither source → T5/T3 |
| G-V15-04 | pin fail-closed (V15-04) | resolver property test (G-V14-06 dimensions): final with `pin = None` → T3/T5, never T4/T6, no CP2/CP3; grep gate: `receipt_pin` never called as a function and never passed as `pinned_manifest_sha256` |
| G-V15-05 | fatal quarantine (V15-05) | inject EPERM/ENOSPC into the step-5 impostor quarantine rename → `PublishIdentityMismatch` raised with cause chained (no `except: pass`), runner dies before CP1b/CP2/CP3, no receipt; observe() on the leftover state → exactly one T-row (T3/T5); spy asserts the impostor never classifies T4/T6 |
| G-V15-06 | same-UID trust boundary (V15-06) | `RUN_ROOT` not owned by `os.geteuid()` or group/other-writable → `PublishUnavailable` at lock, before any artifact; fstat/stat UID+mode proof asserted; doc gate: §5.2.5 states kernel-prevention (different-UID) vs detection (same-UID) explicitly |
| G-V15-07 | 12 MiB budget proof (V15-07) | tracemalloc CI gate: three phase peaks ≤ 8,781,824 / 151,552 / 11,202,224 B under 12,582,912 B, with the §6.5 measured values recorded; mutations: whole-file read, retained-chunk loop, or held `json.loads(bytes)` buffer → killer fails |
| G-V16-01 | mandatory out-of-band pins (V16-01) | resolver property test (G-V14-06 dimensions): refusal with `journal_pin = None` or one flipped byte → T3, never T0; receipt with `receipt_pin = None` or flipped byte → T3, never T1/T6 — a CORRECTLY RECOMPUTED self-digest does not help; grep gate: the old optional-pin form (`journal_pin is not None and …` / `receipt_pin is not None and …`) absent from §9.1/§9.2; mutation: restore an optional-pin check → killer fails |
| G-V16-02 | catch-and-classify quarantine (V16-02) | inject EEXIST/EPERM/EIO/ENOSPC/EXDEV/ENOSYS into BOTH `observe()` staging-quarantine sites → `observe()` returns exactly one T-row and NEVER raises (final + unmovable staging → T5 immediately; staging-only → T5 on every outcome); spy: no quarantine exception crosses the `observe()` boundary; seal-time step-5 impostor quarantine still raises fatally (D28 unchanged) |
| G-V16-03 | T4 terminal, no receipt reconstitution (V16-03) | AST/grep gate: no receipt `publish_file`/`fsync(pfd)` call reachable after CP1 outside the CP3 sequence; crash injection at K10/K11/K12 → `observe()` = T4 and STAYS T4 on every subsequent observation (idempotent, no CP2/CP3 completion, no receipt file ever appears); mutation: add receipt-republish recovery → killer fails |
| G-V16-04 | reproducible memory accounting (V16-04; instrument rules restated by V17-04/V18-03) | CI reruns the Appendix A protocol (`python -m tools.obs.probes.run_all --check`, CPython 3.12.3, deterministic inputs) → every recorded value must match A.2/A.3 (8,396,983 / 148,004 / 11,188,520 / 11,188,600 / 11,188,520 B tracemalloc; 8,396,848 / 147,848 / 11,186,544 B interposed), the banned `no_del` variant must still FAIL its bound, and `native_headroom`'s client-only request region must satisfy 214,120 B ≤ `HTTP_HEADROOM` with every A.5.8 inventory item inside its derived bound; a `mallinfo2` figure is REPORTED and never compared (A.5.3), a drifted value or a missing Appendix row fails the gate |
| G-V16-05 | loader precedence + dialect equivalence (V16-05) | differential test: for every input class (bad body on line 1 + bad keys on line 5; duplicate key; `NaN`; non-UTF-8; truncated; line > `MAX_LINE`; digest mismatch; count mismatch) assert Step-1's `load_run` and the new `load_run` raise the SAME `ManifestError` message at the SAME precedence position on the same bytes — sole exemption: lines > `MAX_LINE` (new rejects with the P-6 message, Step-1 accepts — D-04/D-05/D-21…D-23); mutation: decode a body before all-lines structure validation → killer fails |
| G-V16-06 | audit check (g) alignment (V16-06) | property test: every `wc` that reaches `audit_run` is `int` (not `bool`, not `None`) and `== len(records)` — the R4 mirror enforces it pre-audit; `wc` ∈ {absent, bool, str, ≠ len} → T5-with-conflict or T3, and `audit_run` is NEVER called with an invalid `wc`; ordering spy: an unauthenticated receipt's `wrapper_count` never reaches the audit (R3 before use); mutation: delete the R4 mirror → killer fails |
| G-V16-07 | receipt temp-inode binding (V16-07) | spy substitutes `.<run_id>.receipt.tmp` for a foreign file between `close(tmp_fd)` and `publish_file` → step-3 `expect` mismatch → publication refused BEFORE `renameat2` (or, for a swap after the step-3 stat, step-5 `PublishIdentityMismatch`) → CP3 fails → `observe()` = T4 (the real receipt never published) or T3 (foreign bytes standing under the final name fail `receipt_pin`) — NEVER T6; grep gate: §5.2.4 passes `expect = st_tmp`, never `expect = None` for a file target |

| G-V17-01 | loader contract, `MAX_LINE` and the differential corpus (V17-01) | (a) code/doc identity: `LOADER_CONTRACT_ID == "obs-loader/2"`, `LOADER_CONTRACT_SUPERSEDES == "obs-loader/1"`, and the §1.0/§5.1.2.0 literals agree; (b) `MAX_LINE == 4 * ((MAX_BODY_BYTES + 2) // 3) + FRAMING_ALLOWANCE_BYTES == 5,592,920` and `FRAMING_ALLOWANCE_BYTES == 512`, asserted at import, plus a measured worst-case framing ≤ 512 B; (c) boundary replay of §5.1.2.1 cases A–D asserting ACCEPT/ACCEPT/REJECT/REJECT with the exact cap message and line number; (d) the full corpus D-01…D-23 against the hash-pinned `legacy_loader.py` oracle, asserting identical outcome, identical message INCLUDING JSON positions (D-07 proves the P-9a terminator rule), identical `LoadedRun`/manifest, and equality on the legacy archive (D-18); (e) monotonicity over D-19: `accept(/2) ⇒ accept(/1)`, with the only permitted asymmetry being the cap class; (f) AST gate: no `read_bytes`, no `raw.split(b"\n")`, no `record_to_json`, and no `/1` fallback path reachable in the load path; mutations that MUST kill: parse the terminator-inclusive buffer (D-07 → `line 2 column 1`), remove the cap (D-04/D-05 accepted → 139.8 MB class returns), decode a body before all-lines structure (D-11/D-12), reorder digests after parsing (D-13) |
| G-V17-02 | creation-identity binding + CP3e (V17-02) | spy substitutes `.<run_id>.receipt.tmp` with a foreign file BETWEEN the step-3 `stat` and the `renameat2` call → step 5 compares `st_dst` to `fstat(tmp_fd)` → `PublishIdentityMismatch`, impostor quarantined, NO `receipt_pin` printed, `observe()` ∈ {T3, T4}, never T6; the SAME fixture with step 5 anchored on `st_src` (v1.7's rule) PUBLISHES the impostor — re-introducing that anchor MUST kill the gate; CP3e fixture: rewrite the published receipt in place before step 8 → `snap.sha256 ≠ receipt_sha_written` → CP3 fails, no pin printed; AST/grep gate: every `publish_file` call site passes a non-None `expect` and `identity_source = CREATION`, and `publish_quarantine_of` is the only `OBSERVED` caller; `st_nlink == 1` and `S_ISREG(st_tmp.st_mode)` asserted at step 4 |
| G-V17-03 | descriptor-relative receipt snapshotting (V17-03) | runtime spy: for every observation, exactly ONE `os.open` per artifact name through `pfd` and ZERO path-based reads/presence calls (`Path.read_bytes`, `open(path)`, `os.path.exists`, `os.lstat`, path `os.stat`); substitution matrix — replace the receipt with (i) absent, (ii) a symlink, (iii) a FIFO, (iv) a directory, (v) a `RECEIPT_MAX_BYTES + 1` file, (vi) foreign bytes, (vii) a swap immediately after the snapshot, (viii) a swap between the audit and the outcome branch — each yields exactly one T-row, (ii)–(v) → T3 via FAULT, (vii)/(viii) → the classification of the FROZEN snapshot (unchanged by the swap); orphan-receipt fixture (receipt, no final) → T3; peak memory of `snapshot` ≤ `RECEIPT_MAX_BYTES + CHUNK_BYTES`; mutation: reintroduce a second presence check or a path read → killer fails |
| G-V18-01 | explicit rejection policy for over-cap artifacts (V18-01) | (a) REACHABILITY, in this order: the hash-pinned `/1` oracle ACCEPTED fixtures D-21/D-22/D-23 — each is a valid 12-key record whose line content is 6,990,684 / 6,291,630 / > `MAX_LINE` B — and `/2` rejected each with `records.jsonl line {n} exceeds the maximum line length` at the right line number; the test FAILS if `/1` rejects a fixture (the reachability claim became vacuous) or if `/2` accepts one; (b) D-23 additionally asserts NONE of the bodies was decoded (P-6 precedes P-8: the cap is a file-level pre-parse fact); (c) AST/behaviour gate: no truncation, split, skip, retry-with-`/1`, tolerance flag, environment variable or keyword argument can change the verdict for an over-cap file — a mutation adding any of them MUST fail; (d) doc gate: §5.1.2.6 exists and contains the strings `REJECTION POLICY`, `CONFORMING`, `LEGACY-ADMITTED` and the 6,852 B / 697,196 B margin figures, and neither "impossible under the frozen schema" nor "proved unreachable" appears anywhere except inside an explicit retraction quotation (§5.1.2.1, §5.1.2.6 P7 — a grep gate) |
| G-V18-02 | the probe suite is delivered code, not prose (V18-02) | (a) `python -m tools.obs.probes.run_all --manifest` reproduces A.0's fourteen path/size/SHA-256 rows byte for byte, and `--check` exits 0 on the pinned interpreter; (b) every A.7 listing is byte-identical to the file it names IN THIS REVISION once this document's CRLF line separators are normalised (A.7 preamble; the modules are committed with LF) and A.0's rows are `--manifest`'s output, both GENERATED from `tools/obs/probes/` by script; the generation is a REVIEW-TIME step — the script is not part of the suite and CI does not diff the appendix — so a later drift of the DOCUMENT is caught by review, while `--check` catches drift of the FILES; stated as a residual, not claimed as automation (V20-15); (c) the driver REFUSES to run (exit 2) when any of the fourteen files is missing — a partially copied suite cannot silently narrow the protocol — and, since v2.0, when any file's size or SHA-256 differs from `expected.json`'s manifest (V19-05); and, since v2.2, when any entry in this directory is not a REGULAR FILE — a link (inside the tree, outside it or dangling), a directory, a FIFO, a socket or a device — so the fourteen files cannot be satisfied by a link to something else (V21-01); (d) `alloc_peak.so` is absent from the committed tree and the gate FAILS, not skips, when `cc` cannot build it; (e) README.md documents the run line, the TLS-fixture policy (committed fixture preferred, ephemeral `openssl` fallback otherwise) and the instrument limits — deleting any of the three fails |
| G-V18-03 | direct-`mmap` fence around the native term (V18-03) | (a) `alloc_peak.c` exports `alloc_peak_map_peak()` and its symbol table contains `mmap`, `mmap64` and `munmap` (build gate: `nm -D`); (b) `probe6` reports a `map_peak` for the request region and `run_all` compares the SUM `peak + map_peak` against `HTTP_HEADROOM`, failing when the interposer is unavailable instead of skipping; (c) the phases report their `map_peak` (0 B measured) and a phase whose channel exceeds `HTTP_HEADROOM` fails with the A.5.7 note that the malloc figure is no longer a usable bound; (d) a mutation that removes the mmap interposition MUST fail (a) and (b); a mutation that compares only the malloc channel MUST fail (b); (e) doc gate: A.5.4 contains the interception inventory (including `posix_memalign`/`aligned_alloc`/`brk` as NOT intercepted) and A.5.7 contains the acknowledgment, the measured channel table and the page-rounding lemma — deleting any of them fails |

| G-V17-04 | native instrumentation + repository probes (V17-04; channels extended by V18-03) | CI runs `python -m tools.obs.probes.run_all --check` (exit 0 required) on the pinned interpreter, asserting for every phase BOTH instruments: `tracemalloc` peaks (8,396,983 / 148,004 / 11,188,520 / 11,188,600 / 11,188,520 B) and interposed malloc peaks (8,400,920 / 147,848 / 11,186,544 B) within their §6.5 bounds, the banned `no_del` variant still FAILING its bound (5,656,528 B), byte equality at 8,511,232 B, and `native_headroom`'s client-only request region on BOTH channels — malloc 214,120 B plus direct `mmap` 0 B, SUM 214,120 B ≤ `HTTP_HEADROOM = 262,144 B` — plus the five A.5.8 inventory items, each inside its derived bound (77,864 ≤ 98,304 / 69,992 ≤ 86,016 / 0 ≤ 65,536 / 0 ≤ 65,536 / 168,048 ≤ 196,608); probe6's `mallinfo2` sample max is reported and NEVER compared (it is a lower bound — 105,072 B this revision against a 52,192 B end delta, the under-read A.5.3 documents); `HTTP_HEADROOM == 262,144` and the A.5.8 per-request item bounds sum to 253,952 ≤ it, while the four coarse A.5.7.4 terms plus one page of rounding each sum to ≤ 147,456 B; a probe file whose sha256 differs from A.0's manifest without a doc revision fails; doc gate: A.5 must contain the `uordblks`/`hblkhd`/`MMAP_THRESHOLD`/per-thread-arena/kernel-buffer clauses, the retraction sentence, the interception inventory (A.5.4) and the arena-granularity caveat — deleting any of them fails |

| G-V19-01 | thread-safe, fail-closed mmap accounting (V19-01) | (a) source gate: every mutation of `map_tab`/`map_used` and of the map live total occurs between `map_lock()`/`map_unlock()`; no `atomic_load`+`atomic_store` pair decrements a total (a CAS loop does); (b) a full table ABORTS, and only WHERE INTENDED — probe8 runs the child under `ALLOC_PEAK_MAP_SLOTS=64`, which the child's own measured baseline (3 interpreter regions) makes the exact capacity of 61 explicit mappings; the gate requires the flushed `MAPPED` line whose tracked count EQUALS the capacity, a table filled to exactly 64 ranges, `SIGABRT` (−6) rather than an exit code, and the single diagnostic line matched byte for byte including its `(tracked 64, capacity 64, live 2,363,392)` numbers; `ALLOC_PEAK_MAP_SLOTS=1` is deliberately NOT used, because the interpreter's startup mappings fill it before the probe's first mapping, which is how an earlier form of this check passed without ever reaching the abort; a negative control with the capacity unset must reach `SURVIVED` and exit 0; (c) probe8's concurrency phase: 8 threads × 64 iterations, the peak must be ≥ 8,388,608 B (all eight 1 MiB mappings live at the barrier — a lost update makes it smaller), the range table must return to its baseline live total and baseline entry count, and a leaked entry would have aborted the run; (d) mutation: restore the v1.9 load/store decrement or the silent drop → (b)/(c) fail |
| G-V19-02 | range-aware mapping bookkeeping (V19-02) | (a) probe8 A: map 12,288 B → `munmap` the middle page → live 8,192 B in TWO ranges → free the remaining pieces → live 0; (b) probe8 B: 8,192 B → `mremap(MAYMOVE)` to 32,768 B → live 32,768 B → `munmap` → 0 — an add-only or subtract-only implementation misses one of the two figures; (c) source gate: `mremap` is interposed and passes `MREMAP_FIXED`'s fifth argument, `MAP_FIXED` installs subtract the replaced range first, and adjacent ranges coalesce; (d) mutations: ignore partial unmaps, treat `mremap` as a no-op, or stop coalescing → (a)/(b) or the table-baseline check fail |
| G-V19-03 | native allocation inventory, derived and gated (V19-03) | (a) `expected.json` carries the five-item inventory (unit × count derivation and a bound per item) and `run_all.compare_inventory` computes each item from the measured stages and FAILS when it exceeds its bound, when a stage is missing, or when it falls below the one-page negative tolerance the two ~0 B items carry (allocator block reuse makes a few dozen bytes of peak-difference noise, and a stage that measured LESS by more than a page would mean the difference is not the consumer it claims to be); (b) `per_request_bound` (258,048 B) is asserted ≤ `HTTP_HEADROOM`; (c) the client-only region is the gated figure — the loopback server runs in its own process, so a probe that ever measured the server again would raise every stage and breach the bounds; (d) doc gate: A.5.8 contains the derivation column, the cold/warm split and the unenumerated-remainder arithmetic; deleting any of them fails |
| G-V19-04 | CI enforces the probe gate (V19-04) | (a) `.github/workflows/ci.yml` has a `probe-suite` job that pins CPython 3.12.3, compiles `tools/obs/probes/alloc_peak.c` with `-Wall -Wextra -Werror`, and runs `python3 -m tools.obs.probes.run_all --check --report artifacts/probes/report.json`; (b) the gate step's exit status survives the pipe (`PIPESTATUS`) and the job fails when the gate fails; (c) `probe-suite-evidence` (gate.log, manifest.json, report.json, build.log) and `alloc-peak-so` are uploaded with `if: always()`, so a red run still yields its raw output; (d) mutation: drop the build step, the gate step or the artifact upload → the workflow no longer proves anything and the gate fails on the missing artifact |
| G-V19-05 | machine-enforced suite manifest (V19-05) | (a) `expected.json` has `schema: obs-probes/2` and a `manifest.files` array with path, bytes and SHA-256 for every OTHER file; (b) `--check` refuses (exit 2) on a MODIFIED file (size or digest), an ADDED file and a DELETED file — all three demonstrated, each with a per-file diagnostic; (c) the refusal happens BEFORE any measurement, so a tampered suite cannot produce a passing report; (d) `--update-manifest` is the only writer and `--manifest` prints `expected.json`'s own digest, which A.0 pins; (e) mutation: replace `check_manifest` with an existence check → (b) fails |
| G-V20-01 | the `realloc`-failure regression is a GATED measurement (V20-11/V20-12) | (a) `probe6_native --realloc` exists and is exercised by `run_all --check` through the `realloc_accounting` row; (b) the row's clauses are conjunctive: child exit 0, `NULL` return, `errno == ENOMEM`, block byte-identical, block still writable, second block allocated, peak ≥ 8,388,608 B and ≤ 12,582,912 B; (c) demonstrated twice: 8,398,608 B on the shipped shim (all eight clauses true) and 4,200,608 B with the A.5.4 guard removed (the peak clause fails, so the gate fails); (d) the recorded peak is re-measured every run with `tolerance` 0.02, so a drift fails rather than passing on a stale figure; (e) mutation: delete the `if (p == NULL && size != 0) return NULL;` line → (c) fails |
| G-V20-02 | the manifest is validated as DATA, not matched by name (V20-14) | (a) every row must be an object with exactly `path`/`bytes`/`sha256`; `path` must be the canonical `tools/obs/probes/<name>`; duplicate paths and duplicate basenames are refused; `bytes` is a non-negative `int`, `sha256` is 64 lowercase hex; `expected.json` and `alloc_peak.so` may not be pinned; the block itself admits only `algorithm` (which must be `sha256`) and a non-empty `files` array; (b) demonstrated: twenty-three malformed manifests each produce exit 2 with a per-entry diagnostic while the real manifest validates — duplicate path, duplicate basename under another directory, bare basename, absolute path, `bytes` as `"1234"`/`-1`/`true`, short/uppercase/missing digest, unknown row field, non-object row, self-pin, artifact pin, `algorithm: md5`, stray block field, `files` not a list, empty `files`, wrong size, wrong digest, deleted row, and a missing or non-object block; (c) since v2.1, A.0 and A.7 are regenerated from the files by script, so this revision's appendix cannot claim a digest the file does not have (review-time: CI verifies the manifest, not the appendix — G-V18-02 b); (d) mutation: restore v2.0's basename indexing → the duplicate-path and basename cases are ACCEPTED (one row silently overwrites the other) and (b) fails |
| G-V20-03 | the map live total cannot be clamped (V20-13) | (a) source gate: `map_live_sub` contains no clamp (`cur > n ? ... : 0` is gone) and calls `map_fail_underflow(n, cur)`, which writes one diagnostic line with both figures and `abort()`s; (b) demonstrated with a FAULT-INJECTED build (one 4 MiB range silently removed from the table): `SIGABRT` (−6) and the byte-exact line `alloc_peak: FATAL: mmap accounting underflow: 4202496 B to subtract, 2121728 B tracked (regions 3): refusing to clamp to zero`, while the shipped build runs the same child to `SURVIVED` with `live` back at its baseline; (c) the path is NOT reachable from a correct shim, so it is verified by fault injection in review rather than shipped as a test hook — stated as a limit, not hidden: CI cannot provoke a lost range without a deliberate bug in the instrument; (d) mutation: restore the clamp → the injected build exits 0 with a silently reduced total instead of aborting |
| G-V21-01 | the suite's inventory is IDENTITY-based, not name-based (V21-01) | (a) `suite_files()` enumerates with `os.scandir` + `lstat` semantics and REFUSES any entry that is not a regular file; `check_manifest()` hashes each file through ONE `O_NOFOLLOW` descriptor and requires `os.path.samestat(lstat, fstat)` plus an unchanged size, so the bytes compared belong to the inode inspected; (b) `--self-test` runs fourteen cases and exits non-zero if ANY refusal is missing: post-enumeration substitution by a link to a file inside the suite, a link to a file outside it, a link added after the inventory, a dangling link, a link to `/dev/null`, a directory, a FIFO, a real character device, a direct `opened_regular` call on a link, `open(O_NOFOLLOW)` refusing with `ELOOP`, a modified file still refused — plus a CONTROL that an honest tree validates and that a regular file still hashes to its own bytes; (c) CI runs `--self-test` before the gate and archives `self-test.log`; (d) mutation: restore `os.listdir` + `os.path.isfile` → the link cases are ACCEPTED and (b) fails |
| G-V21-02 | the reported counts are three distinct counts, correctly named (V21-02) | (a) the success line names inventoried (14), pinned-by-`expected.json` (13) and `expected.json`-pinned-by-A.0 separately, and prints `expected.json`'s digest; (b) `report.json` carries `coverage.{inventoried, pinned_by_expected_json, self_path, self_sha256, self_pinned_by}` and those values EQUAL `len(manifest.files)` (14) and `len(expected.manifest.files)` (13); (c) demonstrated twice on the working tree this appendix pins, and v2.1's single-number line is recorded as wrong in §1.0c rather than silently replaced; (d) mutation: print one number for both → (a) fails |
| G-V24-01 | every child interpreter starts ISOLATED and SITE-FREE (V24-01) | (a) `probe_common.child_command()` is `[sys.executable, '-I', '-S', '-c', BOOTSTRAP]` for EVERY child — probe6's server/stage/`--realloc`, probe8's mmap child and capacity program, the `--interpose` driver — and no spawn site passes `-m` or a path; (b) the bootstrap's `isolated()` runs before it reads the parent's request and exits 86 unless `sys.flags.isolated`, `no_site`, `ignore_environment` and `no_user_site` are set, `site`/`sitecustomize`/`usercustomize` are absent from `sys.modules`, and no `sys.path` entry is the working directory; (c) `--self-test` proves it with REAL children in a working directory holding a hostile `sitecustomize.py`, `hashlib.py` and `ssl.py`: the hook does not run, `hashlib.__file__` is the standard library's, the payload digest still verifies, a child started without the flags is refused, and a CONTROL shows the same plant DOES run when the flags are removed; (d) mutation: drop `-I`, `-S` or the `isolated()` call → (b) and (c) fail (`a child started WITHOUT -I -S is refused`) |
| G-V23-01 | every child interpreter executes only manifest-verified bytes (V23-01) | (a) no mode of the driver and neither probe starts a child with `-m` or from a path: probe6's server, stage and `--realloc` children, probe8's mmap child and probe8's capacity program all start through `probe_common`, which sends the source over a pipe from the buffers `check_manifest(keep=…)` accepted, one frame per module carrying the SHA-256 `expected.json` promises for that file, and the child recomputes it before `compile()`; (b) the child's bootstrap is bound by digest (`sys.orig_argv` against the parent's `sha256(BOOTSTRAP)`) and its `tools.obs.probes` package is closed (`__path__ = []`), so a module the parent did not send cannot be imported from disk there; (c) `--self-test` demonstrates the properties with REAL children: a frame whose digest does not match is refused (exit 86) and never executed, a child runs the bytes it was sent while the path it names holds different source, a swapped bootstrap and a truncated payload are refused, and an unverified sibling cannot be imported; (d) the measurement semantics are unchanged and stated — fresh interpreter counted from exec, same `cwd`, same `sys.argv[0]`, same resets, module run as `__main__` — and the two figures the bootstrap moved are re-pinned with their reason; (e) mutation: restore `-m` at any spawn site → (a) fails and the substitution case (c) executes the disk copy |
| G-V21-03 | the lineage claim names its commit and its run (V21-03) | (a) the preamble names commit `e30ef37011af7cc073fa13c8ee5384ae080995b5`, run `42208989835`, job `127862655167`, conclusion `success`, the exact command and the exact printed lines; (b) A.0's fourteen digests equal the digests that run's `--manifest` step printed, so the claim is about those bytes and not about a nearby tree — independently checkable from the `probe-suite-evidence` artifact or `gh run view 42208989835 --log`; (c) the claim is SCOPED — it covers the ten measurements at that SHA, and says the v2.2 reporting line is a working-tree result until the next run prints it; (d) mutation: delete the run id, or widen the claim to "all output at e30ef37", → the sentence then contradicts that run's `gate.log` and fails review |

Decisions (new): **D11** dynamic target supplied as `target_fn` evaluated per admission read (static path retained);
**D12** on budget breach, discard the whole body (`b""` + `error=INCIDENT-MEMORY`) rather than persisting a partial one;
**D13** `TRANSIENT_BUDGET_BYTES` may be changed only together with the §6.5 derivation; **D14** recovery NEVER completes an
interrupted commit — pre-CP1 staging is always quarantined, and post-CP1 the run is TERMINAL-incomplete (T4, operator
review): v1.7 removed the old CP2/CP3 completion, no CP1-durable receipt draft exists (V16-03, D33); **D15** skip decisions → event log, admitted decisions →
receipt (§4.4); **D16** refusal journal is a `RUN_ROOT` sibling keyed by `run_id` (never inside a run directory);
**D17** `abort_seq` convention: live runs pass `pacer.abort_seq`, `observe()` re-derives via `abort_condition_seq` (§3.3.2);
**D18** `write_run` is REPLACED in Step 2 (same name/signature/return; descriptor-relative + streaming + fsync, §5.1.1;
byte-identical output; the old body survives only as the G-V14-02 reference serializer); **D19** `TRANSIENT_BUDGET_BYTES`
re-derived to 12,582,912 B from the three §6.5 phase peaks — any change re-derives all three; **D20** receipt and
refusal gain self-digests (`receipt_digest`, `journal_digest`) plus out-of-band byte-SHA-256 pins printed at publication;
**D21** CP1b content re-verification before CP3, and an identity mismatch quarantines the published final instead of
leaving it in place; **D22** a daemon `obs-watchdog` thread enforces the 250 ms second-signal bound during blocking
syscalls; **D23** resolver precedence: entry snapshot over five artifacts with steps 1→5, verification-failure
precedence (`conflict → T5`, else T3) and a closed receipt-outcome enum;
**D24** `load_run` is a bounded-pass incremental reader in FIVE stages (v1.7 restates this for V16-05 — v1.6's
wording claimed "Step-1 error precedence preserved" while its interleaved pass violated it): structure scan of ALL
lines (incremental sha256 + line facts + first structure error deferred, per-line dicts discarded), digest checks,
records structure-all-lines → records decode-all-lines (`f.readline(MAX_LINE + 2)`, normative release order
decode → release → parse → release → encode → release → `b64decode(bytes)`, decode re-hashes for TOCTOU), then events
the same, then count — Step-1's exact precedence (rec digest → ev digest → rec truncation → rec structure → rec decode
→ ev … → count) and its exact JSON dialect (`_no_duplicate_keys`, `parse_constant` rejection, normalization net); a
whole-file read or a held bytes/text/parsed triple is banned from verification (V15-02/V16-05);
**D25** the seal's writer is metadata-only (`record_meta_json`, 11 keys, never touches `r.body`) with byte-equal
`{`-head / `",`-tail framing (probe-verified against `_lines([record_to_json…])` incl. a 4 MiB body) and the JSONL
terminator; `record_to_json` is banned from the writer (V15-01);
**D26** `wrapper_count` comes only from the out-of-band `egress_count` print or `receipt.wrapper_count`;
disagreement → T3, neither → check (g) fails → T5/T3, structural derivation banned (V15-03);
**D27** `pin` is mandatory to verify or recover a final; `receipt_pin` is never a manifest pin; `pin` absent + final
present → T5/T3 before any load; no post-CP1 recovery exists at all — T4 is terminal (V15-04, V16-03/D33);
**D28** quarantine publication failure is strictly fatal (`PublishIdentityMismatch`, cause chained, never `except:
pass`); the runner dies before any receipt exists and the residual impostor can only resolve T3/T5 (V15-05);
**D29** filesystem trust boundary: different-UID writers are kernel-prevented (owner-only mode + `O_NOFOLLOW` +
fstat/stat identity re-proof), same-UID writers are inside the trust boundary and only detected (step-5 inode proof,
CP1b, pins → T3/T5) — stated, never claimed prevented (V15-06);
**D30** `TRANSIENT_BUDGET_BYTES = 12,582,912` is OFFICIAL against the §6.5 measured three-phase proofs; any change to
`MAX_BODY_BYTES`, the writer or the reader re-derives all three phases before the budget may change (V15-07);
**D31** all three out-of-band pins are MANDATORY: `journal_pin` for T0, `receipt_pin` for T1/T6, `pin` for any final
verification/recovery — pin absent or byte-SHA-256 mismatch → T3; self-digests (`journal_digest`, `receipt_digest`)
are re-checked as necessary but never sufficient for an authoritative state (V16-01);
**D32** every quarantine attempt inside `observe()` runs through `try_quarantine`, which never raises
(`PublishConflict` → CONFLICT; `PublishUnavailable`/`PublishIdentityMismatch`/`OSError` → QUARANTINE-FAILED → T5);
seal-time impostor quarantine remains strictly fatal (D28) (V16-02);
**D33** T4 is a TERMINAL incomplete state requiring operator review: no code path may write, fsync or publish a
receipt after CP1 (the complete draft lived only in memory — no CP1-durable draft exists), K10–K12 resolve T4 only,
and `observe()` is idempotent on T4 (V16-03);
**D34** every §6.5 phase bound and the `HTTP_HEADROOM` term are substantiated by the Appendix A protocol — fixed
worst-case inputs, `tracemalloc` over the exact normative sequences, raw values recorded in the document, native
headroom measured via glibc `mallinfo2` — and any budget change re-runs it (V16-04);
**D35** `load_run` reproduces Step-1's error precedence and JSON dialect exactly (five bounded stages; all-lines
structure before any body decode), with lines longer than `MAX_LINE` as the SOLE documented acceptance divergence —
REACHABLE for `/1`-accepted evidence, REFUSED by explicit policy (§5.1.2.6) and mandated by the Domain B budget
(V16-05; corrected by V18-01/D43);
**D36** `observe()` mirrors audit check (g) explicitly before `audit_run` (supplied, integer-not-bool, `==
len(records)`) and only ever passes an `egress_count`/authenticated-`receipt.wrapper_count` value; receipt
authentication (R3) precedes every use of a receipt field (V16-06);
**D37** receipt publication binds the temp inode: `st_tmp = os.fstat(tmp_fd)` on the creation descriptor before
close, passed as `expect` into `publish_file()` — never `expect = None` for a file target; substitution → CP3 fails
→ T4 (or T3 if foreign bytes stand at the final name) — a substituted receipt never authenticates (V16-07); 
**D38** the loader is a VERSIONED contract: `obs-loader/1` (Step-1, frozen, oracle only) is superseded by `obs-loader/2`
(bounded, normative), with no runtime selection, no fallback and no silent change — every future change mints
`obs-loader/3` and updates the registry, §11 and §12 together (V17-01);
**D39** `MAX_LINE = 4 × ⌈MAX_BODY_BYTES/3⌉ + FRAMING_ALLOWANCE_BYTES (5,592,920 B)` is a DERIVED, inclusive cap asserted at
import; cap and truncation are file-level pre-parse facts that outrank every parse error and sit after both digest
checks; line CONTENT (terminator stripped) is what gets parsed; and `/2`'s accept set is a strict subset of `/1`'s —
the sole divergence is the over-long-line class, which is REACHABLE for `/1`-accepted legacy evidence and therefore
refused by explicit policy rather than by an impossibility claim (§5.1.2.6, V18-01/D43);
**D40** receipt (and staging-directory) publication proves the DESTINATION against the CREATION identity captured by
`fstat` on the creating descriptor under `identity_source = CREATION`, never against the substitutable pre-syscall
source stat; `OBSERVED` is confined to quarantine moves; CP3e re-reads the published receipt and must reproduce the
written digest before `receipt_pin` is printed (V17-02);
**D41** `observe()` learns every artifact fact through exactly one descriptor-relative `snapshot()`/`stat_component()`
per name, authenticates the immutable snapshot bytes against the mandatory pin, parses those same bytes, and classifies
from frozen facts only — path reads, second presence checks, re-reads and FAULT-to-ABSENT collapse are banned, a receipt
without a final is a contradiction (T3), and an unreadable artifact is never "absent" (V17-03);
**D42** native memory is bounded ANALYTICALLY and enforced by gate, not inferred from a difference sample: `uordblks`
alone is a lower bound (blind to mmapped regions, non-main arenas and intra-window peaks), the four-term headroom table
(≤ 131,072 B) is doubled to `HTTP_HEADROOM = 262,144 B`, event-point sampling plus an `LD_PRELOAD` peak interposer on TWO
channels (malloc family AND direct anonymous `mmap`, V18-03) provide the measurement, and the probe suite is repository
code under `tools/obs/probes/` whose digests are pinned in A.0 (V17-04; V18-02).
**D43** the cap is a REJECTION BOUNDARY, not a conformance claim: `obs-loader/2` intentionally refuses any line whose
content exceeds `MAX_LINE`, including artifacts Step-1 accepts, because Step-1 validates no string length and the bound is a
theorem only for records §5.1.1 writes; the refusal is the deterministic P-6/P-10 message with the offending line number,
it is terminal (T5 with a conflict, T3 otherwise; a seal aborts to quarantine), and no flag, environment variable, truncation,
skip, subset verdict or `/1` fallback may soften it — oversize legacy evidence requires a reviewed `obs-loader/3` (V18-01);
**D44** the Appendix A probe suite is repository code, not an appendix listing: fourteen files under `tools/obs/probes/`,
with size and SHA-256 pinned in A.0, regenerated listings in A.7, a driver that refuses to run on an incomplete suite, and a
recorded-values file that only a reviewed revision may refresh (V18-02);
**D45** a malloc-only interposer is not a bound: the native term is measured on TWO channels (malloc family and direct
anonymous `mmap`), the analytic four-term constant is proved allocator-independent by page-rounding each term and doubling
(A.5.7.4), reservations (obmalloc arenas) are never added to live-byte figures, and the gate compares the SUM against
`HTTP_HEADROOM` rather than trusting one channel (V18-03).
**D46** the direct-`mmap` channel is a shared data structure and is treated as one: the range table and every live total
are mutated under a single spinlock, totals use true atomic read-modify-write, the peak is published by compare-exchange,
and a full table ABORTS with a diagnostic rather than dropping an entry — an interposer that under-counts is worse than no
interposer, so there is no "best effort" path (V19-01);
**D47** mapping bookkeeping is RANGE-based, not call-based: partial unmaps subtract exactly the overlap (splitting a range
when a hole is punched), `mremap` is remove-old + add-new for `MAYMOVE`/`FIXED`/`DONTUNMAP`, `MAP_FIXED` installs subtract
the replaced bytes first, an untracked source is never started into the count, and adjacent ranges coalesce so capacity
tracks disjoint regions rather than call count (V19-02);
**D48** the native headroom is an INVENTORY, not a factor: five measured stages (cold_connect, cold_full, warm_connect,
warm_handshake, warm_empty, warm_full, warm_big), each per-request consumer bounded as unit × count from a protocol
constant, the one-time dynamic loading charged to `HARNESS_FIXED_BUDGET_BYTES` instead of a request, the per-request bounds
summing to 258,048 B ≤ `HTTP_HEADROOM`, and the unenumerated remainder quantified as the residual headroom the gate
enforces (V19-03);
**D49** the probe gate is CI, not a reviewer's courtesy: a dedicated job compiles the interposer with warnings as errors,
runs `--check`, preserves the gate exit status through the pipe, and archives the raw outputs and the built shim on every
outcome (V19-04);
**D50** the suite is pinned by MACHINE, not by prose: `expected.json` carries size + SHA-256 for every other file and
`--check` refuses a modification, an addition or a deletion before it measures anything; `expected.json` cannot hash itself,
so A.0 pins it against this document and `--manifest` prints its digest — the chain is document (git-anchored) →
`expected.json` → every probe file (V19-05).

**D51** a failed allocation moves no accounting: `realloc(p, n)` returning `NULL` for `n != 0` leaves `p` alive, so the shim
returns `NULL` and changes nothing (subtracting there would under-count a live block forever), and by the same rule the
capacity refusal runs BEFORE the live total is advanced, so an aborted mapping is never half-counted. Both rules are
enforced by measurement, not by reading: the 4 MiB + 4 MiB `realloc`-failure case (A.5.4) and probe8's property (D).

**D52** a documented regression is not a gate: the `realloc`-failure rule had a prose paragraph and two hand-measured
numbers (A.5.4), which is exactly the shape V19-05 rejected for the manifest — reviewable, unenforced. It is now the
`realloc_accounting` row of the suite, so the next `alloc_peak.c` change that erases a live block turns `--check` red
instead of passing review on a paragraph (G-V20-01).

**D53** an under-count is fatal, never clamped: subtracting more bytes than the live total means the range table and the
total disagree. Clamping would preserve a wrong-but-plausible number, which is the failure the instrument exists to
prevent (V19-01 dropped an entry for the same reason). `map_live_sub` therefore aborts with both figures (G-V20-03), and
the capacity refusal's rule — refuse before advancing the total (D51) — is the same rule read forwards.

**D54** the manifest is DATA before it is a claim: `check_manifest` validates shape (canonical path, no duplicate paths or
basenames, typed `bytes`, 64-hex `sha256`, no self-pin, no artifact pin, no unknown fields) BEFORE it compares digests,
because v2.0's basename index made two rows indistinguishable and let a non-canonical path bind to this directory's file.
A malformed manifest is a refusal to run, not a warning (G-V20-02).

**D55** a claim names its tree: this document may only report a gate result for a specific, identified tree, and when that
tree is a working tree rather than a commit it must say so in the same sentence. v2.0's "`--check` exits 0" outlived the
tree it described and was false at the commit CI tested; v2.1 withdraws it in place, reports the working-tree result with
its command and its numbers, and leaves the pinned-SHA claim to the pipeline that can make one (V20-15).
**D56** a manifest pins INODES, not names: hashing a path is a statement about whatever that path resolves to at that
instant, which is not necessarily the file the reviewer read. The inventory therefore refuses links and every other
non-regular entry outright, and each comparison goes through one `O_NOFOLLOW` descriptor whose `fstat` must equal the
`lstat` it was enumerated with (V21-01, G-V21-01). A refusal is cheap and recoverable; a hash of somebody else's file is
the one defect the evidence chain cannot survive.

**D57** a count must name what it counts: 14 files exist, `expected.json` pins 13 of them, and `expected.json` is pinned by
A.0 — three numbers, three names, never one sentence (V21-02, G-V21-02). In an evidence chain an off-by-one is not
cosmetic: it tells the reviewer which link they are allowed to skip.

**D58** when the pipeline passes, the claim moves to the pipeline: a working-tree result is the honest maximum before a run
exists and the minimum afterwards. v2.2 replaces v2.1's disclaimer with the SHA, the run, the job, the command and the
printed lines, and keeps the distinction — in the same paragraph — for anything that run did not print (V21-03,
G-V21-03).

## 12. Normative constants (single table; source of truth `tools/obs/params.py` + runner additions)

| Constant | Value | Source / section |
|---|---|---|
| `SPACING_NS` / `WINDOWS` (OBS-02) | 600 ms; (1 s, 2), (60 s, 60) open-left/closed-right | params.py, PACE-2/3 |
| `OBS01_SPACING_NS` / `OBS01_WINDOWS` (OBS-01) | 2 s; (2 s, 1), (60 s, 30) | params.py |
| `DEADLINE_NS` / `AUDIT_MAX_DURATION_NS` / `CANCEL_GRACE_NS` | 17 s / 18 s / 1 s (CANCEL_FAILED window [17,19] s) | params.py, PACE-8, audit (e) |
| `CONNECT/READ/WRITE/POOL_TIMEOUT_S` | 5.0 / 12.0 / 5.0 / 1.0 s; `SEND_TIMEOUT_S` 0.25 s | params.py |
| `MAX_CONSECUTIVE_NO_RESPONSE` | 3 | params.py, ladder B3 |
| `MAX_BODY_BYTES` / `SESSION_BODY_BUDGET_BYTES` | 4,194,304 B / 52,428,800 B | transport.py / runner, §6 |
| `MAX_LINE` / `FRAMING_ALLOWANCE_BYTES` / `READLINE_SLACK_BYTES` | 5,592,920 B = 4 × ⌈MAX_BODY_BYTES / 3⌉ + 512; 512 B; 2 B (`f.readline(MAX_LINE + 2)`) | `obs-loader/2` cap (§5.1.2.1, V17-01/D39); derived + import-asserted; inclusive; §6.5 phase 3 (V15-02) |
| `LOADER_CONTRACT_ID` / `LOADER_CONTRACT_SUPERSEDES` | `"obs-loader/2"` / `"obs-loader/1"` | §5.1.2.0 registry (V17-01/D38); not persisted — derived binding (§5.1.2.0 R-4) |
| `CHUNK_BYTES` | 65,536 B | §6.4; also the `snapshot()` read size (§9.2.1) |
| `RECEIPT_MAX_BYTES` / `JOURNAL_MAX_BYTES` | 131,072 B / 16,384 B | §9.2.1 bounded snapshot caps (V17-03); receipt ≤ 100 KiB and journal ≤ 4 KiB by schema (§6.6), 1.3×/4× headroom |
| `HTTP_HEADROOM` / `SEAL_SLICE_BYTES` | 262,144 B / 49,152 B (3-aligned) | §6.5 phase 1 / §5.1.1 (V14-03); per-request ALLOCATION INVENTORY bounds summing to 258,048 B (A.5.8, derived and gate-checked), checked by the interposer on a client-only request region of 214,120 B, Appendix A.5/A.5.8 (V17-04/D42; inventory V19-03/D48) |
| `TRANSIENT_BUDGET_BYTES` | 12,582,912 B (12 MiB) | §6.1/§6.5 measured proofs (V13-04; re-derived V14-03, D19; OFFICIAL V15-07, D30; reproducible via Appendix A protocol, V16-04/D34) |
| `HARNESS_FIXED_BUDGET_BYTES` / `RUN_RECORD_LIMIT` | 2,097,152 B / 2,000 | §6.6 |
| `MAX_DECOMPRESSED_BYTES` / `MAX_EXPANSION_RATIO` | 52,428,800 B / 1000:1 | §6.7 |
| `DELTA` / `W_MAX_NS` / `RETENTION_NS` / `FALLBACK_NS` | 1/10000 (100 ppm); 250 ms; 600 s; 60 s | params.py, protocol §5.2/5.3 |
| `GROUP_WINDOWS_MS` | g0 (0,2500), g1 (2000,2500), g2 (10000,2500), g3 (60000,5000), ref (180000,5000) | audit.py, V1 window |
| `MIN_SYNC_CALLS` / `RESYNC_COUNTS` / group & role orders | 10; 3–7; (resync,g0,g1,g2,g3,ref); 5m = (S1,K5m,S2), 4tf = (S1,K4h,K1h,K15m,K5m,S2) | audit.py |
| `RENAME_NOREPLACE` | 1 (`<linux/fs.h>`; no `os.RENAME_NOREPLACE` on Python 3.12) | §5.2 (V13-02) |
| `PUBLISH_LOCK_TIMEOUT_NS` / `INTERRUPT_POLL_NS` / `CHECKPOINT_DEFER_MAX_MS` | 30 s / 100 ms / 250 ms | §5.2.1, §7.1, §7.4 |
| Host / paths / params | `data-api.binance.vision`; `/api/v3/time`, `/api/v3/klines` exactly; `symbol,interval,startTime,endTime,limit`; GET only | params.py, protocol §2 |

**Runner additions (normative here; Step-2 code).** `TRANSIENT_BUDGET_BYTES`, `MAX_LINE`,
`FRAMING_ALLOWANCE_BYTES`, `READLINE_SLACK_BYTES`, `SEAL_SLICE_BYTES`, `HTTP_HEADROOM`, `CHUNK_BYTES`,
`RECEIPT_MAX_BYTES`, `JOURNAL_MAX_BYTES`, the `LOADER_CONTRACT_ID`/`LOADER_CONTRACT_SUPERSEDES` pair and the
§5.1.1/§5.1.2 contracts are normative in this document; `params.py` remains
the source of truth for the OBS parameters above. Any new runner constant joins this table in the next reviewed
revision — the budget may change only with a re-derived §6.5 under the Appendix A protocol (D13/D19/D30/D34).

## 13. Appendix A — Memory-accounting probes, native-instrumentation boundaries and the delivered suite (V16-04, V17-04, V18-02, V18-03; informative)

This appendix is the reproducibility record for every §6.5 number: how it is measured, with which instrument, on what,
with which raw values — the boundaries of the native instrument (A.5.4, A.5.7), the ALLOCATION INVENTORY behind the native
term (A.5.8), the concurrency contract of the second channel (A.5.9) and the `realloc`-failure regression of A.5.4) — and
the complete source of the probe programs,
generated from the repository copies (A.7). The bounds of §6.5 are UNCHANGED by this revision. What v2.0 adds is that the
suite is not merely described and not merely present: it is PINNED (A.0 records fourteen digests, `expected.json` pins every
other file, and the driver refuses to run when anything was modified, added or deleted — V19-05), it is GATED IN CI on a
freshly compiled interposer with its raw outputs archived (G-V19-04), and its native figure is decomposed into derived
consumers rather than asserted (A.5.8). Every number below was produced by running those exact files — the working tree
whose digests A.0 records — with `PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --check` on the pinned interpreter,
which printed `PASS: 10 measurements, 14 files pinned by expected.json` and exited 0 — and at commit
`e30ef37011af7cc073fa13c8ee5384ae080995b5`, GitHub Actions run `42208989835` printed that same line from those same bytes
and uploaded its gate log, manifest, report and build log as `probe-suite-evidence` (V21-03, G-V21-03). For the ten
measurements below the claim is therefore a statement about a COMMIT, not about a tree that resembles one; the
corrected reporting line introduced by V21-02 is a working-tree result until the next run prints it, and that is stated
where it belongs (§1.0c) rather than implied here.

### A.0 The probe suite IS repository code, delivered, pinned and machine-enforced (V17-04; V18-02; V19-05; V21-01)

These fourteen files exist at the paths below in the repository; they are not a description of a suite, they ARE it. Every
number in A.2/A.3 was produced by running them from the repository root, and the gate that reproduces those numbers is the
same command a reviewer runs:

```
cc -shared -fPIC -O2 -Wall -Wextra -Werror -o tools/obs/probes/alloc_peak.so tools/obs/probes/alloc_peak.c
PYTHONPATH=$PWD python3 -m tools.obs.probes.run_all --check      # exit 0 pass / 1 mismatch / 2 refused
```

| Path | Role | Bytes | SHA-256 |
|---|---|---|---|
| `tools/obs/probes/README.md` | run instructions, manifest policy, TLS fixture policy, instrument limits, what needs a doc revision | 17,538 | `8221b076d19e005b8c684e6e2f22f4f2bf51596aa2a776ef6cc8eea4a25f5227` |
| `tools/obs/probes/__init__.py` | package marker (empty file; `touch tools/obs/probes/__init__.py`) | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tools/obs/probes/alloc_peak.c` | `LD_PRELOAD` dual-channel peak shim: malloc family AND a locked, range-aware direct anonymous `mmap` (A.5.4/A.5.7) | 19,327 | `19064773bb13436d9386ac896fa9ab3021f01afe0e5bf05a03b1bfdca210efa3` |
| `tools/obs/probes/expected.json` | the manifest (size + SHA-256 of every other file) AND the recorded values, bounds and inventory derivations (§6.5, A.2/A.3/A.5.8) | 6,814 | `8e062a4421f09771941430b663eb0470e6ecbd7dfcaa313d951df2fd0fbb03b6` |
| `tools/obs/probes/probe1_phase1.py` | phase 1 — the §6.4 request path (chunked scratch + `bytes(scratch)`) | 1,358 | `1f63e461fb71836d78c718d0f0ac98c64c46f4c64e99852c0afaf9e83fab38d2` |
| `tools/obs/probes/probe2_seal.py` | phase 2 — §5.1.1 seal fragments, plus the banned retain-the-chunk variant | 2,326 | `455ef7b384c0057ea50a1e6ed711538bfa5ca6e904e22590a576be4bf4c7a20f` |
| `tools/obs/probes/probe3_decode.py` | phase 3 — §5.1.2 `decode_pass` release order on a `MAX_LINE` line | 1,699 | `4320fbe9044b7bd4d9b70238d8d5731832e6348d28a710fe8f92368f1ae66066` |
| `tools/obs/probes/probe4_decode_fresh.py` | phase 3 — the same order fed by a real `readline(MAX_LINE + 2)` buffer | 815 | `e72afb89e85274c90db48ec32d03435b32dae6ffa1577adc0f83d0b68e4129eb` |
| `tools/obs/probes/probe5_byte_equality.py` | §5.1.1 writer vs `_lines([record_to_json…])` (G-V14-02) | 2,647 | `61278c289c1ab2cb10ed7305e3e572e63debed8f1a9b6997a2a440b5c0572a47` |
| `tools/obs/probes/probe6_native.py` | native term: `mallinfo2` samples, both interposed channels, the A.5.8 stage inventory (server in its own process) and the `--realloc` regression; children bootstrapped from verified bytes (V23-01) | 22,236 | `6f630fc3646f06794dcd98513d0dd3cfe20ebb89c59334b62089a5738936dbb4` |
| `tools/obs/probes/probe7_structure.py` | phase 3 — §5.1.2 `scan_structure` (parse + key check + discard) | 780 | `d1e1e15712c3cdbe0693b278e421da048680ba33e7dc264b8c746029341a58e4` |
| `tools/obs/probes/probe8_mmap_threads.py` | A.5.9 — partial unmap, `mremap`, 8-thread concurrency and the fail-closed capacity abort; children and the capacity program bootstrapped from verified bytes (V23-01) | 19,110 | `f802508e3bcbb97d4973edc712a9c86fd124cf2cade195d4a4dbdaa5f973c601` |
| `tools/obs/probes/probe_common.py` | §12 constants, deterministic worst-case fixtures, `measure()`, the shim's getters, and the verified child transport (V23-01) | 24,373 | `6559ba0c7e309ef35368df0c7f0a27206dcccb792924476f4689bf0faccbe437` |
| `tools/obs/probes/run_all.py` | driver: `--check` / `--self-test` / `--record` / `--manifest` / `--update-manifest` / `--report` / `--interpose`; verified-byte module execution and child binding (V22-01/V23-01), the three counts (V21-02) | 69,422 | `2106d2a2c2214962131e54beeefc2d486cc43064151fbb9647dcaf84782d0682` |
| **14 files** | **total** | **188,445** | `python -m tools.obs.probes.run_all --manifest` prints this table |

**A file is its INODE, not its name (V21-01).** This table pins BODIES, and the driver is what makes that true: the
inventory refuses any entry in this directory that is not a regular file, and every comparison hashes through a single
`O_NOFOLLOW` descriptor whose `fstat` must be the same inode as the `lstat` it was enumerated with. A symlink — to
another probe, to a file outside the repository, dangling, or swapped in after the inventory — is a refusal (exit 2)
whose message names the link and its target, never a hash of whatever it points at; `--self-test` proves each case and
also proves that an honest tree still passes, so the refusal cannot be satisfied by refusing everything (G-V21-01).

**The pin has two links, and the second one is CODE (V19-05).** This table is the OUTER link: it names `expected.json`'s
own byte size and SHA-256, which a file cannot hold about itself. The INNER link is `expected.json`'s `manifest` block — path,
byte size and SHA-256 for each of the other thirteen files — and `run_all.check_manifest()` enforces it BEFORE the first
measurement. A MODIFIED file (size or digest), an ADDED file (present on disk, absent from the manifest) and a DELETED file
(absent on disk, present in the manifest) each exit 2 with a per-file diagnostic; the three cases are demonstrated in §1.0
V19-05 and gated by G-V19-05. `--manifest` prints both links, so a reviewer can diff the whole chain in one command.

Rules (normative): stdlib only; no network beyond a loopback TLS listener (which runs in its OWN process, A.5.8); no
wall-clock or unseeded random input (every probe is deterministic and byte-exact); exit codes 0 = pass, 1 = mismatch on a
recorded value or a derived bound, 2 = refused (integrity, interpreter, toolchain). Editing a probe's MEASUREMENT LOGIC
without a reviewed revision of this appendix fails G-V17-04; editing a file without updating `expected.json` fails
G-V19-05; editing A.0's digest without editing the file fails G-V18-02. `alloc_peak.so` is a build artifact and MUST NOT be
committed — it is excluded from the manifest, excluded from the file set, and rebuilt by CI on every run (G-V19-04). When
`cc` is unavailable the gate reports the interposer as unavailable and FAILS rather than silently dropping the check
(A.5.5 requires the constant to be checked).

**Why the digests are in the document AND in the manifest.** A listing that drifts from the code it claims to be is worse
than no listing: it launders an unverified number into a review artifact. Four mechanisms replace trust: `--manifest`
recomputes both tables from the files; A.7's listings are GENERATED from the same files, so the document cannot hold a stale
copy; the driver refuses to run (exit 2) when any of the fourteen files is missing OR when anything in the directory has
changed (V19-05); and CI reruns all of it on the pinned interpreter with the raw output archived (G-V19-04).

**How to refresh a recorded value.** Only inside a reviewed revision: run `--record`, replace the `measurements` array in
`expected.json`, run `--update-manifest`, regenerate A.0/A.7, and state the reason in A.3. A tolerance is not a licence to
drift — D34/D42 list the changes that invalidate every value (interpreter, `MAX_BODY_BYTES`, writer, reader or receipt
schema), and D48 lists those that invalidate the inventory.

### A.1 Environment and measurement protocol

* **Interpreter:** CPython **3.12.3** (the target of `tools/obs/`), OpenSSL **3.0.13**, Linux x86-64, glibc with
  `mallinfo2`, `cc` available for the interposer (`-Wall -Wextra -Werror`). `run_all.py` REFUSES to run (exit 2) on any
  other patch release: a different interpreter invalidates every recorded byte count.
* **Tracemalloc protocol:** `tracemalloc.start()` → run the exact normative sequence → `get_traced_memory()[1]` (the
  peak) → `stop()`. **Inputs are built BEFORE the measurement starts** — a 4 MiB body allocated inside the measured
  region would be attributed to the phase and swamp it; `probe_common.measure` documents and enforces the convention.
* **Second instrument, two channels:** the same sequence is re-run in a child with `alloc_peak.so` preloaded (A.7.9),
  which counts live malloc-family bytes across every MALLOC arena and thread — so it sees allocations that live and die
  inside the region — and, separately, live `MAP_ANONYMOUS|MAP_PRIVATE` bytes, the channel a malloc-only instrument
  cannot see (A.5.4, A.5.7). The figures are reported as `interposed` (malloc) and `map_peak` (direct mappings); the
  native region's gate compares their SUM.
* **Native region = CLIENT only (v2.0).** The loopback server runs in a SEPARATE process (`probe6 --serve`), so the
  measured region contains the request path the runner actually costs. v1.9 ran both endpoints inside the measured
  process, which was conservative in the sum but made per-consumer attribution impossible (A.5.8). The certificate is
  passed to the server process, so an ephemeral fixture is shared rather than regenerated.
* **Cold vs warm (v2.0).** `cold_*` stages measure the FIRST such request in a fresh process — the worst case, and what a
  one-request OBS-01 session pays — while `warm_*` stages run one throwaway request first and then measure the identical
  request, i.e. the steady-state per-request cost. The difference prices the one-time dynamic loading (first `getaddrinfo`
  loads the NSS modules): 168,048 B, charged to `HARNESS_FIXED_BUDGET_BYTES` rather than to a request (A.5.8).
* **TLS fixture (probe6):** the loopback server prefers the repository's `tests/fixtures/tls/localhost.pem`. When it is
  absent — a clean clone — the probe generates an ephemeral self-signed certificate with `openssl` in a temporary
  directory and deletes it at exit, so no key material is committed and the gate still runs. A different certificate
  chain moves the request-region peak by a few kilobytes, which is why the native region carries a 20 % tolerance and
  every phase carries a hard bound.
* **Inputs:** worst-case by construction, deterministic: `MAX_BODY_BYTES = 4,194,304`, `MAX_LINE = 5,592,920`,
  `SEAL_SLICE_BYTES = 49,152`, `CHUNK_BYTES = 65,536`, serialized with Step-1's `_canonical` (sort_keys, separators
  `(",", ":")`). The framing of a schema-valid record with an empty body measures **348 B** (A.7.1), so the widest
  legal record line measures **5,592,756 B** — 164 B below `MAX_LINE` — and the probes additionally exercise a synthetic
  line at exactly `MAX_LINE` to pin the §5.1.2.1 boundary cases.
* **Pass criterion:** each phase ≤ its §6.5 bound under BOTH instruments, phases never summed, max ≤
  `TRANSIENT_BUDGET_BYTES`. `phase2_seal_no_del` is the mirror image: the gate fails if it ever PASSES its bound. The
  native region has two criteria: the SUM of both channels ≤ `HTTP_HEADROOM`, and every A.5.8 inventory item ≤ the bound
  derived for it.
* **Determinism:** repeated runs reproduce every `tracemalloc` figure exactly, every phase's malloc figure within
  0.05 %, and every stage of the native inventory exactly (measured twice per revision); the native region's malloc peak
  varies with the certificate chain, which the recorded tolerance covers; the `mallinfo2` sample figures move freely and
  are reported, never gated (A.5.3).

### A.2 Probe inventory and recorded values

Every value below comes from `python -m tools.obs.probes.run_all --check` on the delivered files (A.0), not from a probe
kept outside the repository.

| Probe | Measurement | Bound (B) | `tracemalloc` (B) | Interposed malloc (B) | Interposed mmap (B) | Verdict |
|---|---|---|---|---|---|---|
| probe1 | `phase1_request` — §6.4 request path | 8,781,824 | 8,396,983 | 8,400,920 | 0 | PASS |
| probe2 | `phase2_seal` — §5.1.1 seal, normative `del` | 151,552 | 148,004 | 147,848 | 0 | PASS |
| probe2 | `phase2_seal_no_del` — BANNED retain-the-chunk | 151,552 | 5,656,528 | — | — | FAILS (intended) |
| probe3 | `phase3_decode` — §5.1.2 decode pass | 11,202,224 | 11,188,520 | 11,186,544 | 0 | PASS |
| probe4 | `phase3_decode_fresh` — real `readline` buffer | 11,202,224 | 11,188,600 | — | — | PASS |
| probe7 | `phase3_structure` — §5.1.2 structure pass | 11,202,224 | 11,188,520 | — | — | PASS |
| probe5 | `byte_equality` — §5.1.1 vs `record_to_json` | — | — | — | — | PASS (8,511,232 B, 1,020 records) |
| probe6 | `native_headroom` — CLIENT-ONLY request region, SUM of both channels | 262,144 | — | 214,120 | 0 | PASS (214,120) |
| probe6 | `native_headroom` — A.5.8 inventory, five items | per item | — | see A.5.8 | — | PASS (each item inside its derivation) |
| probe8 | `mmap_accounting` — partial unmap, `mremap`, 8-thread concurrency, fail-closed | — | — | — | 8,519,680 peak | PASS (all four properties) |

The `map_peak` column is the v1.9 channel (A.5.7). It is 0 B in every phase — those regions do not map — and 0 B in the
native region since v2.0, because the loopback server no longer shares the measured process: v1.9's 16,384 B was the
SERVER's mapping. The channel is not dead: `probe8` exercises it with 8 threads, partial unmaps and `mremap`, and the
gate checks its exact accounting (A.5.9), so its silence in the request region is a fact about that region rather than an
instrument that stopped working.

The v1.7 campaign figures (probes outside the repository, over a slightly wider region that included the header dict and
record metadata) were 8,462,496 / 148,113 / 11,188,261 / 11,188,197 / 5,656,645 B. The repository probes reproduce them
within 0.8 % on the same interpreter and attribute strictly less, which is the safe direction: the BOUNDS are untouched
and the margin is what §6.5 states.

### A.3 Raw values and reconciliation

**A.3.1 Tracemalloc (Python-object attribution), CPython 3.12.3, this revision.**

| Case | Bound (B) | Measured (B) | Slack (B) |
|---|---|---|---|
| phase 1 — request path | 8,781,824 | 8,396,983 | 384,841 |
| phase 2 — seal, normative `del` | 151,552 | 148,004 | 3,548 |
| phase 2 — WITHOUT the `del` (BANNED) | 151,552 | 5,656,528 | −5,504,976 |
| phase 3 — decode pass | 11,202,224 | 11,188,520 | 13,704 |
| phase 3 — decode, fresh buffer | 11,202,224 | 11,188,600 | 13,624 |
| phase 3 — structure pass | 11,202,224 | 11,188,520 | 13,704 |
| phase 3 — §6.5 adjusted (+8,192 file buffer) | 11,202,224 | 11,196,712 | 5,512 |
| banned — `base64.b64decode(str)` | 11,202,224 | 15,381,335 | BANNED (v1.7 campaign) |
| banned — `json.loads(bytes)` with the buffer held | 11,202,224 | 16,781,149 | BANNED (v1.7 campaign) |
| banned — whole-file `_read` + `_jsonl` (50 MiB session) | 12,582,912 | ≥ 139,810,133 | BANNED (v1.7 campaign) |

**A.3.2 Interposer (malloc-level peak across every malloc arena and thread; direct-`mmap` peak in a separate column),
deterministic.** The second channel is what V18-03 added: a malloc-only figure is not a bound for a process whose object
allocator maps its own arenas (A.5.7.1).

| Region | Bound (B) | Measured malloc `peak` (B) | Measured `map_peak` (B) | Slack (B) |
|---|---|---|---|---|
| phase 1 — request path | 8,781,824 | 8,400,920 | 0 | 380,904 |
| phase 2 — seal | 151,552 | 147,848 | 0 | 3,704 |
| phase 3 — decode pass | 11,202,224 | 11,186,544 | 0 | 15,680 |
| request region — malloc channel (client only) | 262,144 (on the sum) | 214,120 | — | 48,024 |
| request region — direct `mmap` channel | 262,144 (on the sum) | — | 0 | — |
| request region — SUM vs `HTTP_HEADROOM` | 262,144 | 214,120 | | 48,024 |

`peak` alone is already ≥ the native MALLOC share (every malloc allocation in the region, plus its small Python
objects); `map_peak` would add the share that never touches `malloc`, and measures 0 B here because the loopback server is
no longer in this process (v1.9's 16,384 B) and the client's request path maps nothing directly. The two are compared with
`HTTP_HEADROOM` as a SUM and are never decomposed into a per-consumer attribution by the instrument — that is A.5.8's job,
which does it by measuring five separate stages rather than by guessing at the allocator. The phase rows take no sum: a
phase's `map_peak` would double-count Python objects already inside `tracemalloc`'s figure (A.5.7.3), which is why 0 B
there is reported and the phase bounds are unmoved.

**A.3.3 `mallinfo2` samples (reported, never gated).** Six sample points around the request, values relative to the
first. This revision's run: `0 → 104,688 B`, `1 → 105,072 B`, `2 → 97,040 B`, `3 → 80,608 B`, `4 → 52,192 B`, end-to-end
difference `52,192 B`. The sample MAX (105,072 B) and the END DELTA (52,192 B) differ by 50 %, i.e. a before/after
difference under-reads this very fixture by half; and the figures move run to run because they are arena state, not a
measurement (A.5.3). Two instruments, two questions: `mallinfo2` says what the arena looks like, the interposer says what
was touched.

**A.3.4 Reconciliation.** `budget = max(8,781,824; 151,552; 11,202,224) = 11,202,224 ≤ TRANSIENT_BUDGET_BYTES =
12,582,912` (margin 1,380,688 B, 12.3 %); the largest measured phase is 11,196,712 B including the file buffer, and
the interposed figures are all below the tracemalloc-derived bounds. Domain A is released before verification starts
(single-copy rule, §5.4/§6.5), so phase-1 objects never coexist with phase-3 peaks, and the `observe()`/CP3e receipt
snapshot (≤ `RECEIPT_MAX_BYTES + CHUNK_BYTES` = 196,608 B) is charged to Domain C.

### A.4 Banned patterns (normative; each is a plausible shortcut a mutation test kills or the gate catches)

1. `base64.b64decode(str)` — the stdlib re-encodes the whole string first (+4.2 MB over the phase-3 bound).
2. Holding `line bytes + decoded text + parsed dict` simultaneously (`json.loads(raw_bytes)` with the buffer
   referenced) — 16,781,149 B.
3. Any whole-file read of records/events (`path.read_bytes()`, `raw.split(b"\n")`) — Step-1's ≥ 139.8 MB failure.
4. Retaining parsed lines/records across a pass (suspended generators, an output list in the structure pass); the
   `phase2_seal_no_del` probe is the executable form of the seal variant and MUST keep failing its bound.
5. Materializing a whole record line at seal (`record_to_json` / `r.body` / the `body_b64` string).
6. Reading an artifact by PATH inside `observe()` or CP3e (V17-03) — a path read cannot be bound to the presence fact.
7. Building the probe's worst-case INPUT inside the measured region — it attributes the fixture to the phase and
   silently invalidates the bound (A.1).

### A.5 Native instrumentation — what `mallinfo2()` can and cannot bound (v1.9: V17-04; direct-`mmap` fence V18-03)

**A.5.1 What `mallinfo2` reports.** It describes the CALLING thread's glibc main arena (plus any arena it owns) at that
instant: `uordblks` = in-use bytes of the non-mmapped arena, `hblkhd` = in-use bytes of mmapped blocks, `arena`/
`fordblks` = capacity/free. Probe6 samples `uordblks + hblkhd` at six points and reports the maximum and the
end-to-end difference.

**A.5.2 Eight reasons a difference of two samples is not a peak.** Each one is visible in this revision's own numbers:

| Blind spot | Why it bites | Evidence here |
|---|---|---|
| Allocations that live and die inside the window | the counter returns to its old value; only the NET change survives | sample max 115,664–159,360 B vs end delta 84,640–87,088 B — up to 46 % under-read |
| Arena/`mmap` granularity | `uordblks` counts whole arena extents and `hblkhd` whole mmapped blocks, so it can OVER-state a small live set while missing a freed one | the sample figures move between identical runs while the interposed figure does not |
| `mmap`ed blocks vs `uordblks` | blocks ≥ `MMAP_THRESHOLD` (128 KiB default, adaptive up to 32 MiB) never appear in `uordblks` | why `hblkhd` is summed in, and why `uordblks` alone is banned as a bound |
| Per-thread arenas | `mallinfo2` reports the calling thread's arena(s) only; other threads' allocations are invisible | the runner's request executes on `obs-request`, so a main-thread probe is a PROXY for the runner, never a measurement of it |
| Allocator reuse | a freed block satisfies the next request, so the counter may not move at all | repeated requests under-report churn relative to a single worst case |
| Fragmentation | free space inside the arena is not in-use space | `arena` growth is invisible to any in-use counter |
| Non-malloc memory | kernel socket buffers (`sk_buff`), page cache, library-owned mappings | outside the counter and outside Domain B (A.5.6) |
| Direct `mmap` by the program | `uordblks`/`hblkhd` describe the heap glibc manages; a mapping the program makes itself is in neither field — CPython's `obmalloc` arenas are exactly that | the interposer now measures the channel separately: 16,384 B in the request region, 0 B per phase (A.5.7.2) |

**A.5.3 Retraction.** v1.7 argued that "the ceiling does not depend on rounding the headroom term down" after
substituting a raw 277,120 B Δ`uordblks` for the 262,144 B constant. That inference is RETRACTED: a difference sample
is a LOWER BOUND on the native transient peak (A.5.2), so 8,739,616 B was a lower bound presented as a proof. The rule
now is absolute: **`Δuordblks` (or `Δ(uordblks + hblkhd)`) may never be used as an upper bound**, and no gate compares
it to a recorded value. It is retained in the appendix only as evidence of its own limitations.

**A.5.4 The instrument that IS a peak — and the exact list of what it intercepts (V17-04; fenced by V18-03; hardened by
V19-01/V19-02).** `alloc_peak.c` (A.7.9) tracks live bytes and exposes six entry points: `alloc_peak_reset()` (baseline for
both channels), `alloc_peak_peak()` (malloc channel), `alloc_peak_map_peak()` (direct-`mmap` channel, added by v1.9), and
three diagnostics — `alloc_peak_map_live()`, `alloc_peak_map_regions()`, `alloc_peak_map_capacity()` — that `probe8` uses to
assert exact accounting. v1.8's claim that it "sees every arena and every thread" is withdrawn: it sees every MALLOC arena
and thread, and the direct-`mmap` channel is measured separately (A.5.7). The inventory is normative for how the figures may
be read:

| Symbol or path | Intercepted? | Accounting, and why |
|---|---|---|
| `malloc`, `calloc`, `realloc`, `free` | YES | live bytes via `malloc_usable_size`, so block headers and alignment are INSIDE the figure (conservative); totals are `fetch_add` / CAS-decrement, never load-then-store |
| glibc blocks served by its internal `mmap` (≥ `MMAP_THRESHOLD`) | YES, once | they arrive through `malloc`; glibc's internal `__mmap` is not the interposed symbol, so the block is counted in `peak` and NOT again in `map_peak` |
| `mmap`, `mmap64` with `MAP_ANONYMOUS\|MAP_PRIVATE` | YES | live mapped bytes and their high-water since the reset, reported as `map_peak`; never added to `peak` |
| `munmap` — FULL range | YES | the whole entry is removed and its bytes subtracted |
| `munmap` — PARTIAL range (v2.0) | YES | exactly the overlapping bytes are subtracted; a hole punched in the middle SPLITS the entry into two, and each surviving piece keeps its own count (V19-02) |
| `mremap` — `MAYMOVE`, `FIXED`, `DONTUNMAP` (v2.0) | YES | accounted as remove(old) + add(new); a source the shim never tracked is not started into the count, and `DONTUNMAP` keeps both (V19-02) |
| `mmap` that lands on `MAP_FIXED` over a tracked range | YES | the replaced bytes are subtracted before the new range is added, so a replacement is not a double count |
| adjacent ranges | COALESCED | bookkeeping only: capacity tracks DISJOINT regions, not the number of calls |
| `posix_memalign`, `aligned_alloc`, `memalign`, `valloc`, `pvalloc` | NO | glibc serves them from the same arena on the measured paths, but a direct call would be invisible — hence A.5.7.4's allocator-independence argument, which does not rely on them |
| `brk`/`sbrk`, `alloca`, thread stacks, static/BSS | NO | out of Domain B (A.5.6) |
| file-backed and shared mappings | EXCLUDED by design | page cache and code sharing, not runner transient (A.5.6) |
| kernel socket buffers, page cache, driver-pinned memory | NO | outside every userspace instrument (A.5.6, A.5.7.5) |

**`realloc` that FAILS (V19 follow-up).** `realloc(p, n)` with `n != 0` either returns a new block (`p` is gone) or returns
`NULL` and leaves `p` valid and still owned by the caller. The shim returns `NULL` and moves NO accounting in the second
case: `usable(NULL)` is 0, so subtracting `usable(p)` there would erase a live block from the total, and every later sample
would under-count — the single error this instrument exists to prevent. `realloc(p, 0)` is the opposite case (glibc frees
`p` and returns `NULL`) and is accounted as a free. The regression is one measurement wide: allocate 4 MiB, `realloc` it to
`SIZE_MAX` (returns `NULL`, block intact and byte-identical), allocate another 4 MiB; the peak must count BOTH blocks and
the pre-fix shim counted one.

**That regression is GATED (V20-11/V20-12).** `probe6_native.py --realloc` runs it in one child under `alloc_peak.so` and
`run_all --check` requires the row `realloc_accounting`, whose clauses are all mandatory: the child exits 0; `realloc`
returned `NULL`; `errno` is `ENOMEM`; the first block is byte-identical (its SHA-256 is taken through the buffer protocol,
so verifying 4 MiB does not allocate 4 MiB inside the region under test) and still WRITABLE, which is what ownership
means; the second block exists; the peak is at least the two-block floor **8,388,608 B** and at most the ceiling
**12,582,912 B** (floor + one block of slack for interpreter and allocator overhead). Measured on this revision's shim:
**8,398,608 B**; with the guard above REMOVED, the identical child reports **4,200,608 B** and reports
`first_block_byte_identical: true` — the content check alone cannot see the bug, which is why the peak is part of the
gate. The blocks are allocated through `CDLL(None)` (the global scope, i.e. the PRELOADED wrapper): a handle on
`libc.so.6` dlsyms glibc's `malloc` and would bypass the counter the measurement is about.

**Concurrency contract (V19-01).** The measured regions contain worker threads and a `ThreadingHTTPServer`, so the range
table is a shared structure and is treated as one: every mutation of `map_tab`/`map_used` and of the map live total happens
between `map_lock()` and `map_unlock()` (a spinlock that yields); the totals move by TRUE atomic read-modify-write
(`atomic_fetch_add`, and a compare-exchange loop for subtraction — v1.9's `load`+`store` pair lost updates); a subtraction
LARGER than the tracked total ABORTS (`map_fail_underflow`, V20-13) instead of clamping at zero, because a clamped total
is an under-count that no later sample can reveal; the peak is
published by compare-exchange on the current live value, so two threads crossing the high-water mark at once cannot leave
the lower value behind; and the symbol resolution that used to happen lazily on the first allocation now happens in a
constructor, so no wrapper calls `dlsym` on a live thread (the `__libc_*` fallbacks cover the constructor's own recursion).

**Fail-closed capacity (V19-01).** The table holds 1,024 disjoint ranges by default. When it cannot hold a new range the
shim writes `alloc_peak: FATAL: range table capacity exhausted (…)` to stderr and calls `abort()`: a dropped entry would
make `map_peak` an under-count, and an instrument that under-counts is worse than no instrument. `ALLOC_PEAK_MAP_SLOTS`
exists only to REDUCE the capacity (clamped to 1…4,096) and is how `probe8` proves the abort path — a production run uses
the compiled default.

It catches microsecond-lived allocations, which is precisely what A.5.2 lists as invisible to `mallinfo2`. The probe runs
the phase (or the request region) in a child with `LD_PRELOAD=alloc_peak.so`, resets immediately before the region and reads
both peaks immediately after. Bit-exact reproducibility is not claimed for the certificate-dependent native figure:
`peak` agrees within 0.05 % across runs for the phases and the native region carries a recorded tolerance, while
`map_peak` moves in 4 KiB page units.

**A.5.5 The headroom term, and where its derivation now lives.** The constant is derived, not measured — measurement only
CHECKS it. v1.9 stated four coarse rows (TLS record buffers 32,768; OpenSSL per-connection state 65,536; `http.client`/
socket 20,480; allocator bookkeeping 12,288 = 131,072, doubled to 262,144). That table's reasoning was sound but its terms
were ASSERTED: "OpenSSL per-connection state ≤ 65,536" was a guess with no count behind it, and the doubling was a factor
labelled "unenumerated consumers", not a bound. v2.0 replaces it with the inventory in **A.5.8**, where every term is a
`unit × count` derivation from a protocol constant and every count is checked against a measured stage:

| Group | Derived bound (B) | Measured (B) | Stage that isolates it |
|---|---|---|---|
| TLS session (record buffers, handshake reassembly, OpenSSL state, X509 chain, Python SSL objects) | 98,304 | 77,864 | `warm_handshake − warm_connect` |
| HTTP request/response staging (request/headers, response headers, `makefile` reader, first recv chunk, socket objects) | 86,016 | 69,992 | `warm_empty − warm_handshake` |
| Body staging (one additional `CHUNK_BYTES` chunk alive at a time) | 65,536 | 0 | `warm_full − warm_empty` |
| Allocator headers and alignment (16 B × ≤ 512 live blocks) | 8,192 | (not separably measurable) | fixed term, A.5.8 |
| **Per-request total** | **258,048** | **147,856** | `warm_full − warm_connect` |
| **`HTTP_HEADROOM`** | **262,144** | — | the design constant, 4,096 B above the derived total |

Checked, not assumed: the CLIENT-ONLY request region measures **214,120 B** of malloc plus **0 B** of direct `mmap` on the
gated cold stage, so the SUM the gate compares is **214,120 B ≤ 262,144 B** with **48,024 B of slack** over the design
constant. That is the worst case (the first request in a fresh process); the steady-state per-request cost is **147,856 B**.
The coarse v1.9 four-term arithmetic is retained only as a second, cruder bound: its terms plus one 4,096 B page of rounding
each still sum to ≤ 147,456 B (A.5.7.4), so the constant holds under both derivations. Phase 1's absolute slack over its
tracemalloc peak is 8,781,824 − 8,396,983 = **384,841 B**, and both interposed phase-1 figures (8,400,920 B malloc, 0 B
mmap) are inside the same bound, so the phase bound holds with the native term measured rather than modelled.

**A.5.6 Out of the domain, stated rather than hidden.** Kernel socket buffers and page cache are outside `mallinfo2`,
outside `tracemalloc`, outside the interposer and outside Domain B: Domain B is the runner's own transient ALLOCATION
budget, not its RSS. A container memory limit therefore observes more than this budget. This is a scope statement, not
a mitigation: if a deployment caps RSS, the cap must be `TRANSIENT_BUDGET_BYTES + HARNESS_FIXED_BUDGET_BYTES +
SESSION_BODY_BUDGET_BYTES` plus interpreter and kernel overhead, and that total is explicitly NOT claimed here.

**A.5.7 Direct `mmap`: the acknowledged blind spot, measured, and why the four-term buffer bounds it (V18-03).**

**A.5.7.1 The acknowledgment.** A malloc-only interposer is not a peak bound for a process that also maps memory directly,
and CPython does exactly that: `obmalloc` obtains its 1 MiB arenas with a direct `mmap`, so the arenas that hold small
Python objects never pass through `malloc`. The effect is not marginal — under this shim a workload of 200,000 short
strings reports a malloc `peak` of 1,626,096 B against a `map_peak` of 9,437,184 B, i.e. the malloc channel alone would have
missed 85 % of the address space that workload reserved. v1.8's claim that the shim "sees every arena and every thread" is
therefore WITHDRAWN as stated (it sees every MALLOC arena and thread), and v1.9 interposes the `mmap` family so the region's
direct mappings are MEASURED instead of assumed (A.5.4).

**A.5.7.2 What the second channel measures, and what it does not.** `mmap`/`mmap64`/`munmap` are interposed for
`MAP_ANONYMOUS\|MAP_PRIVATE` only (`mremap` since v2.0), tracked in a locked RANGE table, reported as `map_peak` (live
mapped bytes since the reset, high-water) and NEVER added to `peak`. Measured for this revision:

| Region | malloc `peak` (B) | direct `map_peak` (B) | Reading |
|---|---|---|---|
| phase 1 — request path | 8,400,920 | 0 | the 4 MiB body and its copy are `malloc`-served at that size; no mapping occurs inside the measured region |
| phase 2 — seal | 147,848 | 0 | 48 KiB slices; no mapping |
| phase 3 — decode/structure | 11,186,544 | 0 | one `MAX_LINE` line; no mapping |
| request region, client only (TLS + 64 KiB body) | 214,120 | 0 | the client path maps nothing directly; v1.9's 16,384 B belonged to the in-process server |
| `probe8` — 8 threads × 64 iterations | — | 8,519,680 (peak) | the channel is exercised where it matters: a concurrency workload, exact to the byte |

File-backed and shared mappings are excluded on purpose (page cache is not runner transient, A.5.6), and mappings that
glibc's allocator makes internally for large blocks are counted once, in `peak`, because they arrive through `malloc`
(`malloc_usable_size` reports the block; glibc calls its internal `__mmap`, not the interposed symbol).

**A.5.7.3 Why an arena reservation is not a live byte.** An obmalloc arena is 1 MiB of ADDRESS SPACE; only the pools the
workload touches are resident, and the objects inside those pools are already counted by `tracemalloc`, which attributes
Python object sizes regardless of which allocator served them. Adding `map_peak` to a `tracemalloc` figure would count the
same objects twice at two granularities, so the fence is applied only where the two channels describe DISJOINT consumers —
the native request region, where `tracemalloc` sees almost nothing. Domain B is live transient ALLOCATION (§6.2/§6.4), not
RSS; A.5.6 already states that a container's memory limit observes more than this budget. What the second channel buys is
therefore precision about the NATIVE region, not a new term in the phase bounds.

**A.5.7.4 The four-term constant is allocator-independent (the bound V18-03 asked for).** Let the request region's consumers
be `c = 1..4` with the concurrent bounds `b_c` of the A.5.5 table (32,768; 65,536; 20,480; 12,288). Any allocation strategy
— `malloc`, a direct `mmap`, or a static buffer — that serves `c` holds at most `b_c` bytes for `c` at any instant, plus at
most one 4,096 B page of granularity if `c` acquires a mapping of its own. The bound on `b_c` comes from the protocol's own
sizes (one 16,384 B TLS record in and one out; one connection's OpenSSL state; three fixed-size `http.client` staging
buffers; ≤ 256 live blocks with ≤ 16 B of header each), not from an allocator's behaviour, so it is invariant under the choice
of allocator; rounding is the only allocator-dependent term. Hence

```
Σ(b_c + 4,096) = 131,072 + 16,384 = 147,456 B  ≤  HTTP_HEADROOM = 262,144 B
remaining slack = 114,688 B  → unenumerated consumers of the same bounded kind (stdlib `_ssl` C objects,
                               resolver scratch, codec/locale state)
```

The constant therefore bounds the region even if EVERY term were served by a direct `mmap` and every term needed its own
page-rounded mapping — the worst case a malloc-only instrument could hide. The corollary is the useful half: the bound can
only fail if a consumer's live bytes exceed its table term, which means the protocol's own sizes changed (a bigger TLS
record, more whitelisted headers, a second connection) — exactly the change D34/D42 require to re-run this whole protocol.

**A.5.7.5 What is still not measured (stated, not hidden).** Non-anonymous and shared mappings (page cache, `SSL_CTX` code
segments), kernel socket buffers, pinned/DMA buffers owned by a driver, and any library that allocates through its own
private allocator or `brk` directly. None of them is reachable from the request path measured here, and all of them are out
of Domain B by A.5.6's scope statement. G-V18-03 fails if the mmap channel is absent (a build that dropped it), if the sum
`peak + map_peak` exceeds `HTTP_HEADROOM`, or if a phase's `map_peak` exceeds the constant — so a future change that starts
mapping inside a measured region is caught as a review item rather than absorbed silently.

**A.5.8 The allocation inventory behind the native term (V19-03).** The question A.5.5 answers with a number is "which
allocations does one request make, and how large can each be?" — answered here by MEASURING a five-stage decomposition in
separate child processes, with the loopback server in its own process so the region is the client path only:

| Stage | What it performs | malloc peak (B) |
|---|---|---|
| `cold_connect` | first TCP connect in a fresh process | 168,120 |
| `cold_full` | first TLS request in a fresh process (the GATED worst case) | 214,120 |
| `warm_connect` | connect after one throwaway run | 72 |
| `warm_handshake` | TLS handshake, connection closed, no HTTP bytes | 77,936 |
| `warm_empty` | TLS + one request, zero-length response body | 147,928 |
| `warm_full` | TLS + one request, 64 KiB body | 147,928 |
| `warm_big` | TLS + one request, 1 MiB body | 147,928 |

**A.5.8.1 The items, each derived from a protocol constant.** A "unit" below is a documented size, not a preference:
16,384 B is `SSL3_RT_MAX_PLAIN_LENGTH` (the largest TLS record), 8,192 B is `io.DEFAULT_BUFFER_SIZE` (the
`socket.makefile` buffer), 65,536 B is `CHUNK_BYTES` (§6.4), 4,096 B is the page granularity at which any consumer's
mapping is rounded, and 16 B is a glibc chunk header.

| Item | Derivation (unit × count) | Bound (B) | Measured (B) |
|---|---|---|---|
| TLS record buffers | 2 × 16,384 — one read, one write record | 32,768 | |
| TLS handshake reassembly and session ticket | 1 × 16,384 — the largest handshake message the protocol permits | 16,384 | |
| OpenSSL connection state | 1 × 16,384 — `SSL` + `SSL3_STATE` + `SSL_SESSION` + cipher/digest contexts, page-rounded | 16,384 | |
| X509 chain and verification store | 1 × 16,384 — one certificate chain, its parsed objects and the verification context | 16,384 | |
| Python `_ssl` objects | 1 × 16,384 — `SSLSocket` + `SocketIO` + the `_ssl._SSLSocket` wrapper, page-rounded | 16,384 | |
| **TLS session, subtotal** | | **98,304** | **77,864** (`warm_handshake − warm_connect`) |
| Request line and headers | 1 × 4,096 — the §6.4 GET line plus the fixed header set | 4,096 | |
| Response status, headers and parsed dict | 1 × 4,096 — the whitelisted header block and its parsed form | 4,096 | |
| `socket.makefile` reader | 1 × 8,192 — `io.DEFAULT_BUFFER_SIZE` | 8,192 | |
| First receive | 1 × 65,536 — one `CHUNK_BYTES` chunk (headers plus the start of any body) | 65,536 | |
| Socket and `http.client` objects | 1 × 4,096 — the socket, its `_io` wrappers and the response object | 4,096 | |
| **HTTP staging, subtotal** | | **86,016** | **69,992** (`warm_empty − warm_handshake`) |
| Body staging | 1 × 65,536 — ONE further chunk; the previous chunk is rebound and freed, so at most one extra is live | 65,536 | **0** (`warm_full − warm_empty`: the block is reused, which is what the scaling control then proves) |
| Allocator headers and alignment | 16 B × ≤ 512 live blocks | 8,192 | not separable; inside every figure above |
| **Per-request total** | | **258,048** | **147,856** (`warm_full − warm_connect`) |

The two differences that measure 0 B (`body_staging`, `scaling_control`) reproduce to within a few dozen bytes across
runs, because glibc reuses the block the first chunk occupied; the gate therefore allows ONE PAGE of negative slack for
them (`inventory.items[].tolerance = 4,096`) and none for the other three, whose bounds are large enough that reuse cannot
hide a real consumer. Everything else in the table reproduces exactly (measured twice per revision).

**A.5.8.2 The one-time term is not a request.** `cold_connect − warm_connect = 168,120 − 72 = 168,048 B` is the first
`getaddrinfo` loading the NSS modules and their symbol tables. It is bounded at 12 × 16,384 = 196,608 B, it happens ONCE per
process, and it is charged to `HARNESS_FIXED_BUDGET_BYTES` (2,097,152 B, §6.6) — a process-level budget — instead of to the
per-request headroom. v1.9 measured it inside the request region without naming it, which is why its figure (195,184 B) was
larger than the true per-request cost (147,856 B) by an amount no row of its table explained.

**A.5.8.3 The gated worst case still fits.** A one-request session pays both: the gate compares `cold_full` = **214,120 B**
(malloc) + 0 B (direct `mmap`) = **214,120 B** against `HTTP_HEADROOM` = 262,144 B, i.e. **48,024 B of slack**. The two terms
are not simply additive in practice (the request path reuses blocks the loader released, which is why 214,120 < 168,048 +
147,856), so the design does not rely on their sum: it gates the MEASURED worst case, and the analytic per-request bound is
checked separately against its stages.

**A.5.8.4 Unenumerated consumers, quantified.** Two independent numbers, both enforced:

* ANALYTIC: the derived per-request items sum to 258,048 B, leaving **4,096 B** of `HTTP_HEADROOM` for any consumer this
  inventory failed to enumerate. One page. If such a consumer existed and were larger than one page, the derived sum would
  exceed the constant and G-V19-03 fails on `per_request_bound` before any measurement is even consulted.
* MEASURED: the gated region uses 214,120 B of 262,144 B, leaving **48,024 B** that no consumer in this inventory claims.
  Any allocation site outside the inventory is therefore bounded by 48,024 B in the worst case the gate actually observes.

**A.5.8.5 The scaling control.** `warm_big − warm_full = 0 B` for a 1 MiB body (16× the normative 64 KiB). A consumer that
accumulated per byte — a retained response, a growing buffer, an unbounded list — would grow by ~1 MiB and breach the
65,536 B bound the gate places on that difference (with one page of negative slack, since reuse can make the difference
a few dozen bytes negative without meaning anything). This is the quantitative form of "we enumerated the consumers that can
grow": the inventory is complete in the dimension that varies with input size, and every constant term is bounded by its row.

**A.5.9 The direct-`mmap` channel under concurrency (V19-01/V19-02).** `probe8_mmap_threads.py` (A.7.14) measures four
properties in a child with the shim preloaded; each is a failure mode of a naive table, and each is asserted, not observed:

| Property | Measurement | Result |
|---|---|---|
| A. partial unmap | map 12,288 → `munmap` the middle 4,096 → live 8,192 in TWO ranges → free both pieces → 0 | exact (12,288 / 8,192 / 2 ranges / 0) |
| B. `mremap` | map 8,192 → `mremap(MAYMOVE)` to 32,768 → live 32,768 → `munmap` → 0 | exact (8,192 / 32,768 / 0) |
| C. concurrency | 8 threads × 64 iterations of map / map / partial unmap / `mremap` / unmap, after a warm-up; 1 MiB per thread held at a barrier | peak 8,519,680 ≥ 8,388,608 (every mapping counted: a lost update would under-read); final live 0 and final range count 0 (nothing leaked) |
| D. fail-closed | the child runs under `ALLOC_PEAK_MAP_SLOTS=64`; from its OWN measured baseline (3 interpreter regions) that capacity is exactly 61 explicit mappings, after which one more is attempted | `SIGABRT` (−6); the table filled to exactly 64 ranges; the diagnostic matched BYTE FOR BYTE, `… (tracked 64, capacity 64, live 2,363,392): refusing to under-report`; the flushed `MAPPED` lines prove the abort followed the intended mapping |
| D′. negative control | the identical program and preload, capacity left at the compiled 1024, only 4 explicit mappings | exit 0, `SURVIVED` printed, no diagnostic — so the abort in (D) is caused by the capacity and by nothing else |

The peak in (C) is above the 8,388,608 B floor by 131,072 B, which is the interpreter's own arena growth during the phase
(eight threads creating thread states); the gate accepts it inside `floor + 8 × 64 pages` and requires the exactness
properties, not the exact peak. Property (C) is what makes V19-01's lock a MEASURED requirement: without it, 8 × 64 = 512
concurrent insertions and removals of overlapping ranges lose entries, and either the peak falls below the floor or the
table drifts away from its baseline.

Property (D) is deliberately not written as "`ALLOC_PEAK_MAP_SLOTS=1` must abort". An earlier form of it did exactly that,
and the check was a FALSE POSITIVE: the interpreter maps anonymous memory for its own arenas before any probe code runs, so
with a capacity of one the shim aborts during startup — with live 1,064,960 B, a tracked count of 1 and none of the probe's
mappings in existence — and "aborted + no SURVIVED" is satisfied by an abort that proves nothing. The check now depends on
facts the child itself reports, so it cannot pass by accident:

* the child prints `BASELINE live=… regions=…` and `CAPACITY …` with `flush=True` BEFORE it maps anything, so the capacity
  that will fill the table is derived from this run, not from an assumption about startup;
* every `MAPPED` line is flushed before the next mapping is attempted, so its presence on stdout proves the interposer
  recorded that mapping while the process was alive, and its last instance must report tracked == capacity and live ==
  baseline + (capacity − baseline regions) × 4,096;
* the table must fill EXACTLY (61 successful mappings, no more, no fewer), which also proves no explicit mapping coalesced:
  the addresses are `MAP_FIXED_NOREPLACE` and 1 GiB apart;
* the abort must be `SIGABRT` (−6) — not an exit code — and the single diagnostic line must equal the expected string byte
  for byte, including the numbers the same child just printed, so a truncated or reworded message cannot pass and an abort
  raised anywhere else cannot be mistaken for this one;
* the negative control (D′) runs the identical program with the capacity untouched: it must reach `SURVIVED`, exit 0 and
  emit no diagnostic. Without it, a preload failure or a rejected address would look like a capacity abort.

### A.6 Budget reconciliation (normative §6.5 restated with the measured evidence)

Phases run sequentially (single-flight; seal after all requests; verify after seal), so the budget is the max phase
peak, never the sum: 11,202,224 B ≤ `TRANSIENT_BUDGET_BYTES = 12,582,912 B`, largest measured 11,196,712 B. Any change
to `MAX_BODY_BYTES`, the writer, the reader or the receipt schema re-runs this whole protocol (D34/D42) before the
budget may change — and now literally re-runs it, since the protocol is `python -m tools.obs.probes.run_all --check`.

The native term is reconciled separately against its own constant (A.5.8): the gated client-only region measures
**214,120 B** against `HTTP_HEADROOM = 262,144 B` (48,024 B of slack), and the per-request inventory's DERIVED bounds total
**258,048 B**, which also fits — so the constant is satisfied both by measurement and by derivation. The one-time dynamic
loading (168,048 B, A.5.8.2) belongs to `HARNESS_FIXED_BUDGET_BYTES`, i.e. it is charged once per process rather than once
per request. D48 records the rule that carries this forward: a new consumer must be added to the inventory WITH its
derivation before it may appear in a measured region.

### A.7 The complete suite, file by file (V17-04; generated from the delivered files by V18-02 and v2.0)

Every listing below is GENERATED from the file it names, and A.0 pins the same bytes. Listings use THIS
DOCUMENT's CRLF line separators: the probe modules are committed with LF, so the text is identical line for line
while the separator bytes are the document's. A.0's SHA-256 is the authority on the file's own bytes, and
(G-V18-02 b) compares the listings after normalising that separator. Section numbers are STABLE across
revisions so that citations stay valid: v1.9 used A.7.1–A.7.13, and v2.0 appends `probe8_mmap_threads.py` as A.7.14 rather
than renumbering the twelve files a reviewer already knows. If a listing and a file disagree, the file is what runs (G-V18-02).

#### A.7.1 `tools/obs/probes/probe_common.py`

```python
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
```

#### A.7.2 `tools/obs/probes/probe1_phase1.py`

```python
"""Phase 1 - request path (section 6.4): chunked scratch accumulation then `bytes(scratch)`.

Normative sequence, bound 8,781,824 B. The body is built BEFORE the measurement starts (A.1): only the request-path
allocations are attributed to this phase.
"""
from __future__ import annotations

from tools.obs.probes import probe_common as C


def sequence(payload: bytes) -> int:
    scratch = bytearray()
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:offset + C.CHUNK_BYTES]      # <= 64 KiB transient, as in 6.4
        scratch += chunk
        offset += len(chunk)
        del chunk
    finished = bytes(scratch)                              # 2 x MAX_BODY peak: the bytearray AND its copy
    assert len(finished) == len(payload)
    return len(finished)


def main() -> list[dict]:
    payload = C.body()
    return [C.measure("phase1_request", lambda: sequence(payload),
                      max_body_bytes=C.MAX_BODY_BYTES, chunk_bytes=C.CHUNK_BYTES)]


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    payload = C.body()
    return C.interposed_pair(C.shim(), lambda: sequence(payload))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.3 `tools/obs/probes/probe2_seal.py`

```python
"""Phase 2 - the section 5.1.1 seal: one 48 KiB slice -> b64encode -> write, `del` before the next slice.

Bound 151,552 B (normative order) ; the retained-chunk variant is the BANNED anti-pattern (A.4.4).
"""
from __future__ import annotations

import base64
import hashlib

from tools.obs.probes import probe_common as C


class Sink:
    """Stands in for the staging fd: hashes and drops every write (section 5.1.1 `write_all`)."""

    def __init__(self) -> None:
        self.sha = hashlib.sha256()
        self.bytes_written = 0

    def write(self, data: bytes) -> None:
        self.sha.update(data)
        self.bytes_written += len(data)


def sequence(payload: bytes, tail: bytes, retain: bool) -> int:
    sink = Sink()
    sink.write(b'{"body_b64":"')
    kept: list[bytes] = []
    for offset in range(0, len(payload), C.SEAL_SLICE_BYTES):
        chunk = base64.b64encode(payload[offset:offset + C.SEAL_SLICE_BYTES])
        sink.write(chunk)
        if retain:
            kept.append(chunk)                             # anti-pattern: every chunk stays alive
        else:
            del chunk                                      # normative release BEFORE the next slice
    sink.write(tail)
    return sink.bytes_written


def main() -> list[dict]:
    payload = C.body()
    tail = b'"' + b"," + C.canonical({k: v for k, v in _record_meta().items()})[1:].encode() + b"\n"
    return [
        C.measure("phase2_seal", lambda: sequence(payload, tail, False),
                  slices=-(-len(payload) // C.SEAL_SLICE_BYTES)),
        C.measure("phase2_seal_no_del", lambda: sequence(payload, tail, True)),
    ]


def _record_meta() -> dict:
    return {"seq": 2000, "role": "K5m", "path": "/api/v3/time", "start_ns": 1, "end_ns": 2, "status": 200,
            "error": None, "group_name": None, "group_kind": None, "boundary_ms": None, "headers": []}


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    payload = C.body()
    tail = b'"' + b"," + C.canonical(_record_meta())[1:].encode() + b"\n"
    return C.interposed_pair(C.shim(), lambda: sequence(payload, tail, False))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.4 `tools/obs/probes/probe3_decode.py`

```python
"""Phase 3 - the section 5.1.2 `decode_pass` order on ONE line at MAX_LINE.

Normative release order: decode -> del line bytes -> json.loads -> del text -> pop body_b64 -> encode ascii ->
del the str -> b64decode(bytes) -> del raw. Bound 11,202,224 B.
"""
from __future__ import annotations

import base64
import json

from tools.obs.probes import probe_common as C


def decode_one(line: bytes) -> int:
    text = line.decode("utf-8")
    del line                                     # release the bytes BEFORE parsing
    obj = json.loads(text)
    del text                                     # release the text BEFORE touching the value
    if not isinstance(obj, dict) or set(obj) != C.RECORD_KEYS:
        raise SystemExit("fixture is not a schema-valid record line")
    value = obj.pop("body_b64")                  # the <= 5,592,408 B str leaves the dict FIRST
    raw = value.encode("ascii")
    del value                                    # release the str BEFORE decoding
    body = base64.b64decode(raw, validate=True)
    del raw                                      # BYTES in: b64decode(str) would re-encode the whole string
    return len(body) + len(obj)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)
    return [C.measure("phase3_decode", lambda: decode_one(line), line_bytes=len(line))]


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    line = C.line_at(C.MAX_LINE)
    return C.interposed_pair(C.shim(), lambda: decode_one(line))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.5 `tools/obs/probes/probe4_decode_fresh.py`

```python
"""Phase 3 - the same release order fed from a real buffered reader (`readline(MAX_LINE + 2)`), as `decode_pass` does.

Independent re-measurement of the same order with a line buffer the reader allocated itself.
"""
from __future__ import annotations

import io

from tools.obs.probes import probe_common as C
from tools.obs.probes.probe3_decode import decode_one


def read_then_decode(stream: io.BytesIO) -> int:
    raw = stream.readline(C.MAX_LINE + 2)        # the reader's own line buffer (<= MAX_LINE + 2 bytes)
    return decode_one(raw)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)

    def run() -> int:
        return read_then_decode(io.BytesIO(line))

    return [C.measure("phase3_decode_fresh", run, line_bytes=len(line))]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.6 `tools/obs/probes/probe5_byte_equality.py`

```python
"""Probe 5 - byte equality: the section 5.1.1 streaming writer vs `_lines([record_to_json(r) ...])` (G-V14-02).

1,020 deterministic records, one of them at MAX_BODY_BYTES. Equality is asserted on the SHA-256 of the whole stream.
"""
from __future__ import annotations

import base64
import hashlib

from tools.obs.probes import probe_common as C


def record(index: int) -> dict:
    size = C.MAX_BODY_BYTES if index == 1_019 else (index * 37) % 4_096
    return {"seq": index + 1, "role": "S1", "path": "/api/v3/time", "start_ns": index, "end_ns": index + 1,
            "status": 200, "error": None, "group_name": None, "group_kind": None, "boundary_ms": None,
            "body": C.body(size), "headers": []}


def reference_line(obj: dict) -> bytes:
    """Step-1 `record_to_json` + `_lines`: the byte sequence the writer must reproduce exactly."""
    return C.canonical({
        "seq": obj["seq"], "role": obj["role"], "path": obj["path"], "start_ns": obj["start_ns"],
        "end_ns": obj["end_ns"], "status": obj["status"], "error": obj["error"], "group_name": obj["group_name"],
        "group_kind": obj["group_kind"], "boundary_ms": obj["boundary_ms"], "headers": obj["headers"],
        "body_b64": base64.b64encode(obj["body"]).decode("ascii"),
    }).encode("utf-8") + b"\n"


def streamed_line(obj: dict) -> bytes:
    """Section 5.1.1 framing: `{` + "body_b64" value + `,` + the other 11 keys in canonical order + newline."""
    meta = {k: v for k, v in obj.items() if k not in ("body_b64", "body")}
    low = {k: v for k, v in meta.items() if k < "body_b64"}     # EMPTY under the frozen 12-key set
    high = {k: v for k, v in meta.items() if k > "body_b64"}    # the other 11 keys
    out = bytearray(b"{")
    if low:
        out += C.canonical(low)[1:-1].encode() + b","
    out += b'"body_b64":"'
    for offset in range(0, len(obj["body"]), C.SEAL_SLICE_BYTES):
        out += base64.b64encode(obj["body"][offset:offset + C.SEAL_SLICE_BYTES])
    out += b'"' + (b"," + C.canonical(high)[1:].encode() if high else b"}")
    out += b"\n"
    return bytes(out)


def main() -> list[dict]:
    records = [record(i) for i in range(1_020)]
    reference = b"".join(reference_line(r) for r in records)
    streamed = b"".join(streamed_line(r) for r in records)
    equal = hashlib.sha256(reference).hexdigest() == hashlib.sha256(streamed).hexdigest()
    return [{"probe": "byte_equality", "peak": 0, "bound": None, "pass": equal,
             "detail": {"bytes": len(reference), "records": len(records),
                        "max_body_bytes": C.MAX_BODY_BYTES}}]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.7 `tools/obs/probes/probe6_native.py`

```python
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

CHILDREN ARE STARTED FROM THE PARENT'S VERIFIED BYTES (V23-01). v2.3 launched this file's server, stage and realloc
children with `python -m tools.obs.probes.probe6_native`, so the child's interpreter opened this FILE after the driver
had verified a manifest the child never read: a tree substituted in that window would have run unverified code inside
the measurement. Every child here now starts through `probe_common.spawn_suite_child` / `run_suite_child`, which send
the source over a pipe from the buffers the parent's manifest check accepted, with the manifest's own digest per frame
and a closed package (`__path__ = []`) in the child, so nothing it is not given can be imported from disk. That holds
for the measured stage children, the realloc child and the loopback server child alike, and for the grandchildren a
child itself starts. WHAT IS PRESERVED: the child is still a fresh interpreter counted from exec by the shim (its
startup is inside the reported peak, exactly as before), with the same `cwd`, the same `sys.argv` (`-m` gives the module
path and the parent passes that path), the same reset points inside `child()` and `realloc_child()`, and the module is
still executed as `__main__`. Run this file on its own and it refuses to start a child rather than fall back to `-m`.
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
    """Launch the server process — from the verified bytes (V23-01) — and wait for its port."""
    arguments = ["--serve", str(KIND_BODY[kind]), "plain" if kind == "connect" else "tls"]
    if kind != "connect":
        cert, key = material()
        arguments += [cert, key]
    process = C.spawn_suite_child("probe6_native", arguments, cwd=ROOT)
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
    done = C.run_suite_child("probe6_native", ["--child", stage],
                             env={"LD_PRELOAD": SHIM, "ALLOC_PEAK_FILE": report}, timeout=300, cwd=ROOT)
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
    done = C.run_suite_child("probe6_native", ["--realloc"], env={"LD_PRELOAD": SHIM}, timeout=300, cwd=ROOT)
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
```

#### A.7.8 `tools/obs/probes/probe7_structure.py`

```python
"""Phase 3 - the section 5.1.2 `scan_structure` pass: parse + key check + DISCARD, no body decode.

Bound 11,202,224 B. Retaining the dict (or the line) is the banned pattern A.4.4.
"""
from __future__ import annotations

import json

from tools.obs.probes import probe_common as C


def scan(line: bytes) -> int:
    text = line.decode("utf-8")
    del line
    obj = json.loads(text)
    del text
    ok = isinstance(obj, dict) and set(obj) == C.RECORD_KEYS
    del obj                                      # DISCARD: the structure pass retains nothing
    return int(ok)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)
    return [C.measure("phase3_structure", lambda: scan(line), line_bytes=len(line))]


if __name__ == "__main__":
    print(C.canonical(main()))
```

#### A.7.9 `tools/obs/probes/alloc_peak.c`

```c
// alloc_peak.c - LD_PRELOAD peak allocator for Appendix A.5 (V17-04; direct-mmap fence V18-03; concurrency and
// range-awareness v2.0, V19-01/V19-02).
//
// TWO counters, because one allocator family is not the whole story:
//
//   1. MALLOC FAMILY (malloc/calloc/realloc/free): live bytes across every malloc arena and thread, atomically, with
//      the PEAK delta since the last reset. This is what mallinfo2 cannot give: a difference of two samples misses
//      allocations that live and die between them, mallinfo2 sees only the calling thread's arena(s), and uordblks
//      alone excludes mmapped blocks.
//
//   2. DIRECT mmap (mmap/mmap64/munmap/mremap, MAP_ANONYMOUS|MAP_PRIVATE only): live mapped bytes and their peak since
//      the last reset. Python's own object allocator does NOT go through malloc for its 1 MiB arenas, so a malloc-only
//      interposer is blind to them (A.5.7). Blocks that malloc itself serves with mmap are NOT double counted here:
//      glibc calls __mmap internally, not the interposable symbol, and they are already counted by malloc_usable_size.
//
// CONCURRENCY (V19-01). The measured region contains a ThreadingHTTPServer and worker threads, so the mmap channel is a
// multi-writer structure. Every mutation of the range table and of every live total happens under one spinlock
// (map_flag), and the live totals are updated with a true atomic read-modify-write (fetch_add / a CAS-decrement loop),
// never a load-then-store pair. The peak is published with a compare-exchange loop on the current live value, so no
// observation is lost when several threads cross the high-water mark at once.
//
// RANGE AWARENESS (V19-02). The table stores [start, start+len) ranges, not bare lengths, so
//   * munmap of a PARTIAL range subtracts exactly the overlap and keeps (or splits into) the surviving pieces;
//   * mremap is accounted as remove(old) + add(new), including MREMAP_FIXED (which unmaps its target first) and
//     MREMAP_DONTUNMAP (which keeps the source);
//   * an mmap that lands on MAP_FIXED over an existing tracked range subtracts the replaced bytes before adding the new
//     ones, and ADJACENT ranges are coalesced so a page-by-page workload cannot exhaust the table.
//
// FAIL CLOSED (V19-01). If the table cannot hold a range, the shim writes a diagnostic and calls abort(). It never
// silently drops an entry: a dropped entry would make map_peak an under-count, and an under-count is exactly the
// failure mode this instrument exists to prevent. ALLOC_PEAK_MAP_SLOTS may only REDUCE the capacity (test use: it is how
// probe8 proves the abort path); production runs use the compiled default.
//
// REALLOC FAILURE (V19 follow-up). `realloc(p, n)` with n != 0 that returns NULL leaves p valid and owned by the caller,
// so the shim returns NULL and moves NOTHING: subtracting usable(p) there would erase a live block from the total and
// every later sample would be an under-count. `realloc(p, 0)` is different - glibc frees p and returns NULL - and is
// accounted as a free.
//
// Public symbols:
//   void   alloc_peak_reset(void):        baseline := live, peak := 0, and the same for the mmap counter
//   size_t alloc_peak_peak(void):         peak live-minus-baseline malloc bytes since the reset
//   size_t alloc_peak_map_peak(void):     peak live anonymous-private mmap bytes since the reset (A.5.7)
//   size_t alloc_peak_map_live(void):     current live mapped bytes (diagnostic; probe8 asserts on it)
//   size_t alloc_peak_map_regions(void):  current tracked ranges (diagnostic; coalescing must keep this flat)
//   size_t alloc_peak_map_capacity(void): the effective table capacity (diagnostic)
//
// On exit it also writes {"peak":N,"map_peak":M,"map_live":L,"map_regions":R} to $ALLOC_PEAK_FILE when set.
//
// Build: cc -shared -fPIC -O2 -Wall -Wextra -o alloc_peak.so alloc_peak.c
//
// FENCED LIMITS (A.5.4/A.5.7 - stated, not hidden):
//   * not intercepted: posix_memalign/aligned_alloc/memalign/valloc/pvalloc (glibc serves them through malloc on the
//     measured paths, but a direct call would be invisible), brk/sbrk, alloca, thread stacks, static/BSS, and any
//     library that calls its own private allocator;
//   * file-backed and shared mappings are excluded on purpose (page cache is out of Domain B, A.5.6);
//   * a range the shim did not create (a mapping that predates LD_PRELOAD) is not in the table, so unmapping it subtracts
//     nothing - it was never counted either.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <malloc.h>
#include <sched.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

/* glibc's own allocator entry points: the bootstrap fallback, so that symbol resolution can never recurse. */
extern void *__libc_malloc(size_t);
extern void *__libc_calloc(size_t, size_t);
extern void *__libc_realloc(void *, size_t);
extern void  __libc_free(void *);

static void *(*real_malloc)(size_t);
static void *(*real_calloc)(size_t, size_t);
static void *(*real_realloc)(void *, size_t);
static void  (*real_free)(void *);

/* Resolve the real symbols ONCE, in a constructor: after this point the wrappers never call dlsym, so they are safe on
   any thread. If the constructor's dlsym is itself still resolving (it allocates), the __libc_* fallbacks below serve
   the call instead of recursing. */
__attribute__((constructor)) static void alloc_peak_bootstrap(void) {
    real_malloc = (void *(*)(size_t))dlsym(RTLD_NEXT, "malloc");
    real_calloc = (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "calloc");
    real_realloc = (void *(*)(void *, size_t))dlsym(RTLD_NEXT, "realloc");
    real_free = (void (*)(void *))dlsym(RTLD_NEXT, "free");
}

static size_t usable(void *p) { return p ? malloc_usable_size(p) : 0; }

/* ---- malloc channel ------------------------------------------------------------------------------------------- */

static _Atomic size_t live = 0;
static _Atomic size_t base = 0;
static _Atomic size_t peak = 0;

static void observe_peak(_Atomic size_t *baseline, size_t now, _Atomic size_t *high_water) {
    size_t b = atomic_load_explicit(baseline, memory_order_relaxed);
    size_t rel = now > b ? now - b : 0;
    size_t seen = atomic_load_explicit(high_water, memory_order_relaxed);
    while (rel > seen && !atomic_compare_exchange_weak_explicit(high_water, &seen, rel,
                                                               memory_order_relaxed, memory_order_relaxed)) { }
}

static void track_add(size_t n) {
    size_t now = atomic_fetch_add_explicit(&live, n, memory_order_relaxed) + n;
    observe_peak(&base, now, &peak);
}

static void track_sub(size_t n) {
    size_t cur = atomic_load_explicit(&live, memory_order_relaxed);
    for (;;) {
        size_t next = cur > n ? cur - n : 0;
        if (atomic_compare_exchange_weak_explicit(&live, &cur, next, memory_order_relaxed, memory_order_relaxed)) {
            return;
        }
    }
}

/* ---- direct anonymous-private mappings (A.5.7), lock and range table (V19-01/V19-02) --------------------------- */

#define MAP_SLOTS_DEFAULT 1024
#define MAP_SLOTS_MAX 4096

typedef struct { uintptr_t start; size_t len; } range;

static _Atomic size_t map_live = 0;
static _Atomic size_t map_base = 0;
static _Atomic size_t map_peak = 0;
static _Atomic unsigned map_flag = 0;                 /* 0 = free, 1 = held */
static range map_tab[MAP_SLOTS_MAX];
static size_t map_used = 0;
static size_t map_cap = 0;
static _Atomic size_t map_regions_high = 0;

static void map_lock(void) {
    while (atomic_exchange_explicit(&map_flag, 1u, memory_order_acquire)) {
        while (atomic_load_explicit(&map_flag, memory_order_relaxed)) sched_yield();
    }
}

static void map_unlock(void) { atomic_store_explicit(&map_flag, 0u, memory_order_release); }

static void map_capacity(void) {                      /* called with the lock held */
    if (map_cap) return;
    size_t cap = MAP_SLOTS_DEFAULT;
    const char *env = getenv("ALLOC_PEAK_MAP_SLOTS");        /* TEST-ONLY: can only reduce the capacity */
    if (env && *env) {
        char *end = NULL;
        errno = 0;
        unsigned long v = strtoul(env, &end, 10);
        if (errno == 0 && end && *end == '\0' && v >= 1 && v <= MAP_SLOTS_MAX) cap = (size_t)v;
    }
    map_cap = cap;
}

static void map_fail_closed(const char *why) {        /* called with the lock held; never returns */
    char buf[256];
    int n = snprintf(buf, sizeof buf,
                     "alloc_peak: FATAL: %s (tracked %zu, capacity %zu, live %zu): refusing to under-report\n",
                     why, map_used, map_cap ? map_cap : (size_t)MAP_SLOTS_DEFAULT,
                     (size_t)atomic_load_explicit(&map_live, memory_order_relaxed));
    if (n > 0) {
        ssize_t written = write(STDERR_FILENO, buf, (size_t)(n < (int)sizeof buf ? n : (int)sizeof buf));
        (void)written;
    }
    abort();
}

/* Underflow of the live total: reported with both numbers (never a clamp), then aborted. Kept separate from
   map_fail_closed() so the two invariants are distinguishable in stderr and in a test. */
static void map_fail_underflow(size_t wanted, size_t tracked) {   /* called with the lock held; never returns */
    char buf[256];
    int n = snprintf(buf, sizeof buf,
                     "alloc_peak: FATAL: mmap accounting underflow: %zu B to subtract, %zu B tracked "
                     "(regions %zu): refusing to clamp to zero\n",
                     wanted, tracked, map_used);
    if (n > 0) {
        ssize_t written = write(STDERR_FILENO, buf, (size_t)(n < (int)sizeof buf ? n : (int)sizeof buf));
        (void)written;
    }
    abort();
}

static void map_reserve(size_t extra) {
    if (map_cap == 0) map_capacity();
    if (map_used + extra <= map_cap) return;
    map_fail_closed("range table capacity exhausted");
}

static void map_publish_peak(void) {
    size_t b = atomic_load_explicit(&map_base, memory_order_relaxed);
    size_t now = atomic_load_explicit(&map_live, memory_order_relaxed);
    size_t rel = now > b ? now - b : 0;
    size_t seen = atomic_load_explicit(&map_peak, memory_order_relaxed);
    while (rel > seen && !atomic_compare_exchange_weak_explicit(&map_peak, &seen, rel,
                                                               memory_order_relaxed, memory_order_relaxed)) { }
}

static void map_live_add(size_t n) {
    atomic_fetch_add_explicit(&map_live, n, memory_order_relaxed);
}

/* Subtract n from the live total. The old form clamped at zero (`cur > n ? cur - n : 0`), which silently turns a lost
   range into a plausible-looking number: a total that is too small is exactly the under-count this instrument exists to
   prevent, and clamping makes it permanent and invisible. Removing more bytes than are tracked therefore means the range
   table and the total have disagreed - a bug in the shim, not a property of the workload - so it is FATAL: a diagnostic
   with both figures, then abort(), before any sample can report the corrupted total (V20-13). */
static void map_live_sub(size_t n) {
    size_t cur = atomic_load_explicit(&map_live, memory_order_relaxed);
    for (;;) {
        if (cur < n) map_fail_underflow(n, cur);
        if (atomic_compare_exchange_weak_explicit(&map_live, &cur, cur - n,
                                                 memory_order_relaxed, memory_order_relaxed)) {
            return;
        }
    }
}

/* Subtract [s, e) from the tracked set, adjusting the live total by exactly the overlap. Returns bytes removed. */
static size_t map_forget(uintptr_t s, uintptr_t e) {  /* called with the lock held */
    size_t removed = 0;
    size_t i = 0;
    while (i < map_used) {
        uintptr_t rs = map_tab[i].start;
        uintptr_t re = rs + map_tab[i].len;
        if (e <= rs || s >= re) { i++; continue; }
        uintptr_t lo = s > rs ? s : rs;
        uintptr_t hi = e < re ? e : re;
        removed += (size_t)(hi - lo);
        if (s <= rs && e >= re) {                              /* fully covered: drop the entry */
            map_tab[i] = map_tab[--map_used];
            continue;
        }
        if (s <= rs) {                                         /* head removed */
            map_tab[i].start = e;
            map_tab[i].len = (size_t)(re - e);
            i++;
            continue;
        }
        if (e >= re) {                                         /* tail removed */
            map_tab[i].len = (size_t)(s - rs);
            i++;
            continue;
        }
        map_reserve(1);                                        /* hole punched: split in two */
        map_tab[i].len = (size_t)(s - rs);
        map_tab[map_used].start = e;
        map_tab[map_used].len = (size_t)(re - e);
        map_used++;
        i++;
    }
    if (removed) map_live_sub(removed);
    return removed;
}

static size_t map_len_at(uintptr_t s) {                /* called with the lock held */
    for (size_t i = 0; i < map_used; i++) {
        if (map_tab[i].start == s) return map_tab[i].len;
    }
    return 0;
}

/* Add the new mapping [s, s+len): drop whatever it replaced, then coalesce adjacent ranges (bookkeeping only). */
static void map_record(uintptr_t s, size_t len) {      /* called with the lock held */
    if (len == 0) return;
    uintptr_t e = s + len;
    (void)map_forget(s, e);                            /* MAP_FIXED installs over the old bytes */
    size_t i = 0;
    while (i < map_used) {
        uintptr_t rs = map_tab[i].start;
        uintptr_t re = rs + map_tab[i].len;
        if (re < s || rs > e) { i++; continue; }
        if (rs < s) s = rs;
        if (re > e) e = re;
        map_tab[i] = map_tab[--map_used];
    }
    map_reserve(1);                                    /* before the total moves: a refused range must not be counted */
    map_live_add(len);                                 /* the NEW bytes, not the coalesced extent */
    map_tab[map_used].start = s;
    map_tab[map_used].len = (size_t)(e - s);
    map_used++;
    if (map_used > atomic_load_explicit(&map_regions_high, memory_order_relaxed)) {
        atomic_store_explicit(&map_regions_high, map_used, memory_order_relaxed);
    }
    map_publish_peak();
}

/* ---- public API ------------------------------------------------------------------------------------------------ */

void alloc_peak_reset(void) {
    atomic_store_explicit(&base, atomic_load_explicit(&live, memory_order_relaxed), memory_order_relaxed);
    atomic_store_explicit(&peak, 0, memory_order_relaxed);
    map_lock();
    atomic_store_explicit(&map_base, atomic_load_explicit(&map_live, memory_order_relaxed), memory_order_relaxed);
    atomic_store_explicit(&map_peak, 0, memory_order_relaxed);
    map_unlock();
}

size_t alloc_peak_peak(void) { return atomic_load_explicit(&peak, memory_order_relaxed); }

size_t alloc_peak_map_peak(void) { return atomic_load_explicit(&map_peak, memory_order_relaxed); }

size_t alloc_peak_map_live(void) { return atomic_load_explicit(&map_live, memory_order_relaxed); }

size_t alloc_peak_map_regions(void) {
    map_lock();
    size_t n = map_used;
    map_unlock();
    return n;
}

size_t alloc_peak_map_capacity(void) {
    map_lock();
    if (map_cap == 0) map_capacity();
    size_t n = map_cap;
    map_unlock();
    return n;
}

/* ---- malloc family --------------------------------------------------------------------------------------------- */

void *malloc(size_t size) {
    void *p = real_malloc ? real_malloc(size) : __libc_malloc(size);
    track_add(usable(p));
    return p;
}

void free(void *p) {
    size_t was = usable(p);
    if (was) track_sub(was);
    if (real_free) real_free(p); else __libc_free(p);
}

void *calloc(size_t n, size_t size) {
    void *p = real_calloc ? real_calloc(n, size) : __libc_calloc(n, size);
    track_add(usable(p));
    return p;
}

/* realloc(p, n) with n != 0 either returns a NEW block (p is gone) or fails and leaves p intact. On failure the
   original allocation is still live and still counted, so the tracking state must not move at all: usable(NULL) is 0,
   and subtracting the old size there would erase a block that the caller still owns - an under-count, which is the
   one error this instrument must never make. realloc(p, 0) is the other case: glibc frees p and returns NULL, so the
   subtraction IS correct and is kept below. */
void *realloc(void *old, size_t size) {
    size_t was = usable(old);
    void *p = real_realloc ? real_realloc(old, size) : __libc_realloc(old, size);
    if (p == NULL && size != 0) return NULL;             /* failure: old block untouched, tracking untouched too */
    size_t now = usable(p);
    if (now >= was) track_add(now - was); else track_sub(was - now);
    return p;
}

/* ---- direct mmap family ---------------------------------------------------------------------------------------- */

#if defined(SYS_mmap) && defined(SYS_munmap)
void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    void *p = (void *)syscall(SYS_mmap, addr, len, prot, flags, fd, off);
    if (p == MAP_FAILED) return p;
    if ((flags & MAP_ANONYMOUS) && (flags & MAP_PRIVATE) && !(flags & MAP_SHARED)) {
        map_lock();
        map_record((uintptr_t)p, len);
        map_unlock();
    }
    return p;
}

void *mmap64(void *addr, size_t len, int prot, int flags, int fd, off_t off) {
    return mmap(addr, len, prot, flags, fd, off);
}

int munmap(void *addr, size_t len) {
    int rc = (int)syscall(SYS_munmap, addr, len);
    if (rc == 0 && len) {
        map_lock();
        (void)map_forget((uintptr_t)addr, (uintptr_t)addr + len);
        map_unlock();
    }
    return rc;
}

#if defined(SYS_mremap)
void *mremap(void *old, size_t old_len, size_t new_len, int flags, ...) {
    void *target = NULL;
    if (flags & MREMAP_FIXED) {
        va_list ap;
        va_start(ap, flags);
        target = va_arg(ap, void *);
        va_end(ap);
    }
    void *p = (void *)syscall(SYS_mremap, old, old_len, new_len, flags, target);
    if (p == MAP_FAILED) return p;
    size_t source = old_len;
    map_lock();
    if (source == 0) source = map_len_at((uintptr_t)old);   /* old_len 0 means "size not stated" */
    if (flags & MREMAP_DONTUNMAP) {                         /* the source mapping survives */
        if (source) map_record((uintptr_t)p, new_len);
    } else {
        size_t removed = source ? map_forget((uintptr_t)old, (uintptr_t)old + source) : 0;
        if (removed) map_record((uintptr_t)p, new_len);      /* untracked source: do not start counting it */
    }
    map_unlock();
    return p;
}
#endif
#endif

__attribute__((destructor)) static void report(void) {
    const char *path = getenv("ALLOC_PEAK_FILE");
    if (!path || !*path) return;
    map_lock();
    size_t map_now = atomic_load_explicit(&map_peak, memory_order_relaxed);
    size_t map_still = atomic_load_explicit(&map_live, memory_order_relaxed);
    size_t regions = map_used;
    map_unlock();
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "{\"peak\":%zu,\"map_peak\":%zu,\"map_live\":%zu,\"map_regions\":%zu}\n",
            atomic_load_explicit(&peak, memory_order_relaxed), map_now, map_still, regions);
    fclose(f);
}
```

#### A.7.10 `tools/obs/probes/run_all.py`

```python
"""Driver for the Appendix A probe suite (V17-04; V18-02/V18-03; manifest and inventory v2.0, V19-03/V19-05; v2.2 V21-01/V21-02; v2.3 V22-01/V22-02/V22-03; v2.4 V23-01; v2.5 V24-01).

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
```

#### A.7.11 `tools/obs/probes/README.md`

```
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
`--manifest` prints its digest). The CHILDREN are inside it as of v2.4 and their interpreter STARTUP as of v2.5 — see the next section.

## A child starts from the same bytes, in an isolated interpreter (V23-01, V24-01)

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

The child's INTERPRETER STARTUP is isolated too (V24-01). v2.4 bound the payload but still launched the child as
`python -c <bootstrap>`, so startup was outside every check: `site` imports a `sitecustomize` from the environment,
`PYTHONPATH` entries are searched, and for `-c` the working directory is `sys.path[0]`, so a planted hook or a
shadow `hashlib.py` — the module the payload verification itself calls — could run before the bootstrap's first
line. Every child is now started `python -I -S -c <bootstrap>`: `-I` drops the `PYTHON*` environment, the user site
directory and the working directory from `sys.path`, and `-S` skips `site`, so neither `sitecustomize` nor
`usercustomize` is imported and nothing in the working directory can resolve ahead of the standard library. The
bootstrap does not take that on trust: `isolated()` runs before it reads the parent's request and refuses (exit 86)
unless `sys.flags.isolated`, `no_site`, `ignore_environment` and `no_user_site` are all set, no startup hook is in
`sys.modules`, and no `sys.path` entry is the working directory. A dropped flag fails closed instead of quietly
re-opening the hole, and the measurement is unchanged: the child is still counted by the shim from exec, so Python
startup remains inside the native peak exactly as before, and no gated reading moved.

`--self-test` counts outcomes separately (V22-03): `28 passed, 0 failed, 1 skipped (29 cases)` rather than folding
skips into passes (`29 passed` where the device-node case can run). A case this host cannot run (no `CAP_MKNOD`, no
`O_NOFOLLOW`) prints as `skip` and never counts as a pass; the exit status depends only on failures. Its cases
include a real inode swapped between `lstat()` and `open()` (V22-02), so `samestat`'s refusal is demonstrated rather
than argued, and ten of them start REAL children (V23-01, V24-01): a frame whose digest does not match is refused instead of
executed, a child runs the bytes it was sent while the path it names holds different source, a swapped bootstrap and
a truncated payload are refused, and an unverified sibling cannot be imported from disk. Four of them (V24-01)
start a child in a working directory holding a hostile `sitecustomize.py` plus `hashlib.py` / `ssl.py` shadows:
the hook never runs, `hashlib` is still the standard library's, the payload digest still verifies, a child started
without `-I -S` is refused — and a CONTROL shows the same plant DOES run when the flags are removed, so the cases
cannot pass vacuously.

After a REVIEWED change: `--update-manifest` (this directory), then regenerate A.0/A.7 from the document (D44).

## Files

| File | Role |
|---|---|
| `probe_common.py` | constants (mirroring §12), the deterministic worst-case fixtures, the shim's getters, and the verified child transport — bootstrap, payload framing, `run_suite_child`, launched `-I -S` (V23-01, V24-01) |
| `probe1_phase1.py` | phase 1 — request path: 64 KiB chunked scratch accumulation, then `bytes(scratch)` |
| `probe2_seal.py` | phase 2 — §5.1.1 seal order, plus the BANNED retain-the-chunk variant (must fail its bound) |
| `probe3_decode.py` | phase 3 — the §5.1.2 `decode_pass` release order on ONE line at `MAX_LINE` |
| `probe4_decode_fresh.py` | phase 3 — the same order fed from a real `readline(MAX_LINE + 2)` buffer |
| `probe5_byte_equality.py` | §5.1.1 streaming writer byte-equality over the full session budget |
| `probe6_native.py` | native memory around one loopback TLS request: `mallinfo2` samples, both interposed channels, the five-stage / cold-vs-warm inventory (A.5.8), and the GATED `realloc`-failure regression (`--realloc`, A.5.4 V20-11/V20-12) |
| `probe7_structure.py` | phase 3 — the `scan_structure` pass (parse, key-check, DISCARD) |
| `probe8_mmap_threads.py` | A.5.9 — partial unmap, `mremap`, 8-thread concurrency and the fail-closed capacity abort |
| `alloc_peak.c` | `LD_PRELOAD` shim: malloc-family peak and a locked, range-aware direct-`mmap` peak |
| `run_all.py` | driver: `--check`, `--self-test`, `--record`, `--manifest`, `--update-manifest`, `--report`, `--interpose`; verified-byte module execution and child binding (V22-01, V23-01, V24-01) |
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
```

#### A.7.12 `tools/obs/probes/expected.json`

```json
{
  "env": {
    "isolation": "every child runs python -I -S -c <bootstrap> and refuses (exit 86) unless sys.flags.isolated/no_site/ignore_environment/no_user_site are set, no site/sitecustomize/usercustomize is imported and sys.path holds no working-directory entry (V24-01)",
    "openssl": "3.0.13",
    "platform": "Linux x86-64",
    "python": "3.12.3",
    "updated": "v2.5"
  },
  "inventory": {
    "items": [
      {
        "bound": 196608,
        "derivation": "12 x 16,384 B: first getaddrinfo loads the NSS modules and their symbol tables; charged to HARNESS_FIXED_BUDGET_BYTES, not per request",
        "from": "cold_connect",
        "minus": "warm_connect",
        "name": "one_time_loading"
      },
      {
        "bound": 98304,
        "derivation": "6 x 16,384 B: TLS read buffer, write buffer, handshake reassembly, X509 chain + verify, SSL/SSL3_STATE/SESSION/cipher base, Python _ssl + SSLSocket + SocketIO",
        "from": "warm_handshake",
        "minus": "warm_connect",
        "name": "tls_session"
      },
      {
        "bound": 86016,
        "derivation": "4,096 request line/headers + 4,096 response status/headers/parsed dict + 8,192 socket.makefile reader + 65,536 first recv chunk (CHUNK_BYTES) + 4,096 socket/http object overhead = 86,016 B",
        "from": "warm_empty",
        "minus": "warm_handshake",
        "name": "http_staging"
      },
      {
        "bound": 65536,
        "derivation": "1 x 65,536 B: one recv chunk, transient per chunk (CHUNK_BYTES)",
        "from": "warm_full",
        "minus": "warm_empty",
        "name": "body_staging",
        "tolerance": 4096
      },
      {
        "bound": 65536,
        "derivation": "a 1 MiB body must not add more than ONE chunk: any accumulation would breach this",
        "from": "warm_big",
        "minus": "warm_full",
        "name": "scaling_control",
        "tolerance": 4096
      }
    ],
    "per_request_bound": 258048,
    "stages": [
      "cold_connect",
      "cold_full",
      "warm_connect",
      "warm_handshake",
      "warm_empty",
      "warm_full",
      "warm_big"
    ]
  },
  "manifest": {
    "algorithm": "sha256",
    "files": [
      {
        "bytes": 17538,
        "path": "tools/obs/probes/README.md",
        "sha256": "8221b076d19e005b8c684e6e2f22f4f2bf51596aa2a776ef6cc8eea4a25f5227"
      },
      {
        "bytes": 0,
        "path": "tools/obs/probes/__init__.py",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      },
      {
        "bytes": 19327,
        "path": "tools/obs/probes/alloc_peak.c",
        "sha256": "19064773bb13436d9386ac896fa9ab3021f01afe0e5bf05a03b1bfdca210efa3"
      },
      {
        "bytes": 1358,
        "path": "tools/obs/probes/probe1_phase1.py",
        "sha256": "1f63e461fb71836d78c718d0f0ac98c64c46f4c64e99852c0afaf9e83fab38d2"
      },
      {
        "bytes": 2326,
        "path": "tools/obs/probes/probe2_seal.py",
        "sha256": "455ef7b384c0057ea50a1e6ed711538bfa5ca6e904e22590a576be4bf4c7a20f"
      },
      {
        "bytes": 1699,
        "path": "tools/obs/probes/probe3_decode.py",
        "sha256": "4320fbe9044b7bd4d9b70238d8d5731832e6348d28a710fe8f92368f1ae66066"
      },
      {
        "bytes": 815,
        "path": "tools/obs/probes/probe4_decode_fresh.py",
        "sha256": "e72afb89e85274c90db48ec32d03435b32dae6ffa1577adc0f83d0b68e4129eb"
      },
      {
        "bytes": 2647,
        "path": "tools/obs/probes/probe5_byte_equality.py",
        "sha256": "61278c289c1ab2cb10ed7305e3e572e63debed8f1a9b6997a2a440b5c0572a47"
      },
      {
        "bytes": 22236,
        "path": "tools/obs/probes/probe6_native.py",
        "sha256": "6f630fc3646f06794dcd98513d0dd3cfe20ebb89c59334b62089a5738936dbb4"
      },
      {
        "bytes": 780,
        "path": "tools/obs/probes/probe7_structure.py",
        "sha256": "d1e1e15712c3cdbe0693b278e421da048680ba33e7dc264b8c746029341a58e4"
      },
      {
        "bytes": 19110,
        "path": "tools/obs/probes/probe8_mmap_threads.py",
        "sha256": "f802508e3bcbb97d4973edc712a9c86fd124cf2cade195d4a4dbdaa5f973c601"
      },
      {
        "bytes": 24373,
        "path": "tools/obs/probes/probe_common.py",
        "sha256": "6559ba0c7e309ef35368df0c7f0a27206dcccb792924476f4689bf0faccbe437"
      },
      {
        "bytes": 69422,
        "path": "tools/obs/probes/run_all.py",
        "sha256": "2106d2a2c2214962131e54beeefc2d486cc43064151fbb9647dcaf84782d0682"
      }
    ]
  },
  "measurements": [
    {
      "bound": 8781824,
      "instrument": "tracemalloc",
      "interposed": 8400920,
      "interposed_map_peak": 0,
      "peak": 8396983,
      "probe": "phase1_request",
      "tolerance": 0.02,
      "v17_campaign": 8462496
    },
    {
      "bound": 151552,
      "instrument": "tracemalloc",
      "interposed": 147848,
      "interposed_map_peak": 0,
      "peak": 148004,
      "probe": "phase2_seal",
      "tolerance": 0.02,
      "v17_campaign": 148113
    },
    {
      "bound": 151552,
      "expected_fail": true,
      "instrument": "tracemalloc",
      "peak": 5656528,
      "probe": "phase2_seal_no_del",
      "tolerance": 0.02,
      "v17_campaign": 5656645
    },
    {
      "bound": 11202224,
      "instrument": "tracemalloc",
      "interposed": 11186544,
      "interposed_map_peak": 0,
      "peak": 11188520,
      "probe": "phase3_decode",
      "tolerance": 0.02,
      "v17_campaign": 11188261
    },
    {
      "bound": 11202224,
      "instrument": "tracemalloc",
      "peak": 11188600,
      "probe": "phase3_decode_fresh",
      "tolerance": 0.02,
      "v17_campaign": 11188197
    },
    {
      "bound": 11202224,
      "instrument": "tracemalloc",
      "peak": 11188520,
      "probe": "phase3_structure",
      "tolerance": 0.02,
      "v17_campaign": 11188197
    },
    {
      "bound": null,
      "bytes": 8511232,
      "peak": 0,
      "probe": "byte_equality",
      "records": 1020
    },
    {
      "bound": 262144,
      "end_delta": 52192,
      "instrument": "mallinfo2 sample max (LOWER BOUND); the gate uses the interposed client-only region",
      "interposed": 217072,
      "interposed_map_peak": 0,
      "peak": 105072,
      "probe": "native_headroom",
      "tolerance": 0.2
    },
    {
      "bound": null,
      "instrument": "alloc_peak.so direct-mmap channel under concurrency, partial unmap and mremap (A.5.9)",
      "iterations": 64,
      "peak": 8519680,
      "probe": "mmap_accounting",
      "threads": 8
    },
    {
      "bound": 12582912,
      "instrument": "alloc_peak.so malloc channel, one child: 4 MiB, a failed realloc(p, SIZE_MAX), a second 4 MiB (A.5.4, V20-11/V20-12)",
      "peak": 8398528,
      "probe": "realloc_accounting",
      "tolerance": 0.02
    }
  ],
  "schema": "obs-probes/2"
}
```

#### A.7.13 `tools/obs/probes/__init__.py`

```python

```

#### A.7.14 `tools/obs/probes/probe8_mmap_threads.py`

```python
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

CHILDREN ARE STARTED FROM THE PARENT'S VERIFIED BYTES (V23-01). v2.3 started the mmap child with
`python -m tools.obs.probes.probe8_mmap_threads --child`, which re-opens this FILE in the child after the driver verified
it, and the capacity program was handed to `python -c` with no binding at all. Both now travel through
`probe_common.run_suite_child` / `run_program`: the source goes over a pipe from the parent's manifest-checked buffers,
each frame is checked against the digest the manifest promises, the child's bootstrap is bound by its own digest, and
the child's `tools.obs.probes` package is closed (`__path__ = []`) so an unverified sibling cannot be imported there.
WHAT IS PRESERVED: the same fresh interpreter per child, still counted by the shim from exec (the baseline line is
printed by the program itself, exactly as before), the same `cwd` and `LD_PRELOAD`, the same `sys.argv` (`-c` plus the
mapping count, which is what the inline program used to see), and the same resets. Run this file on its own and it
refuses to start a child rather than fall back to `-m`.
"""
from __future__ import annotations

import ctypes
import itertools
import json
import os
import re
import signal
import sys
import threading

from tools.obs.probes import probe_common as C

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
    """Run the probed program once and return what it printed: its own baseline, its mappings, and how it died.

    V23-01: the program is a literal of THIS file's verified source, and it reaches the child through the same
    digest-checked pipe as everything else — `sys.argv` is still `['-c', '<mappings>']`, so the program's own
    interface did not change.
    """
    env = {key: value for key, value in os.environ.items() if key != "ALLOC_PEAK_MAP_SLOTS"}
    env.update(LD_PRELOAD=SHIM, PYTHONPATH=ROOT)
    if slots is not None:
        env["ALLOC_PEAK_MAP_SLOTS"] = str(slots)
    done = C.run_program(CHILD_PROGRAM, [str(mappings)], env=env, timeout=180, cwd=ROOT)
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
    done = C.run_suite_child("probe8_mmap_threads", ["--child"], env={"LD_PRELOAD": SHIM}, timeout=600, cwd=ROOT)
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
```

End of v2.2. Step-2 implementation SHALL implement §3–§10 literally; any deviation requires a new reviewed revision of this
document, not an implementation choice.
