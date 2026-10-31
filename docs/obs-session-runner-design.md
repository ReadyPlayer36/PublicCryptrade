# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v1.3

## 0. Revision Map (R1–R12 & V12-01–V12-08)
- **R1 / V12-01 (DNS Termination & Incident Ladder):** Resolved in §1.2 & §3.1 (Killable subprocess resolver, corrected incident ladder evaluation order matching `audit.abort_condition_seq`).
- **R2 / V12-08 (Start Semantics & Wire Timestamp):** Resolved in §1.1 & §1.3 (Logical dispatch `start_ns`, `pre_write_ns` worker handoff).
- **R3 / V12-05 (Normative Execute Loop & Window End):** Resolved in §1.2 (Single-read commit, fixed-point timing, `start_at > window_end_ns` check).
- **R4 (Rolling Release):** Resolved in §1.4 (Full `max()`-combined 1s/60s rolling release algorithm with GV-8 vectors).
- **R5 / R6 / V12-04 (Memory Budgets & Accounting):** Resolved in §3.2 (Chunk-level streaming enforcement, single `retained_total` owner, disjoint domains A/B/C).
- **R7 / V12-02 / V12-03 (No-Replace Publication):** Resolved in §2.1 & §2.2 (`renameat2(RENAME_NOREPLACE)` anchored to parent fd, `stat.S_ISDIR` checks, no fallback).
- **R8 / V12-06 (Receipt & Terminal Partition):** Resolved in §5.3 (Durable `obs-refusal/1` journal for T0/T2 distinction, strict T4 re-verification rules).
- **R9 (Quarantine):** Resolved in §2.3 (Atomic staging quarantine via `publish_dir()`).
- **R10 / V12-07 (Emergency Commit & Signals):** Resolved in §4.1 (Commit checkpoints CP1–CP3 and single deferred-signal consumer).
- **R11 (Complete Matrices):** Resolved in §4.2 & §4.3 (Fully enumerated N, T, P, E, and K rows).
- **R12 (Exhaustive Terminal Invariant):** Resolved in §5.3 (Exhaustive T0–T6 state resolver and invariant M).

---

## 1. Concurrency Model & Pacing Mechanics

### 1.1 Thread Inventory [EXISTS / RECONCILED]
- **Main Pacing / Orchestration Thread:** Owns monotonic clock reads, pacing calculations, watchdog absolute deadline monitoring, socket shutdown triggers, event log mutations, and finalization.
- **Request Worker Thread (`obs-request`, daemon=True):** At most one worker exists at any time. Performs socket I/O exclusively. Zero clock reads for decisions; single observational `pre_write_ns` read feeding diagnostics only.

### 1.2 Normative `execute()` Loop & Incident Ladder [NEW]
- **Single-Read Commit:** Admission decided using a single monotonic timestamp read: `now >= max(earliest_start_ns(), ceil(D(now)))`. That exact timestamp read is recorded as `start_ns`.
- **Incident Ladder Evaluation Order (V12-01):** Evaluated strictly matching `audit.abort_condition_seq`:
  1. `error == CANCEL_FAILED`
  2. `status is not None and status != 200`
  3. `status is None` (with single streak increment) and memory aborts.
  4. `status == 200` (resets streak).

### 1.3 Authoritative `start_ns` Invariants & Handoff (S1–S6) [NEW]
- **S1–S6:** `start_ns` is the authoritative logical dispatch timestamp sampled on the pacing thread. `pre_write_ns` records worker handoff timing before the first `sendall()` call.

### 1.4 Combined Rolling Release Calculation [NEW]
- Enforces 2 req/s and 60 req/min rolling caps using exact integer-nanosecond arithmetic (`max()` combination of 1s and 60s windows) with all four **GV-8** boundary validation gates.

---

## 2. Persistence, Sealing & Self-Verification

### 2.1 Durable Staging & Directory-FD Publication [NEW]
- **No-Replace Publication (§2.2):** Uses normative `renameat_no_replace()` anchored to the locked parent directory file descriptor (`pfd`) via `renameat2(RENAME_NOREPLACE)`.
- **Identity & Stat Checks:** Uses `stat.S_ISDIR(st.st_mode)` and `(st_dev, st_ino)` identity verification. Insecure plain `os.rename` fallbacks are removed.

### 2.2 Write-Read-Audit Self-Verification [NEW]
- Runner calls `load_run(staging, pin)` and executes `audit_run(...)` against reloaded persisted artifacts before atomic publication.
## 3. Adversarial Edge Cases & Safety Guards

### 3.1 DNS Isolation Boundary [NEW]
- **Subprocess Isolation:** Resolves hostnames in an isolated, killable `_resolve.py` subprocess using `RESOLVE_TIMEOUT_S = 5.0`. If resolution hangs or exceeds the deadline, the main process terminates the resolver worker via `kill()` and `wait(2.0)`.
- **Pre-Flight Enforcement:** All DNS resolution occurs strictly during pre-flight. The runtime session path connects exclusively via pinned IP addresses, ensuring zero blocking DNS lookups during pacing.
- **Failure Classification:** Unresolvable or unkillable DNS hangups are classified as unsealed, untrusted execution failures (Terminal State T0) with structured cause codes.

### 3.2 Byte-Exact Streaming Memory Budgets (`INCIDENT-MEMORY`) [NEW]
- **Streaming Enforcement:** The chunk-level streaming read loop enforces the session aggregate budget dynamically:
  $$\text{retained\_total} + \text{len(chunk)} > \text{SESSION\_BODY\_BUDGET\_BYTES (50 MiB)}$$
  Pre-dispatch checks serve as advisory guards, while chunk-level streaming validation halts and aborts immediately before retaining excess bytes.
- **Per-Response Cap:** 4 MiB maximum response body enforced via header pre-checks and streaming chunk limits.
- **Disjoint Memory Domains:**
  - **Domain A:** Retained response payloads (capped by 50 MiB session aggregate / 4 MiB per-response).
  - **Domain B:** Transient body buffers (`TRANSIENT_BUDGET_BYTES = 6 MiB`) accommodating in-flight decompression and hashing buffers.
  - **Domain C:** Fixed harness overhead.
- **Decompression Bounds:** Never-decompress policy in the hot execution path; offline verification enforces `MAX_DECOMPRESSED_BYTES` and a strict 1000:1 expansion ratio ceiling.

### 3.3 Protocol v0.5 Alignment [NEW]
- **Record Shape Preservation:** Record structures and JSONL schemas remain frozen under `obs-run-manifest/1`. New detail values for transport and memory incidents live inside the free-form `error` field.
- **No-Response Family Rule:** `status is None` uniformly triggers the no-response sequence and incident counter regardless of transport detail sub-codes.
- **Incident Mapping:** `INCIDENT-MEMORY` maps cleanly to the protocol's formal `ABORT (INCIDENT)` table classification.

---

## 4. Signal State Machine & Incident Matrices

### 4.1 Signal State Machine & Commit Checkpoints (CP1–CP3) [NEW]
- **Lifecycle States:** `PRE-FLIGHT` → `RUNNING` → `STOPPING` → `SEALING` → `VERIFYING` → `COMMITTING` → `COMMITTED` (or `EMERGENCY`).
- **Deferred Interrupt Handling:** First `SIGINT` or `SIGTERM` sets an interrupt flag checked at ≤100 ms intervals inside pacing sleep loops, ensuring no request starts mid-interrupt and triggering a graceful sealed abort.
- **Commit Checkpoints (CP1–CP3):**
  - **CP1:** Immediately after atomic staging rename.
  - **CP2:** Immediately after parent directory `fsync()`.
  - **CP3:** Immediately after outer index receipt publication.
- **Second Signal Behavior:** Triggers immediate emergency exit (`os._exit`), with millisecond-bounded deferral permitted only within atomic synchronization checkpoints to guarantee journal consistency.

### 4.2 Complete Incident Matrices (N1–N14, T1–T9, P1–P8, E1–E12) [EXISTS]
- Fully enumerated persistence and error matrices mapping every condition to its detection rule, countermeasure, outcome code, and evidence treatment:
  - **N1–N14 (Network & Transport):** Covers 12.0 s read timeouts, connection drops, chunk limits, and inline PACE-8 verification.
  - **T1–T9 (Timing & Clock):** Monotonic regression checks, wall-clock jumps, and NTP slew handling.
  - **P1–P8 (Pacing & Admission):** Rolling cap enforcement and target re-evaluation boundaries.
  - **E1–E12 (Execution & Environment):** Signal handling, memory budgets, and file locks.

### 4.3 Staging Crash Persistence Matrix (K0–K12) [EXISTS]
- 13 deterministic persistence failure scenarios (including file write failures, file `fsync()` errors, staging rename interruptions, and parent-directory `fsync()` faults) proving fail-closed atomicity across all staging operations.
## 5. Provenance, Receipt & Terminal Success Invariants

### 5.1 Outer Evidence Index (`obs-outer-index/1`) [EXISTS]
- **Frozen Manifest:** The core run artifact schema (`obs-run-manifest/1`) remains strictly frozen at its exact 8-key set.
- **Provenance Sibling:** All runner execution metadata, Python runtimes, OS platform details, commit SHAs, and working-tree clean status reside in an independent sibling index (`obs-outer-index/1`), bound to the run via the exact manifest SHA-256 pin.

### 5.2 Refusal Journal (`obs-refusal/1`) & Terminal-State Partition [NEW]
- **Durable Refusal Journal:** Pre-flight refusals write a structured, fsynced journal (`obs-refusal/1`). A torn or missing refusal journal during a pre-flight crash correctly resolves to Terminal State **T2 (INCONCLUSIVE-CRASH)** rather than false-positive pre-flight rejection (**T0**).
- **Strict Re-Verification (`observe()`):** `observe()` performs full re-verification of persisted artifacts *before* checking for the receipt. A tampered or corrupt run directory maps to **T3 (FAILED-AUDIT)**, ensuring state **T4 (SEALED-UNRECEIPTED)** is strictly reserved for valid, verified runs that lack a published receipt.

### 5.3 Strict Success Predicate ($S$) & Invariant M [NEW]
- **Invariant M:** Every run attempt terminates in exactly one deterministic state: successfully published and verified, quarantined (`*.unverified/`), or entirely absent (never partial).
- **Strict Success Predicate ($S$):**
  $$S \iff \text{COMMITTED} \land \text{RECEIPT} \land \text{VERIFIED} \land \text{AUDITED} \land \text{EGRESS\_CLEAN} \land \text{PLAN\_TERMINAL}$$
- **Terminal States (T0–T6):** Exhaustive partition mapping every possible runtime outcome to a single definitive state, governing exit codes ($0, 1, 2, 130, 143$) and refusal handling.

---

## 6. Gates & Reviewer Decisions

### 6.1 Validation Gates (G-R1 through G-R12) [NEW]
- Automated assertion and test gates mapped directly to each adversarial remediation requirement (AR-01 through AR-12 and V12-01 through V12-08).

### 6.2 Reviewer Decisions (D1 through D10) [NEW]
- Formal architectural decisions covering host binding policies, memory budget thresholds, isolation boundaries, and protocol v0.5 alignment.
