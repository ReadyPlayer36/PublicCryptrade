# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v1.7 (NORMATIVE)

Status: design only. No live request is authorized by this document. Milestone 1 remains **BLOCKED** until the reviewer accepts
the protocol and a separately reviewed Step-2 implementation commit. This revision **supersedes v1.6**: it resolves all seven
findings of the v1.6 review (V16-01…V16-07, §1.0) and re-states every affected section at implementation granularity; where
v1.6 and this document disagree, this document governs, and sections not restated here remain normative as written in v1.6.

Anchor: repository `ReadyPlayer36/PublicCryptrade`, commit `11ff12535e42639e3bab53304651e3ea2b5cd6b3`
(branch `impl-obs-harness-provenance`; lineage `impl-obs-step1` → `f337862e52dada43f425cee05154e18f212987aa` →
`dbfe53cecaea63b0a5128a756f5ede0c12c3ca6f` → `673f9a2ace30a449267adace9af0f9d94865bda1` → this commit), reviewed
against the actual Step-1 code in `tools/obs/` at that commit. V15/V16 branch-sync result: `tools/obs/` is byte-identical
between `dbfe53c…` and `11ff125…` (only this document changed between them; `673f9a2` and `11ff125` are
documentation-only revisions of this file — `git diff dbfe53c 11ff125 -- tools/obs/` is empty), so every v1.7 correction
below is a design-text-versus-code discrepancy, not code drift. Hard citations re-verified at this commit: `audit.py` lines 70–86
(`abort_condition_seq`), 289–296 (check (g): `wrapper_count` must be a caller-supplied integer — the "independent
egress counter") and 623–626 (`audit_run` reloads the run via `load_run` at 626); `runstore.py` 45 (`ManifestError(ValueError)`),
172/217 (`_canonical`/`_lines`), 206–209 (`record_to_json` base64-encodes the body), 246–250/279–286 (`_read`/`_jsonl`
whole-file load), 253–258 (`load_manifest` fails closed without a 64-hex pin), 291–328 (field validators), 348–357
(`_record_from_json` decodes `body_b64` from a str), 370–388 (`load_run`), and `eventlog.py` 50–58 (digest-line format;
`bytes(r.body)` is `r.body` — probe-verified identity, so bodies hash in place). Phase memory numbers in §6.5 and
Appendix A are measurements over the exact normative sequences on CPython 3.12.3 (`tracemalloc`, worst-case inputs;
methodology, raw values and native-headroom accounting: Appendix A); the probe scripts are review artifacts, not
repository files.
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
and `LoadedRun` contents — the `load_run` contract is made exact by v1.7 for V16-05: Step-1's error precedence and JSON
dialect are reproduced verbatim, with the `MAX_LINE` cap as the sole documented acceptance divergence (§5.1.2, D35)) and
land with the regression tests named in §11.

0.3 Persisted artifacts (all names are exact):

| Artifact | Format tag | Written by | Written when |
|---|---|---|---|
| `records.jsonl`, `events.jsonl`, `manifest.json` | `obs-run-manifest/1` | `runstore.write_run` (Step-2: §5.1.1 replacement) | SEALING, once, exclusive create, fsync F1–F4 |
| `<run_id>.refusal.json` | `obs-refusal/1` | *runner* `RefusalWriter` | pre-flight refusal, once, exclusive create |
| `<run_id>.receipt.json` (sibling of the run dir) | `obs-outer-index/1` | *runner* `ReceiptPublisher` | CP3, once, no-replace publication |
| `manifest.json` SHA-256 pin | (bare hex) | emitted by `write_run` return value | before CP1, out-of-band (§10.1) |
| `<run_id>.receipt.json` SHA-256 | (bare hex) | emitted by `ReceiptPublisher` after CP3 | out-of-band (§10.1, V14-05) |
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

## 1. Revision maps — V16 findings resolved in v1.7; V15/V14/V13 findings retained

### 1.0 V16 findings resolved in v1.7

| ID | Finding (v1.6 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V16-01 | The resolver treated `journal_pin`/`receipt_pin` as optional (`if pin is not None and sha256(raw) != pin`): a refusal authenticated only by its recomputable self-digest classified authoritative T0, and a receipt with no `receipt_pin` could accept T1/T6 — self-digests are tamper-evidence any same-UID writer can forge, so they granted authoritative status | §9.1, §9.2 rules R2/R3, §9.3 T0/T1/T3/T6 rows, §2.4, §10.1, D31, G-V16-01 | All three pins mandatory and fail closed: T0 requires `journal_pin` supplied ∧ byte-SHA-256 match; T1/T6 require `receipt_pin` supplied ∧ byte-SHA-256 match; pin absent or mismatched → T3 (never T0/T1/T6); self-digest recheck retained as necessary but not sufficient |
| V16-02 | `observe()`'s two quarantine calls were naked: `EEXIST` (`PublishConflict`) and `EPERM`/`EIO`/`ENOSYS`/`EXDEV`/`ENOSPC` (`PublishUnavailable`/`OSError`) escaped `observe()` as exceptions instead of resolving terminal states — the resolver could raise, breaking its exactly-one-T-row contract | §9.2 `try_quarantine` (both branches), §9.3 T5 row, D32, G-V16-02 | New `try_quarantine` helper that NEVER raises (`PublishConflict` → CONFLICT; `PublishUnavailable`/`PublishIdentityMismatch`/`OSError` → QUARANTINE-FAILED): final-branch QUARANTINE-FAILED → T5 immediately (final + unmovable stale staging fails closed), staging-branch → T5 on every outcome; seal-time step 5 stays strictly fatal (D28) |
| V16-03 | §7.5/K10–K12/T4 promised automatic T4→T6 receipt reconstitution ("`observe()` may complete CP2+CP3"), but the receipt's complete field set (admitted decisions, skip summaries, memory/diagnostics, pins, `wrapper_count`) exists only in the in-memory draft that dies with the process — no CP1-durable draft exists, so reconstitution is impossible | §5.3, §7.5, §8.5 K10–K12, §9.2, §9.3 T4 row, D14/D33, G-V16-03 | T4 made a TERMINAL incomplete state requiring operator review: no code path may write/fsync/publish a receipt after CP1, K10–K12 resolve T4 only, `observe()` is idempotent on T4; T4 still requires `pin` + full audit pass incl. check (g) with `egress_count` |
| V16-04 | The 12 MiB ceiling rested on quoted numbers with no reproducible measurement record in the document: probe methodology, raw CPython 3.12.3 values and the derivation of the 262,144 B native `HTTP_HEADROOM` term were external to the review artifact | new Appendix A, §6.5, §12, D34, G-V16-04 | New Appendix A: environment and protocol (CPython 3.12.3, `tracemalloc` over the exact normative sequences, worst-case inputs, fixed seeds), probe inventory (probe1–probe7), raw phase and banned-pattern tables (all values re-measured for this revision), and native-headroom accounting over a real local-TLS request via glibc `mallinfo2` (native-arena peak 277,120 B; conservative phase-1 total 8,739,616 ≤ 8,781,824 B) |
| V16-05 | §5.1.2 interleaved structure and body-decode per line (line 1's bad body masked line 5's bad keys — Step-1 validates ALL lines' structure before decoding ANY body, runstore.py:375–379) and parsed with plain `json.loads`, accepting duplicate keys and `NaN`/`Infinity` that Step-1's `_parse_json` rejects; the §0.2 exact accept-reject/error-precedence contract was therefore not met | §5.1.2 rewritten, §0.2, §6.5 phase 3, D24/D35, G-V16-05 | Five bounded stages with Step-1's exact precedence (both digests → records structure for ALL lines → records decode for ALL lines → events structure → events decode → count), Step-1's JSON dialect (`_no_duplicate_keys`, `parse_constant` rejection, verbatim messages, normalization net), structure dicts discarded and decode re-reads (O(1) memory, two reads per file); sole documented acceptance divergence: lines longer than `MAX_LINE` (impossible under the frozen schema; accepting them unbounded would violate the same review's budget) |
| V16-06 | Resolver↔audit check (g) drift: `wrapper_count` could reach `audit_run` as `None`/non-int (failing only by incident), an UNAUTHENTICATED receipt's count could feed check (g) because `receipt_pin` was verified after the audit, and T4's precondition of an independent integer count == `len(records)` was implicit | §9.2 restructured (authenticate receipt → resolve `wc` → mirror check (g) → audit), §9.3 T4 row, D36, G-V16-06 | Receipt authenticated (R3) before ANY of its fields is used; `wc` sourced only from `egress_count` or authenticated `receipt.wrapper_count`; check (g)'s three tests (supplied, int-not-bool, `== len(records)`) mirrored explicitly and failed closed to T3/T5 BEFORE `audit_run`; T4/T1/T6 rows each state their count precondition |
| V16-07 | §5.2.4 published the receipt with `expect = None`: between writing `.<run_id>.receipt.tmp` and `renameat2` a same-UID process could substitute the temp file; neither step 3 nor step 5 pinned its inode, so foreign bytes could be published as the receipt | §5.2.4, §5.2 step 3, D37, G-V16-07 | `st_tmp = os.fstat(tmp_fd)` captured on the creation descriptor BEFORE close and passed as `expect` into `publish_file()`: step 3 pins `(st_dev, st_ino)` pre-syscall, step 5 proves post-rename identity (type relative to `st_src`, so files publish too); substitution → step-3 require aborts before the syscall, or step-5 `PublishIdentityMismatch` after it → CP3 fails → T4 (or T3 when foreign bytes stand under the final name — `receipt_pin` never matches) — terminal, never T6 |

### 1.1 V15 findings resolved in v1.6

| ID | Finding (v1.5 review) | Where resolved | Resolution in one line |
|---|---|---|---|
| V15-01 | `stream_records` called `record_to_json(r)` twice per record (head and tail), each call base64-encoding the whole body (≤ 5,592,408 B string ×2 per record) — the seal's own framing destroyed even v1.4's declared 131,072 B phase-2 bound; it also mis-stated `body_b64`'s canonical position (it sorts FIRST, before `boundary_ms`, not between `boundary_ms` and `end_ns`), its head/tail byte joins produced invalid JSON, and the JSONL line terminator was never written | §5.1.1, §6.5 phase 2, D25, G-V15-01 | New metadata-only `record_meta_json(r)` (11 keys, never touches `r.body`; `record_to_json` banned from the writer), corrected `{`-head / `",`-tail framing proven byte-equal to `_lines([record_to_json…])` incl. a 4 MiB body (probe-verified), seal peak ≤ 151,552 B (measured 148,113 B) |
| V15-02 | `load_run` (runstore.py:370–388) reads whole files (`_read` → `read_bytes`) and splits them in memory (`raw.split(b"\n")`) holding every parsed record — verification of a 50 MiB session peaks at ≥ 139.8 MB, not 12 MiB; §6.5 phase 3 assumed an incremental reader that no code specified | new §5.1.2, §6.5 phase 3, §0.2, D24, G-V15-02 | New §5.1.2 incremental `load_run`: 64 KiB chunk reads, digest pass first (Step-1 error precedence preserved), `MAX_LINE`-capped line reader, decode → release → parse → release → encode → release → `b64decode(bytes)` record decoding (measured 11,188,261 B ≤ 11,202,224 B); declared the fourth Step-2 extension point with a byte-exact contract (v1.6's implementation of this row did NOT in fact preserve Step-1's precedence — found by V16-05, see §1.0) |
| V15-03 | §9.2 passed `wrapper_count = receipt.outer_count or structurally-derived`: `outer_count` is not a receipt key (`wrapper_count` is), `receipt` was referenced before it was parsed, and any value derived from the record stream makes audit check (g) tautological (audit.py:289–296 requires an INDEPENDENT counter, 623–624) | §9.2, §2.4, §10.1, §10.2, D26, G-V15-03 | `wrapper_count` sourced only from (1) the out-of-band `egress_count` print (`transport.sent`, flushed beside the manifest pin) or (2) `receipt.wrapper_count` (minted from `transport.sent` at CP3); disagreement → T3; absent both → check (g) fails → T5/T3; structural derivation explicitly banned |
| V15-04 | `load_run(final, pinned = pin if pin else receipt_pin(final))` called `receipt_pin` (a hex string, not a function) as if it produced a manifest pin; without `pin`, Step-1's `load_manifest` fails closed anyway (runstore.py:255–258), so v1.5's "structural verification still runs" was unimplementable for finals | §9.2, §9.3 T3/T4 rows, §7.5, §10.1, D27, G-V15-04 | `pin` mandatory to verify or recover a final: `pin` absent + final present → T5/T3 (fail closed, never T4/T6, no CP2/CP3 recovery); recovery (CP2+CP3) only with the independently supplied manifest pin; `receipt_pin` never used as a manifest pin |
| V15-05 | §5.2 step 5 swallowed a failed impostor quarantine (`except PublishUnavailable: pass`), leaving the impostor standing under `<run_id>` while the comment claimed T3; `PublishConflict` (EEXIST) escaped unhandled; `observe()`'s own quarantine calls could raise out of the resolver | §5.2 step 5, §5.2.5, §9.2, D28, G-V15-05 | Quarantine failure strictly fatal: no `pass`, every branch raises `PublishIdentityMismatch` with the cause chained, the runner dies before CP1b/CP2/CP3 so no receipt can exist; `observe()` catches quarantine failures and still returns exactly one T-row; classification-level guarantee with the residual stated |
| V15-06 | §5.2.5 bounded the mode (`& 0o022 == 0`) but never stated the UID trust boundary: no owner check (`st_uid`), no explicit statement about same-UID processes (which can rename inside `RUN_ROOT` without taking the flock) | §5.2 step 1, §5.2.5, D29, G-V15-06 | Owner validation `st_pfd.st_uid == os.geteuid()` at lock time; explicit two-tier boundary: different-UID writers kernel-prevented (owner-only mode + `O_NOFOLLOW` + identity re-proof), same-UID writers detected-not-prevented (step-5 inode proof, CP1b, pins → quarantine/T3/T5), §10.1 residual restated |
| V15-07 | The 12 MiB budget was asserted with formula-only phase peaks that did not match the code those paths would run (v1.5 phase 2 assumed 124,928 B while its own `record_to_json` calls cost ~11 MB; phase 3's `+1,024` term was 757 B short of measurement; no measured evidence) | §6.1, §6.5, §12, G-V13-04, G-V14-03, G-V15-07, D30 | Official `TRANSIENT_BUDGET_BYTES = 12,582,912` (D30) with per-instant measured proofs: peak₁ ≤ 8,781,824 (measured 8,724,640), peak₂ ≤ 151,552 (measured 148,113), peak₃ ≤ 11,202,224 (measured 11,188,261); budget = max ≤ 12,582,912, margin 1,380,688 B (12.3 %); banned patterns measured: `b64decode(str)` 15,381,335, `json.loads(bytes)` held 16,781,149, retained chunks 5,656,645 |

### 1.2 V14 findings resolved in v1.5 (retained)

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

### 1.3 V13 findings resolved in v1.4 (retained)

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
    sfd = os.open(staging_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC, dir_fd = pfd)   # staging mkdir'ed by the runner (K1)
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

5.1.2 **Normative reader — exact Step-1 compatibility, bounded passes (V15-02, V16-05; the fourth Step-2 extension
point, §0.2; D24/D35).** The Step-1 `load_run` (runstore.py:370–388) reads each file whole (`_read` →
`path.read_bytes()`, 246–250), splits it in memory (`raw.split(b"\n")`, `_jsonl` 279–286), parses every line and holds
all records: for a 50 MiB session that peaks at ≥ 139.8 MB of transient (≥ 2 × 4/3 × `SESSION_BODY_BUDGET_BYTES` of
jsonl bytes plus every parsed `body_b64` string) — an order of magnitude above the Domain B budget — and it cannot
support §6.5 phase 3's 12 MiB verification bound. Step 2 REPLACES `load_run` (decision **D24**): same name, same
keyword-only signature, same `LoadedRun`, same `ManifestError` messages, same accept-reject set — the differential
tests of §11 (G-V16-05) pin the contract. `audit_run` (audit.py:626) calls `load_run` and inherits it unchanged;
`load_manifest` (runstore.py:253) is unchanged — its manifest is ≤ 1 KiB by the 8-key schema (bounded full read) and
it already fails closed without a well-formed 64-hex pin (255–258, V15-04).

**Exact Step-1 precedence (V16-05), reproduced branch-for-branch.** In Step-1's `load_run` the records statement
evaluates `_jsonl(records_raw, …)` — truncation check, then per-line `_parse_json`, then per-line key-set check — to
COMPLETION before mapping `_record_from_json` (body decode + field validation) over it, and the records statement
completes before the events statement runs (runstore.py:375–379). The observable precedence is therefore exactly:

```
1. manifest errors (load_manifest; pin required, runstore.py:253–258)
2. records read OSError ("records.jsonl is missing or unreadable: …", 246–250)
3. events read OSError  (same message for events.jsonl)
4. records digest mismatch   5. events digest mismatch   (249–250 equivalents)
6. records truncation → records line-JSON/key errors for ALL lines → records body-decode/field errors for ALL lines
7. events truncation  → events line-JSON/key errors for ALL lines  → events body-decode/field errors for ALL lines
8. count mismatch (386–387)
```

v1.6 violated (6)/(7): its single interleaved pass decoded line 1's body before checking line 5's keys, so a bad body
masked a bad key set that Step-1 reports first; and its plain `json.loads` accepted duplicate keys and `NaN`/`Infinity`,
which Step-1's `_parse_json` (runstore.py:194–201: `object_pairs_hook = _no_duplicate_keys`, `parse_constant` →
`ManifestError`) rejects — different accept sets. Both defects are corrected below, together with Step-1's
normalization net (381–385). The reader is now five bounded stages over two reads per file:

```
function LOAD_RUN(run_dir, *, pinned_manifest_sha256) -> LoadedRun:   # normative; REPLACES Step-1 load_run (D24/D35)
    manifest = load_manifest(run_dir/manifest.json, pinned_sha256 = pinned_manifest_sha256)   # 1: unchanged; V15-04
    rec = scan_structure(records.jsonl, _RECORD_KEYS)   # 2: read OSError (verbatim 246–250) + sha256 over ALL bytes
    ev  = scan_structure(events.jsonl,  _EVENT_KEYS)    # 3: read OSError second, matching Step-1's read order
    if rec.hex != manifest.records_file_sha256:         # 4: digests BEFORE any parse — outside the net, as Step-1
        raise ManifestError("records.jsonl does not match the manifest digest (altered or substituted)")
    if ev.hex != manifest.events_file_sha256:           # 5:
        raise ManifestError("events.jsonl does not match the manifest digest (altered or substituted log)")
    try:                                                # Step-1's normalization net span (381–385), verbatim types:
        check_lines(rec, "records.jsonl")               #   (ValueError, TypeError, KeyError, AttributeError,
        if rec.struct_err is not None: raise rec.struct_err        # 6b: ALL record line-JSON/key errors (first wins)
        records = decode_pass(records.jsonl, _RECORD_KEYS, rec.hex)  # 6c: body decode + fields for ALL records
        check_lines(ev, "events.jsonl")                 # 7a: events truncation only after records are fully decoded
        if ev.struct_err is not None: raise ev.struct_err          # 7b: ALL events line-JSON/key errors
        events = decode_pass(events.jsonl, _EVENT_KEYS, ev.hex)     # 7c
        if len(records) != manifest.record_count or len(events) != manifest.event_count:
            raise ManifestError("record or event count does not match the manifest")   # 8: verbatim (386–387)
    except ManifestError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ManifestError(f"persisted run artifact is malformed: {exc!r}") from exc   # verbatim (384–385)
    return LoadedRun(tuple(records), tuple(events), manifest)

scan_structure(path, keys) -> Scan2:       # *runner*: ONE bounded read — hash + line facts + FIRST structure error
    h = sha256(); n = 0; over_cap = None; struct_err = None; last = b""
    with open(path, "rb") as f:             # OSError → verbatim "{what} is missing or unreadable: …"
        while True:
            raw = f.readline(MAX_LINE + 2)  # CAP by API: <= MAX_LINE+2 bytes per read — bounded by construction
            if raw == b"": break
            n += 1; h.update(raw)           # incremental hashing: O(1) memory for any file size
            last = raw[-1:]                 # truncation fact: final byte of the final line read
            if raw.endswith(b"\n"):
                if len(raw) - 1 > MAX_LINE and over_cap is None: over_cap = n        # newline-terminated breach
            elif len(raw) > MAX_LINE and over_cap is None: over_cap = n              # capped read, no newline
            if struct_err is None:          # parse structure ONLY until the first error; afterwards just hash
                try:
                    obj = parse_line(raw, f"{path.name} line {n}")   # Step-1 JSON dialect (below)
                except ManifestError as exc:
                    struct_err = exc        # DEFERRED: digest checks (4/5) must run first, exactly as Step-1 does
                else:
                    if not isinstance(obj, dict) or set(obj) != keys:
                        struct_err = ManifestError(f"{path.name} line {n}: unexpected or missing keys")  # verbatim 284
                    del obj                 # DISCARD — no body decoded, nothing retained: O(1) memory per line
    return Scan2(hex = h.hexdigest(), truncated = n > 0 and last != b"\n",
                 over_cap = over_cap, struct_err = struct_err)

check_lines(scan, what):                    # truncation → MAX_LINE, in Step-1's truncation-first position
    if scan.truncated: raise ManifestError(f"{what} is truncated (no final newline)")                # verbatim 280–281
    if scan.over_cap:  raise ManifestError(f"{what} line {scan.over_cap} exceeds the maximum line length")
    # the MAX_LINE cap above is the SOLE documented acceptance divergence from Step-1 (D35): valid records fit it by
    # construction (body <= MAX_BODY_BYTES ⇒ line <= MAX_LINE), and accepting unbounded lines would violate the
    # Domain B budget that V15-02/D30 mandate. G-V16-05 differential-tests every other input.

parse_line(raw, what) -> dict:              # Step-1 `_parse_json` dialect (runstore.py:194–201), memory-ordered
    try:
        text = raw.decode("utf-8"); del raw # the ONLY deviation from calling `_parse_json` verbatim: release the
        return json.loads(text,             # line bytes BEFORE parsing (holding line+text+parsed = 16,781,149 B,
              object_pairs_hook = _no_duplicate_keys,      # measured, banned by §6.5 phase 3). It changes NO
              parse_constant = lambda c: (_ for _ in ()).throw(  # observable outcome: the bytes are already copied
                  ManifestError(f"{what}: {c} is not allowed")))  # into text; G-V16-05 differential-tests both.
    except ManifestError:                   # duplicate keys / NaN / Infinity — verbatim, unwrapped (Step-1 195–196)
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{what} is not valid JSON: {exc}") from exc                   # verbatim (197–201)

decode_pass(path, keys, expected_hex) -> list:  # *runner*: SECOND read — body decode + fields; re-hashes (TOCTOU)
    out = []; h = sha256(); n = 0
    with open(path, "rb") as f:
        while True:
            raw = f.readline(MAX_LINE + 2)
            if raw == b"": break
            n += 1; h.update(raw)           # re-hash while decoding: closes the two-pass TOCTOU window
            ... same truncation/MAX_LINE re-checks as scan_structure (mid-read swap only, fail closed) ...
            tag = f"{path.name} line {n}"
            obj = parse_line(raw, tag)
            if not isinstance(obj, dict) or set(obj) != keys: raise ManifestError(f"{tag}: unexpected or missing keys")
            try:
                value = obj.pop("body_b64")  # removes the <= 5,592,408 B str from the dict FIRST
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

Why each stage exists and how the memory stays bounded (§6.5 phase 3): the structure stage parses one line, checks its
key set and DISCARDS the dict — a suspended generator or a retained list would keep every `body_b64` string alive
(Step-1's own 139.8 MB failure); the decode stage is the line's sole owner at every instant with the v1.6 release order
(decode → release → parse → release → encode → release → `b64decode(bytes)`), peaking at the same ≤ 11,202,224 B bound
(measured 11,188,261 B decode / ≤ structure-pass value, Appendix A). Two reads per file (hash+structure, then decode)
≈ 3 × `records.jsonl` + 3 × `events.jsonl` ≈ 205 MB of sequential I/O for a full session — offline verification,
O(1) memory either way. Valid records fit `MAX_LINE` by construction (body ≤ `MAX_BODY_BYTES`, plan-constrained
path/headers, bounded incident `error` strings); any longer line — only producible by foreign or corrupt content —
fails closed before parsing (the one documented acceptance divergence, D35). Files mutated between the two reads are
caught by the decode stage's end-of-pass re-hash (digest error) or fail parsing — strictly fail-closed, a superset of
Step-1's rejections for stable inputs; for every stable input the accept-reject set and the first-raised
`ManifestError` message are identical to Step-1's, modulo the `MAX_LINE` cap (G-V16-05).

5.2 **Publication — exact `renameat2(RENAME_NOREPLACE)` contract (V13-02, V13-03).** This sequence publishes either a run
directory, the quarantine directory, or the receipt file; the normative unit is `publish_dir()`/`publish_file()`. On Linux,
Python 3.12 exposes **no** `os.RENAME_NOREPLACE` (verified on the target interpreter); the syscall is reached through
`ctypes`, and a missing libc symbol is a fail-closed error, never a fallback.

```
function PUBLISH_COMPONENT(pfd, staging_name, final_name, expect: Stat | None) -> int:    # normative
    # 0. Preconditions (both names are SINGLE components of the same locked parent):
    for name in (staging_name, final_name):
        require name not in ("", ".", "..") and "/" not in name and "\0" not in name      # component validation
    # 1. Identity of the locked descriptor vs the path (parent must not have been swapped) + boundary checks:
    st_pfd  = os.fstat(pfd)                                       # the descriptor we locked (§5.2.1)
    st_path = os.stat(RUN_ROOT, follow_symlinks=True)             # absolute path only (§5.2.5); what the path names now
    require (st_pfd.st_dev, st_pfd.st_ino) == (st_path.st_dev, st_path.st_ino)            # else abort, no publication
    require (st_pfd.st_mode & 0o022) == 0                         # RUN_ROOT not group/other-writable (§5.2.5 boundary)
    require st_pfd.st_uid == os.geteuid()                         # RUN_ROOT owned by THIS uid (V15-06, §5.2.5)
    # 2. Destination must not exist (advisory pre-check; renameat2 is the enforcement):
    try:      os.stat(final_name, dir_fd = pfd, follow_symlinks = False); exists = True
    except FileNotFoundError: exists = False
    if exists: raise PublishConflict(final_name)                  # → quarantine path (§5.5), never overwrite
    # 3. Staging identity: same parent, inode pinned against `expect` (V16-07): the os.fstat() of the descriptor
    #    that CREATED the staging name — the receipt temp (§5.2.4) — or of the descriptor it was opened through
    #    (directory targets), captured by the caller, never re-derived from the path:
    st_src = os.stat(staging_name, dir_fd = pfd, follow_symlinks = False)
    if stat.S_ISREG(st_src.st_mode):
        require expect is not None                        # FILE staging (the receipt temp) MUST carry its creation fstat
    else:
        require stat.S_ISDIR(st_src.st_mode)              # run/quarantine targets are directories
    require expect is None or (st_src.st_dev, st_src.st_ino) == (expect.st_dev, expect.st_ino)
        # with §5.2.4's mandatory `expect` this is an unconditional PRE-syscall pin for the receipt: a same-UID
        # substitution of .<run_id>.receipt.tmp between close and renameat2 is detected BEFORE the syscall; the
        # residual stat→syscall window is closed after it by step 5's post-rename proof
    # 4. THE SYSCALL — both directory fds anchored to the locked parent, RENAME_NOREPLACE:
    #      renameat2(int pfd, const char *staging_name, int pfd, const char *final_name, unsigned int flags)
    #      flags = RENAME_NOREPLACE = 1 (Linux <linux/fs.h>); names relative to pfd, NOT to the CWD, NOT to AT_FDCWD
    libc = ctypes.CDLL(None, use_errno = True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None: raise PublishUnavailable("libc has no renameat2")               # fail closed (§5.2.3)
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype  = ctypes.c_int
    rc = renameat2(int(pfd), os.fsencode(staging_name), int(pfd), os.fsencode(final_name), 1)
    if rc != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST: raise PublishConflict(final_name)   # raced despite §5.2 step 2 → quarantine
        raise PublishUnavailable(f"renameat2 failed: errno {err}")  # ENOSYS/EINVAL/EOPNOTSUPP/EXDEV/EPERM: NO FALLBACK
    # 5. Post-rename identity: rename preserves (dev, ino) — proves WE moved OUR staging, not an impostor.
    #    V14-07/V15-05: a mismatch (source name swapped between step 3 and the syscall) means the directory now under
    #    final_name is an IMPPOSTOR. Its quarantine is ATTEMPTED UNCONDITIONALLY and every failure is STRICTLY FATAL:
    #    no `pass`, no swallowed branch, no fall-through — each path raises the single fatal type with its cause
    #    chained (consequences below §5.2.4; classification limits §5.2.5):
    st_dst = os.stat(final_name, dir_fd = pfd, follow_symlinks = False)
    # identity + type proof (V16-07): inode equality, and type RELATIVE to st_src — which step 3 already typed:
    # a directory stays a directory, the receipt temp stays a regular file; any inode or kind change = IMPPOSTOR
    if (st_dst.st_dev, st_dst.st_ino) != (st_src.st_dev, st_src.st_ino) or stat.S_ISDIR(st_dst.st_mode) != stat.S_ISDIR(st_src.st_mode):
        try:
            publish_quarantine_of(final_name)          # renameat2(NOREPLACE) final → <run_id>.unverified (§5.5)
        except BaseException as q_exc:                 # PublishConflict (EEXIST), PublishUnavailable, OSError, …
            raise PublishIdentityMismatch(final_name) from q_exc # cause CHAINED; never `pass`; the runner dies HERE
        raise PublishIdentityMismatch(final_name)      # mismatch fatal even when the quarantine succeeded
    return st_dst
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

5.2.4 **Receipt publication (v1.7, V16-07: temporary-inode binding).** The receipt temp is created by
`tmp_fd = os.open(".<run_id>.receipt.tmp", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0o644, dir_fd = pfd)` in
`RUN_ROOT`, fully written and fsynced through THAT descriptor; then `st_tmp = os.fstat(tmp_fd)` is captured on the
creation descriptor BEFORE `os.close(tmp_fd)` and passed as `expect` into
`publish_file(pfd, ".<run_id>.receipt.tmp", "<run_id>.receipt.json", expect = st_tmp)` (`final_name =
<run_id>.receipt.json`; the step-3 type check accepts a regular file). Publication with `expect = None` is **BANNED**
for the receipt (G-V16-07): between `close` and `renameat2` a same-UID process may substitute the temp name, and
`expect` makes step 3 compare the temp's `(st_dev, st_ino)` against the inode of the descriptor that created it
BEFORE the syscall — a substitution raises before publication, and a substitution inside the residual stat→syscall
window is caught by step 5's post-rename proof (`PublishIdentityMismatch`). Either way CP3 fails → the run stays
**T4 (terminal, operator review; §7.5/D33)** — or **T3** in the residual where step 5 could not move the impostor
aside and foreign bytes stand under the final name (the operator's `receipt_pin` never matches them); terminal either
way, and T6 requires the authenticated publication of THIS temp's bytes. A crash before the syscall leaves only the temp name (ignored by the
resolver → T4); after the syscall the receipt is complete (→ T6 path). Torn receipts under the final name are
impossible by construction.

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

* **Source-identity race (stat → renameat2).** The step-3 `stat(staging_name)` window can never be fully eliminated
  (`renameat2` takes names, not descriptors), so it is closed by detection *with consequence*: the step-5 post-rename
  inode proof compares the published inode against the pre-syscall stat, and on mismatch the runner immediately
  quarantines the published name (§5.2 step 5) — the impostor is moved out from under `<run_id>`, or, if the filesystem
  refuses that rename, the failure is strictly fatal (V15-05) and the standing impostor can only ever resolve T5/T3,
  never silent success. Step 3 re-stats immediately before the syscall to shrink the window; the re-stat narrows, the
  proof closes.
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
    (HTTP_HEADROOM = 262,144 B: http.client + ssl user-space buffers, header dict, malloc overhead — design
     constant, asserted by the G-V13-04 allocation spy. Measured core without headroom: 8,462,496 B →
     8,724,640 B with headroom ≤ 8,781,824 B.)

Phase 2 — seal, §5.1.1 metadata-only writer (V15-01): ONE 48 KiB body slice + ONE ≤ 64 KiB base64 chunk + the
          CPython base64 encoder's 32,768 B working buffer + ≤ 4,096 B of digest line, head/tail fragments and
          framing — all live at the `b64encode` instant; `chunk` is `del`ed before the next slice:
    peak₂ ≤ 49,152 + 65,536 + 32,768 + 4,096 = 151,552 B   (measured 148,113 B)
    (banned patterns, measured: retaining chunks across iterations 5,656,645 B; v1.5's two `record_to_json(r)`
     calls per record allocate the full ≤ 5,592,408 B base64 string twice — G-V15-01 kills both. v1.4's model
     (full base64 string + full JSON line = 11,184,816 B) and the current Step-1 write_run (≥ 139.8 MB) remain
     excluded by D18.)

Phase 3 — verify, §5.1.2 incremental `load_run` (V15-02): the reader holds at most ONE line buffer, its decoded
          text and the parsed `body_b64` string at once, plus the file object's 8 KiB buffer and json/dict
          overhead; the per-line release order is normative (read ≤ MAX_LINE+2 → decode → `del` line bytes →
          json.loads → `del` text → `.encode("ascii")` → `del` the str → `b64decode(bytes)` → `del` raw):
    MAX_LINE = 4 × ⌈MAX_BODY_BYTES / 3⌉ + 512 (framing) = 5,592,920 B
    peak₃ ≤ 2 × MAX_LINE + 16,384 = 11,202,224 B   (measured 11,188,261 B on a MAX_LINE line; +8,192 file
                                                      buffer + ~2,624 json/dict overhead -> 11,196,453 B ≤ bound)
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
plan/skips/admitted decisions ≤ 300 KiB; manifest + receipt draft ≤ 100 KiB → ≈ 2.0 MiB ≤ budget. Exceeding any term aborts
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
CP1  rc == 0 from renameat2(pfd, ".<run_id>.staging", pfd, "<run_id>", RENAME_NOREPLACE)
     → phase = COMMITTING/SEALED;  pin and abort_seq were already flushed out-of-band (§5.1)
CP1b post-rename content re-verification (v1.5, V14-07; pin-only call restated V15-04), lock still held:
     run = load_run(final, pinned_manifest_sha256 = pin)   # the out-of-band MANIFEST pin of §10.1 — receipt_pin is
     NEVER used as a manifest pin, and observe() without `pin` resolves T3 (or T5), never T4/T6 — and the manifest
     digest verifies → otherwise quarantine the published final via renameat2(NOREPLACE) into
     <run_id>.unverified (§5.2.5), stop → T5; a crash here equals K10 (final, no receipt) → observe() re-verifies →
     T4 or T3 — an impostor never receives a receipt
CP2  os.fsync(pfd) returns 0                                   # namespace durable; failure → stop → T4 (K11)
CP3  receipt published (V16-07: temporary-inode binding):
     tmp_fd = os.open(".<run_id>.receipt.tmp", O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0o644, dir_fd = pfd)
     → write canonical receipt JSON → os.fsync(tmp_fd)
     → st_tmp = os.fstat(tmp_fd)     # captured on the CREATION descriptor, BEFORE close (V16-07)
     → os.close(tmp_fd)
     → publish_file(pfd, ".<run_id>.receipt.tmp", "<run_id>.receipt.json", expect = st_tmp)
         # renameat2(RENAME_NOREPLACE); step 3 pins (st_dev, st_ino) pre-syscall, step 5 proves it post-rename
     → os.fsync(pfd)
     → phase = COMMITTED; resolve (§9.2); receipt fields carry terminal_state, outcome, reason, exit_code
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
when `journal_pin` is supplied and matches. The strict parser recomputes `journal_digest` over the other eight keys
(naive edits fail), and `observe()` COMPARES the file's byte SHA-256 against `journal_pin` **as a mandatory check
(v1.7, V16-01/D31): `journal_pin is None` → T3, mismatch → T3 — T0 is unreachable without the out-of-band pin**. The
self-digest alone is tamper-evidence, never authentication: anyone with `RUN_ROOT` write access can recompute it, so a
self-digest by itself must never grant authoritative status (v1.6's optional-pin reading is removed).

9.2 **Resolver precedence (normative `observe()`), deterministic given disk state only** (`pin`, `egress_count`,
`receipt_pin`, `journal_pin` supplied out of band). v1.7 fail-closed rules (V16-01/D31): **ALL THREE pins are
MANDATORY and each is checked before its target's state may be claimed** — (i) `pin` is MANDATORY to verify or recover
a final (V15-04 unchanged): `receipt_pin` is a hex string, never a manifest pin, Step-1's `load_manifest` fails closed
without the pin (runstore.py:255–258), so a present final with `pin is None` resolves `T5 if conflict else T3` BEFORE
any load, and T4/T6 are unreachable without the independently supplied manifest pin ("structural-only" verification of
finals does not exist); (ii) `journal_pin` is MANDATORY for T0 — absent or mismatched → T3 (§9.1); (iii) `receipt_pin`
is MANDATORY for T1/T6 — absent or mismatched → T3 (R3 below). Self-digests (`journal_digest`, `receipt_digest`) are
re-verified as necessary but NEVER sufficient: a self-digest alone grants no authoritative state, because anyone with
`RUN_ROOT` write access can recompute it (V16-01). Full forgery by an adversary that controls records, files AND pins
together stays out of scope — stated limit of `runstore`, §10.1. v1.5 harmonized this pseudocode with the §9.3 table
over ALL edge-case artifact combinations (V14-06): inputs are five artifacts (refusal, staging, final, receipt,
quarantine) × receipt validity × the closed outcome enum × (`pin`, `egress_count`, `journal_pin`, `receipt_pin`)
presence; every combination resolves to exactly one row of §9.3. v1.7 adds two structural rules: **R2** every
quarantine attempt inside `observe()` goes through `try_quarantine` (V16-02 — no exception may escape the resolver),
and **R3/R4** the receipt is authenticated BEFORE any of its fields is used, with audit check (g) mirrored explicitly
before `audit_run` (V16-06).

The classification helper (normative, V16-02/D32) — NEVER raises; used at EVERY quarantine site inside `observe()`:

```
function TRY_QUARANTINE(name) -> CONFLICT | QUARANTINE-FAILED:   # observe()-internal; never raises (V16-02)
    try:
        publish_quarantine_of(name)            # renameat2(NOREPLACE) name → <run_id>.unverified (§5.5)
        return CONFLICT                        # moved aside; the conflict signature now stands (K1/K8)
    except PublishConflict:
        return CONFLICT                        # EEXIST: an unverified sibling already exists — also a conflict
    except (PublishUnavailable, PublishIdentityMismatch, OSError):
        return QUARANTINE-FAILED               # EPERM/EIO/ENOSPC/EXDEV/ENOSYS/… — classified, never propagated
```

Seal-time quarantine (§5.2 step 5, D28/V15-05) is NOT routed through this helper: there a failed impostor quarantine
is strictly fatal by design. The helper covers only `observe()`'s two staging-quarantine sites (V16-02): every outcome
becomes a deterministic fail-closed terminal state — CONFLICT keeps the conflict flag, QUARANTINE-FAILED resolves T5 —
so no `EEXIST`/`EPERM`/`EIO`/`ENOSPC` can escape `observe()` as an exception.

```
function OBSERVE(run_id, pin | None, egress_count | None, receipt_pin | None, journal_pin | None) -> TerminalState:
    # ENTRY SNAPSHOT — read before any mutation this observation performs, so a step-2 self-quarantine (or a
    # stale-sibling quarantine by an earlier observation) never flips the state seen by a later one:
    q_pre = exists(<run_id>.unverified)                  # pre-existing quarantine (K8 / prior K-row)
    # 1. refusal journal
    if refusal_exists(run_id):
        raw = read_bytes(refusal)
        j = parse_strict(raw)                            # exact 9-key set, exact types, journal_digest verified
        if j is None or not j.format == "obs-refusal/1": return T2      # torn/invalid → crash, NEVER T0
        if journal_pin is None or sha256(raw) != journal_pin:
                                     return T3            # V16-01: journal_pin MANDATORY — absent/mismatch fails
                                                          # closed; self-digest alone never grants T0 (D31)
        if final_exists(run_id) or staging_exists(run_id) or q_pre:
                                     return T3           # refusal ∧ artifacts/quarantine contradiction
        return T0                                        # journal_pin present ∧ byte-SHA-256 matched (V16-01);
                                                          # (record_count reported, not resolved here)
    # 2. final run directory
    if final_exists(run_id):
        conflict = q_pre                                 # our quarantined attempt alongside a final (K8 signature)
        if staging_exists(run_id):                        # stale sibling (K1/K8); T unchanged when it moves:
            qc = try_quarantine(staging)                 # V16-02: NEVER raises — every outcome classified
            if qc is QUARANTINE-FAILED: return T5        # final + UNMOVABLE stale staging → fail closed (§9.3 T5)
            conflict = True                              # CONFLICT: moved aside, or unverified sibling already there
        # Verification-failure precedence (V14-06): K8's foreign final cannot authenticate against our pin and fails
        # load/audit → T5 + conflict report; an own final failing with no conflict → T3. A final that PASSES
        # verification ignores `conflict`, so re-observation of a run whose stale sibling was quarantined stays
        # T4/T1/T6. With no out-of-band pin the two cases are indistinguishable AND unverifiable: both fail closed
        # before any load (V15-04) — stated limit (§10.1).
        if pin is None: return T5 if conflict else T3     # V15-04: never load a final without its manifest pin
        run = load_run(final, pinned = pin)              # receipt_pin is a hex string — never passed as a pin
        if run fails structurally:      return T5 if conflict else T3
        # R3 (V16-01/V16-06): the receipt is AUTHENTICATED before ANY of its fields is used — receipt_pin is
        # MANDATORY for T1/T6 (absent → T3, byte-SHA-256 mismatch → T3, D31). No count and no outcome from an
        # unauthenticated receipt may reach the audit or the classifier.
        raw = read_bytes(receipt_path) if receipt_exists(run_id) else None
        receipt = parse_strict(raw) if raw is not None else None   # exact key set, receipt_digest verified (V14-05)
        if receipt_exists(run_id):
            if receipt is None or receipt.run_id != run_id:
                                     return T3            # torn/foreign receipt → FAILED-AUDIT (V14-06)
            if receipt_pin is None or sha256(raw) != receipt_pin:
                                     return T3            # V16-01: receipt_pin MANDATORY — self-digest never enough
            if receipt.manifest_sha256 != pin:
                                     return T3            # content chain broken (pin non-None above; V15-04)
        # wrapper_count: exactly two admissible INDEPENDENT sources (V15-03) — (1) the out-of-band egress_count
        # print (§10.1(1b): transport.sent, flushed beside the manifest pin) and (2) receipt.wrapper_count — now
        # only from an AUTHENTICATED receipt (R3). Any count derived from the record stream is BANNED: it would make
        # audit check (g) tautological (audit.py:289–296 requires a caller-supplied counter, 623–626).
        wc = egress_count if egress_count is not None else (receipt.wrapper_count if receipt is not None else None)
        # R4 (V16-06/D36): explicit mirror of audit check (g) BEFORE audit_run — wc must be an integer (not bool,
        # not None) and must equal len(run.records); any other combination fails closed (conflict → T5, else T3)
        # instead of reaching audit_run and failing only "by incident":
        if not isinstance(wc, int) or isinstance(wc, bool) or wc != len(run.records):
                                     return T5 if conflict else T3   # check (g) mirror: supplied / int / == len
        result = audit_run(..., wrapper_count = wc, abort_seq = abort_condition_seq(run.records), ...)
        if not result.ok:               return T5 if conflict else T3   # after R4 only a TOCTOU change lands here
        if not receipt_exists(run_id):  return T4          # final NAME only; .receipt.tmp ignored (§5.2.4);
                                     # preconditions: pin ∧ audit pass ∧ wc from egress_count (V16-03/V16-06)
        if egress_count is not None and receipt.wrapper_count != egress_count:
                                     return T3            # independent egress sources disagree (V15-03)
        if receipt.outcome == "ABORTED":       return T1   # receipt authenticated (R3), count cross-checked above
        if receipt.outcome in {"COMPLETE-VALID", "INCONCLUSIVE-TIMING", "FAILED"}: return T6
        return T3                                        # outcome outside the closed enum → FAILED-AUDIT (V14-06)
    # 3. staging without final
    if staging_exists(run_id):
        if not q_pre: try_quarantine(staging)            # V16-02: NEVER raises; EEXIST/EPERM/EIO/… classified
        return T5                                        # staging present → T5 on EVERY outcome (K1/K7), fail closed
    # 4. pre-existing quarantine alone (stale K-row result)
    if q_pre:                                            return T5
    # 5. nothing
    return T2                                            # crash with no trustworthy artifact (incl. missing journal)
```

9.3 **T0–T6 resolver table (exhaustive; every state is exactly one row):**

| T | Name | Defining persisted state (all conditions) | Exit | Recovery allowed |
|---|---|---|---|---|
| T0 | REFUSED | valid `obs-refusal/1` ∧ `journal_pin` supplied ∧ sha256(journal bytes) = `journal_pin` (V16-01) ∧ no final ∧ no staging ∧ no quarantine | 2 | none (terminal) |
| T1 | ABORTED-SEALED | final ∧ verify+audit pass ∧ receipt valid (incl. `receipt_pin` supplied ∧ sha256(receipt bytes) = `receipt_pin`, V16-01) ∧ `receipt.outcome = ABORTED` (incident ladder, N/T/E rows, or signal reason) | 1 / 130 / 143 | none; owner reports to reviewer before rerun |
| T2 | INCONCLUSIVE-CRASH | nothing for `run_id`, or journal present but torn/invalid, or (power loss) rename lost before CP2 | 1 | none automatic: rerun is a NEW `run_id` |
| T3 | FAILED-AUDIT | final present that fails verification — including a final presented with no out-of-band manifest pin, fail-closed V15-04 — with NO staging/quarantine conflict ∨ receipt invalid (torn/foreign/digest-or-pin mismatch/`receipt_pin` absent or mismatched V16-01/`wrapper_count` disagreement V15-03/outcome outside the enum) ∨ refusal present with `journal_pin` absent or mismatched (V16-01) ∨ refusal ∧ artifacts/quarantine contradiction | 1 | none; quarantine-or-report per reviewer |
| T4 | SEALED-UNRECEIPTED | final ∧ pin supplied ∧ verify+audit pass (incl. check (g): `egress_count` supplied, integer, `== len(records)` — V16-06) ∧ receipt absent (no pin ⇒ resolves T3/T5, never T4 — V15-04; no admissible independent count ⇒ T5/T3, never T4 — V16-06) | 1 | NONE — TERMINAL incomplete state requiring operator review (v1.7, V16-03/D33): no CP1-durable receipt draft exists, so no code path may write/fsync/publish a receipt after CP1; a rerun uses a new `run_id` |
| T5 | QUARANTINED | staging found without final (K1/K7), or `<run_id>.unverified/` present with final absent (any K-row/`INVALID-PACING`/seal failure/E11/N14 path), or final present that fails verification while staging/quarantine is also present (K8 conflict, reported), or final present whose stale staging sibling cannot be moved aside (`try_quarantine` → QUARANTINE-FAILED, V16-02), or a final presented without its manifest pin while a conflict exists (V15-04 fail-closed) | 1 | none (fresh `run_id` for a rerun) |
| T6 | COMMITTED | S holds (§2.4 — incl. `receipt_pin` supplied ∧ sha256(receipt bytes) = `receipt_pin`, V16-01); `receipt.outcome` ∈ {COMPLETE-VALID, INCONCLUSIVE-TIMING, FAILED} | 0 / 1 / 1 | none |

Exhaustiveness argument (v1.5, V14-06; extended v1.6 for V15-03/V15-04; v1.7 for V16-01/V16-02/V16-06): the inputs
are the five filesystem artifacts (refusal, staging, final, receipt, quarantine), receipt validity (torn / foreign /
digest-or-pin mismatch / `receipt_pin` absent / valid) and the closed outcome enum (three values ∪ invalid), plus the
out-of-band inputs `pin`, `egress_count`, `journal_pin`, `receipt_pin` (present/absent each — V15-04/V15-03/V16-01)
and both quarantine outcomes (CONFLICT / QUARANTINE-FAILED, V16-02). Steps 1→5 partition them: refusal present →
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
check (g), audit.py:289–296), and disagreement between the two independent sources resolves T3 (§9.2). (2) After CP3
the runner prints `sha256(<run_id>.receipt.json bytes)` with a flush — the receipt pin; `observe()` **REQUIRES**
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
the strict parser recomputes it, and after CP3 the runner prints the receipt's byte SHA-256 out-of-band (§10.1),
which `observe()` verifies when `receipt_pin` is supplied. `wrapper_count` is minted from `transport.sent` at CP3
and is the second admissible independent egress source (§10.1(1b), V15-03).

10.3 **Frozen schemas:** `records.jsonl` object keys = `_RECORD_KEYS` (12 keys, exact); `events.jsonl` keys = `_EVENT_KEYS`;
`manifest.json` keys = the 8 manifest keys; refusal and receipt keys as specified above. Any new detail belongs in the
free-form `error` string (records) or the receipt's `reason`/`diagnostics` (protocol §0/§3.3 alignment: record shapes stay
frozen under `obs-run-manifest/1`).

## 11. Gates and decisions (v1.7 adds G-V16-01–07 and D31–D37; v1.6 adds G-V15-01–07 and D24–D30; v1.4 additions; v1.3 G-R1–G-R12, D1–D10 remain in force where still applicable)

| Gate | Assertion | Killer-test sketch |
|---|---|---|
| G-V13-01 | ladder branch order == `abort_condition_seq` order | generate record streams hitting B1/B2/B3/B4 boundaries (non-200 mid-streak; `CANCEL_FAILED` with `status=None`; streak 2→3; 200 reset); assert runner abort `seq` == `abort_condition_seq` result; mutation: swap B1/B2 → must fail |
| G-V13-02 | exact syscall arguments | fake libc records `(pfd, b".<id>.staging", pfd, b"<id>", 1)`; component names with `/`, `..`, `\0` rejected pre-call; EEXIST → `PublishConflict` |
| G-V13-03 | identity checks + no fallback | spy asserts `os.rename`/`os.replace`/`os.link`/`shutil.move` NEVER called during publish; parent-path swap (fstat≠stat) aborts; ENOSYS/EINVAL → `PublishUnavailable` (no fallback path exists); post-rename inode mismatch quarantines the published name, then raises (V14-07) |
| G-V13-04 | budgets | chunk loop at `budget−1 / budget / budget+1` bytes; 4 MiB+1 response; §6.5 three-phase peaks pinned to ≤ 8,781,824 / 151,552 / 11,202,224 B under the 12,582,912 B budget (measured 8,724,640 / 148,113 / 11,196,453 B, V15-07); gzip bomb hits 1000:1 and 50 MiB ceilings; mutation: remove chunk check → killer fails |
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
| G-V16-04 | reproducible memory accounting (V16-04) | CI reruns the Appendix A protocol (probe1–probe7, CPython 3.12.3, fixed inputs) → recorded values must match Appendix A: 8,462,496 / 148,113 / 11,188,261 / 11,188,197 B, native `mallinfo2` Δ 277,120 B → conservative phase-1 total 8,739,616 ≤ 8,781,824 B; a drifted value or missing Appendix row fails the gate |
| G-V16-05 | loader precedence + dialect equivalence (V16-05) | differential test: for every input class (bad body on line 1 + bad keys on line 5; duplicate key; `NaN`; non-UTF-8; truncated; line > `MAX_LINE`; digest mismatch; count mismatch) assert Step-1's `load_run` and the new `load_run` raise the SAME `ManifestError` message at the SAME precedence position on the same bytes — sole exemption: lines > `MAX_LINE` (new rejects, Step-1 cannot); mutation: decode a body before all-lines structure validation → killer fails |
| G-V16-06 | audit check (g) alignment (V16-06) | property test: every `wc` that reaches `audit_run` is `int` (not `bool`, not `None`) and `== len(records)` — the R4 mirror enforces it pre-audit; `wc` ∈ {absent, bool, str, ≠ len} → T5-with-conflict or T3, and `audit_run` is NEVER called with an invalid `wc`; ordering spy: an unauthenticated receipt's `wrapper_count` never reaches the audit (R3 before use); mutation: delete the R4 mirror → killer fails |
| G-V16-07 | receipt temp-inode binding (V16-07) | spy substitutes `.<run_id>.receipt.tmp` for a foreign file between `close(tmp_fd)` and `publish_file` → step-3 `expect` mismatch → publication refused BEFORE `renameat2` (or, for a swap after the step-3 stat, step-5 `PublishIdentityMismatch`) → CP3 fails → `observe()` = T4 (the real receipt never published) or T3 (foreign bytes standing under the final name fail `receipt_pin`) — NEVER T6; grep gate: §5.2.4 passes `expect = st_tmp`, never `expect = None` for a file target |

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
impossible under the frozen schema and mandated by the Domain B budget (V16-05);
**D36** `observe()` mirrors audit check (g) explicitly before `audit_run` (supplied, integer-not-bool, `==
len(records)`) and only ever passes an `egress_count`/authenticated-`receipt.wrapper_count` value; receipt
authentication (R3) precedes every use of a receipt field (V16-06);
**D37** receipt publication binds the temp inode: `st_tmp = os.fstat(tmp_fd)` on the creation descriptor before
close, passed as `expect` into `publish_file()` — never `expect = None` for a file target; substitution → CP3 fails
→ T4 (or T3 if foreign bytes stand at the final name) — a substituted receipt never authenticates (V16-07).

## 12. Normative constants (single table; source of truth `tools/obs/params.py` + runner additions)

| Constant | Value | Source / section |
|---|---|---|
| `SPACING_NS` / `WINDOWS` (OBS-02) | 600 ms; (1 s, 2), (60 s, 60) open-left/closed-right | params.py, PACE-2/3 |
| `OBS01_SPACING_NS` / `OBS01_WINDOWS` (OBS-01) | 2 s; (2 s, 1), (60 s, 30) | params.py |
| `DEADLINE_NS` / `AUDIT_MAX_DURATION_NS` / `CANCEL_GRACE_NS` | 17 s / 18 s / 1 s (CANCEL_FAILED window [17,19] s) | params.py, PACE-8, audit (e) |
| `CONNECT/READ/WRITE/POOL_TIMEOUT_S` | 5.0 / 12.0 / 5.0 / 1.0 s; `SEND_TIMEOUT_S` 0.25 s | params.py |
| `MAX_CONSECUTIVE_NO_RESPONSE` | 3 | params.py, ladder B3 |
| `MAX_BODY_BYTES` / `SESSION_BODY_BUDGET_BYTES` | 4,194,304 B / 52,428,800 B | transport.py / runner, §6 |
| `MAX_LINE` | 5,592,920 B (4 × ⌈MAX_BODY_BYTES / 3⌉ + 512) | runstore `_jsonl` framing; §5.1.2/§6.5 phase 3 (V15-02) |
| `CHUNK_BYTES` | 65,536 B | §6.4 |
| `HTTP_HEADROOM` / `SEAL_SLICE_BYTES` | 262,144 B / 49,152 B (3-aligned) | §6.5 phase 1 / §5.1.1 (V14-03); native-headroom substantiation Appendix A.5 (V16-04) |
| `TRANSIENT_BUDGET_BYTES` | 12,582,912 B (12 MiB) | §6.1/§6.5 measured proofs (V13-04; re-derived V14-03, D19; OFFICIAL V15-07, D30; reproducible via Appendix A protocol, V16-04/D34) |
| `HARNESS_FIXED_BUDGET_BYTES` / `RUN_RECORD_LIMIT` | 2,097,152 B / 2,000 | §6.6 |
| `MAX_DECOMPRESSED_BYTES` / `MAX_EXPANSION_RATIO` | 52,428,800 B / 1000:1 | §6.7 |
| `DELTA` / `W_MAX_NS` / `RETENTION_NS` / `FALLBACK_NS` | 1/10000 (100 ppm); 250 ms; 600 s; 60 s | params.py, protocol §5.2/5.3 |
| `GROUP_WINDOWS_MS` | g0 (0,2500), g1 (2000,2500), g2 (10000,2500), g3 (60000,5000), ref (180000,5000) | audit.py, V1 window |
| `MIN_SYNC_CALLS` / `RESYNC_COUNTS` / group & role orders | 10; 3–7; (resync,g0,g1,g2,g3,ref); 5m = (S1,K5m,S2), 4tf = (S1,K4h,K1h,K15m,K5m,S2) | audit.py |
| `RENAME_NOREPLACE` | 1 (`<linux/fs.h>`; no `os.RENAME_NOREPLACE` on Python 3.12) | §5.2 (V13-02) |
| `PUBLISH_LOCK_TIMEOUT_NS` / `INTERRUPT_POLL_NS` / `CHECKPOINT_DEFER_MAX_MS` | 30 s / 100 ms / 250 ms | §5.2.1, §7.1, §7.4 |
| Host / paths / params | `data-api.binance.vision`; `/api/v3/time`, `/api/v3/klines` exactly; `symbol,interval,startTime,endTime,limit`; GET only | params.py, protocol §2 |

**Runner additions (normative here; Step-2 code).** `TRANSIENT_BUDGET_BYTES`, `MAX_LINE`, `SEAL_SLICE_BYTES`,
`HTTP_HEADROOM`, `CHUNK_BYTES` and the §5.1.1/§5.1.2 contracts are normative in this document; `params.py` remains
the source of truth for the OBS parameters above. Any new runner constant joins this table in the next reviewed
revision — the budget may change only with a re-derived §6.5 under the Appendix A protocol (D13/D19/D30/D34).

## 13. Appendix A — Memory-accounting probe methodology, raw measurements and native headroom (V16-04; informative)

This appendix is the reproducibility record for every §6.5 number: how it was measured, on what, with what raw values —
the evidence V16-04 found missing from the document itself. All values below were re-measured for this revision (v1.7)
on the verification environment. The probe scripts are review artifacts, not repository files (§0 anchor).

### A.1 Environment and measurement protocol

* **Interpreter:** CPython 3.12.3 — the target interpreter of `tools/obs/` (OpenSSL 3.0.13), Linux x86-64, glibc with
  `mallinfo2`; stdlib only (`json`, `base64`, `hashlib`, `tracemalloc`, `ssl`, `socket`, `ctypes`). No JIT, no
  third-party packages.
* **Measurement method:** `tracemalloc.start()` → execute the EXACT normative sequence (the pseudocode of §5.1.1 /
  §5.1.2 / §6.4–§6.5 transcribed line-for-line, same order, same `del` points) → `tracemalloc.get_traced_memory()` →
  record the PEAK → `stop()`. `tracemalloc` traces Python-object allocations only; native buffers (SSL, socket,
  glibc arenas) are accounted separately in A.5.
* **Inputs:** worst-case BY CONSTRUCTION, fully deterministic — no randomness, no seeds: every probe builds its input
  inline from the §12 constants (`MAX_BODY_BYTES = 4,194,304`, `MAX_LINE = 5,592,920`,
  `SESSION_BODY_BUDGET_BYTES = 52,428,800`, …) using Step-1's own `_canonical` (sort_keys, separators `(",",":")`),
  so byte lengths are exact (the worst-case record line INCLUDING its JSONL terminator measures 5,592,919 B ≤ `MAX_LINE = 5,592,920` — probe7's exact input).
* **Pass criterion:** each phase peak ≤ its §6.5 bound (8,781,824 / 151,552 / 11,202,224 B), the three sequential
  phases never summed, max ≤ `TRANSIENT_BUDGET_BYTES = 12,582,912`. A probe whose measured value EXCEEDS its bound
  documents a BANNED pattern (A.4), enforced by mutation tests in the §11 gates.

### A.2 Probe inventory (v1.7)

| Probe | What it measures | Normative target |
|---|---|---|
| probe1 | phase-1 request conversion (worst-case record incl. base64 of a 4 MiB body) | §6.5 phase 1 |
| probe2 | phase-2 seal fragments (meta-fragment, digest-line, `b64encode`-slice; superseded for full-line values by probe3/4) | §6.5 phase 2 |
| probe3 | phase-3 decode pass, normative `del` release order, `MAX_LINE` line | §5.1.2 `decode_pass` |
| probe4 | phase-3 decode pass, fresh-buffer variant (same release order) | §5.1.2 `decode_pass` |
| probe5 | byte-equality: §5.1.1 writer vs `_lines([record_to_json…])` (1,020 records, 5,894,085 B) | G-V14-02 |
| probe6 | native headroom over a real local-TLS HTTP request (`mallinfo2` + `tracemalloc`) | `HTTP_HEADROOM`, A.5 |
| probe7 | phase-3 STRUCTURE pass peak (parse + key-set check + discard; no body decode) | §5.1.2 `scan_structure` |

### A.3 Raw measurements (CPython 3.12.3, this revision)

| Case | Bound (B) | Measured peak (B) | Verdict |
|---|---|---|---|
| phase 1 — request conversion, Python-level (probe1) | 8,781,824 | 8,462,496 | PASS (slack 319,328) |
| phase 1 — + named `HTTP_HEADROOM` (262,144; §6.5 arithmetic) | 8,781,824 | 8,724,640 | PASS (slack 57,184) |
| phase 1 — + RAW native arena peak (probe6, A.5) | 8,781,824 | 8,739,616 | PASS (slack 42,208) |
| phase 2 — streaming seal, normative `del` order (probe3 path) | 151,552 | 148,113 | PASS (slack 3,439) |
| phase 3 — decode pass, `MAX_LINE` line (probe3) | 11,202,224 | 11,188,261 | PASS |
| phase 3 — decode pass, fresh-buffer variant (probe4) | 11,202,224 | 11,188,197 | PASS |
| phase 3 — structure pass, `MAX_LINE` line (probe7) | 11,202,224 | 11,188,197 | PASS |
| phase 3 — §6.5 adjusted value (11,188,261 + 8,192 file buffer, §6.5 phase 3) | 11,202,224 | 11,196,453 | PASS |
| phase 2 — WITHOUT the normative `del` (anti-pattern) | 151,552 | 5,656,645 | BANNED |
| phase 2 — meta fragment / digest line / b64encode slice | 151,552 | 2,099 / 1,410 / 147,524 | PASS |
| banned — `base64.b64decode(str)` (stdlib re-encodes the whole string) | 11,202,224 | 15,381,335 | BANNED |
| banned — `json.loads(bytes)` with the buffer held | 11,202,224 | 16,781,149 | BANNED |
| banned — Step-1's whole-file `_read` + `_jsonl` (50 MiB session) | 12,582,912 | ≥ 139,810,133 | BANNED |

Reconciliation: budget = max(8,781,824; 151,552; 11,202,224) = 11,202,224 ≤ 12,582,912 B (margin 1,380,688 B,
12.3 %); worst measured phase-3 peak 11,196,453 B ≤ bound. The structure pass (probe7) peaks below the decode pass
because it releases the line and the dict in the same order without the base64 dance — it cannot exceed the decode
bound that already includes both.

### A.4 Banned patterns (normative summary; each is a plausible shortcut a mutation test kills)

1. `base64.b64decode(str)` — the stdlib re-encodes the full string to bytes first (+4.2 MB over the phase-3 bound).
2. Holding `line bytes + decoded text + parsed dict` simultaneously (e.g. `json.loads(raw_bytes)` with the buffer
   referenced) — 16,781,149 B.
3. Any whole-file read of records/events (`path.read_bytes()`, `raw.split(b"\n")`) — Step-1's ≥ 139.8 MB failure.
4. Retaining parsed lines/records across a pass (suspended generators, an output list in the structure pass).
5. Materializing a whole record line at seal (`record_to_json` / `r.body` / the `body_b64` string).

### A.5 Native headroom — the `HTTP_HEADROOM = 262,144 B` term (probe6)

`tracemalloc` sees only Python objects; SSL buffers, socket staging and glibc arena metadata are native. Probe6
measures that native term directly against a real local-TLS request (ephemeral `http.server` + `ssl` loopback socket,
first-ever cold request, sampled twice):

* **native arena peak** — glibc `mallinfo2().uordblks` after minus before the request: **277,120 B** (identical in
  both runs);
* **Python peak** for the same request: **8,398,928 B** / **8,399,008 B** (two runs);
* **RSS was rejected as the method:** page-level RSS masks the footprint (shared arenas, allocator reuse) and
  understates it; `mallinfo2` reports the arena's own in-use bytes directly.

Substantiation of the §6.5 phase-1 bound under BOTH headroom terms: named term → 8,462,496 + 262,144 = **8,724,640 ≤
8,781,824** (slack 57,184); raw measured native → 8,462,496 + 277,120 = **8,739,616 ≤ 8,781,824** (slack 42,208).
The bound therefore holds even when the named 262,144 B constant is replaced by the FULL raw native measurement —
the ceiling does not depend on rounding the headroom term down. (A real combined measurement of the request itself:
8,399,008 + 277,120 = 8,676,048 B, slack 105,776 B.)

### A.6 Budget reconciliation (normative §6.5 restated with the measured evidence)

The three phases run sequentially (single-flight; seal after all requests; verify after seal), so the budget is the
max phase peak, never the sum: max ≤ 11,202,224 B ≤ `TRANSIENT_BUDGET_BYTES = 12,582,912 B`. Domain A is released
before verify starts (single-copy rule, §5.4/§6.5), so phase-1 objects cannot coexist with phase-3 peaks. Any future
change to `MAX_BODY_BYTES`, the writer or the reader re-runs this whole protocol (D34) before the budget may change.

End of v1.7. Step-2 implementation SHALL implement §3–§10 literally; any deviation requires a new reviewed revision of this
document, not an implementation choice.