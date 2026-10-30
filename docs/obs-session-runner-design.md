# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v1.1

## 0. Revision Map (AR-01 through AR-12)
- **AR-01 (Thread Inventory):** Reconciled in §1.1 (Main pacing thread + at most one worker; watchdog thread eliminated).
- **AR-02 (Normative Execute Loop):** Reconciled in §1.2 (Single-read commit, fixed-point re-evaluation, GV-6/GV-7 tests).
- **AR-03 (Start Semantics):** Reconciled in §1.3 (Invariants S1–S6 for authoritative `start_ns`).
- **AR-04 (Rolling Release):** Reconciled in §1.4 (Integer-nanosecond open-left/closed-right evaluation, GV-8 gates).
- **AR-05 (Durable Publication):** Reconciled in §2.1 (Staging dir, file/dir fsync, atomic rename, parent fsync).
- **AR-06 (Self-Verification):** Reconciled in §2.2 (Reloaded persisted artifact audit, independent wrapper count).
- **AR-07 (DNS Termination):** Reconciled in §3.1 (Execution boundary lifecycle, replacing `sys.exit` with structured `RunOutcome`).
- **AR-08 (Memory Budgets):** Reconciled in §3.2 (Byte-exact streaming checks, pre-dispatch 50 MiB budget guard, `INCIDENT-MEMORY`).
- **AR-09 (Signal State Machine):** Reconciled in §4.1 (State machine: PRE-FLIGHT → COMMITTED, 100 ms sleep slices, deferred interrupts).
- **AR-10 (Incident/Crash Matrices):** Reconciled in §4.2 & §4.3 (Complete N1–N14, T1–T9, P1–P8, E1–E12 matrices and K0–K12 staging crash table).
- **AR-11 (Outer Evidence Index):** Reconciled in §5.1 (Frozen `obs-run-manifest/1` schema preserved; provenance moved to sibling `obs-outer-index/1`).
- **AR-12 (Terminal Success Invariant):** Reconciled in §5.2 (Invariant M and strict success predicate $S$).

---

## 1. Concurrency Model & Pacing Mechanics

### 1.1 Thread Inventory [EXISTS / RECONCILED]
The OBS session runner strictly enforces a **two-thread ceiling**:
1. **Main Pacing / Orchestration Thread:** Owns all monotonic clock reads, pacing calculations, watchdog absolute deadline monitoring, socket shutdown triggers, event log mutations, and finalization.
2. **Request Worker Thread (`obs-request`, daemon=True):** At most one worker exists at any time. It performs socket/network I/O exclusively and never reads clocks or makes pacing decisions.

*Note:* V1.0’s conceptual "watchdog thread" is eliminated. Watchdog absolute deadline monitoring and socket shutdown are handled inline by the main pacing thread during socket wait loops.

### 1.2 Normative `execute()` Loop & Fixed-Point Timing [NEW]
To eliminate drift-gap sites between target calculation and dispatch, the pacing loop executes a **single-read commit**:
- `target_fn(now)` is re-evaluated dynamically on every wake.
- Admission is decided using a single monotonic timestamp read: `now >= max(earliest_start_ns(), ceil(D(now)))`.
- The exact timestamp read that satisfies this condition **is** recorded as `start_ns`. No second timestamp read occurs between admission and dispatch.
- Normative acceptance criteria are governed by protocol golden vectors **GV-6** and **GV-7**, verifying exact first valid integer-nanosecond instants and fixed-point re-evaluation.

### 1.3 Authoritative `start_ns` Invariants (S1–S6) [NEW]
- **S1:** Single source of truth sampled on the pacing thread immediately upon admission.
- **S2:** Self-consistent at the recorded instant (`start_ns >= D(start_ns)`).
- **S3:** Sole deadline anchor for PACE-2 and PACE-3 evaluations.
- **S4:** Strictly distinct from `decided_at` and `end_ns`.
- **S5:** Never derived retrospectively.
- **S6:** Audit-equivalent to authoritative network handoff timing.

### 1.4 Rolling Release Calculation [NEW]
Rolling rate caps (2 req/s, 60 req/min) are enforced using exact integer-nanosecond arithmetic:
- `window_count = bisect_right(t) - bisect_right(t - W)`
- `release = starts[-cap] + W`
- All four **GV-8** boundary cases are enforced as mandatory validation gates tested across pacer functions, live loops, and independent re-derivation.

---

## 2. Persistence, Sealing & Self-Verification

### 2.1 Durable Staging-Directory Publication Recipe [NEW]
To ensure atomicity and fail-closed durability, evidence publication follows a strict staging pipeline:
1. Create a unique staging directory on the same filesystem as the final run directory.
2. Write records (`records.jsonl`) and events (`events.jsonl`) into staging; execute `fsync()` on each file.
3. Write `manifest.json` last; execute `fsync()` on the manifest file.
4. Execute `fsync()` on the staging directory.
5. Perform write-read-audit self-verification against the staging artifacts.
6. Execute atomic `os.rename()` of the staging directory to its final run directory name.
7. Execute `fsync()` on the parent directory.
8. Emit receipt (pin + outer index).

### 2.2 Write-Read-Audit Self-Verification [NEW]
Before publication, the runner calls `load_run(staging, pin)` and audits the reloaded persisted artifacts via `audit_run(...)`:
- Verifies pin authenticity against manifest bytes.
- Validates manifest self-digest and schema.
- Confirms JSONL file digests match manifest declarations.
- Enforces strict type, shape, sequence, and chain validation on reloaded records and events.
- Any verification failure aborts the run, placing artifacts into a quarantined `*.unverified/` directory.

---

## 3. Adversarial Edge Cases & Safety Guards

### 3.1 Execution Boundary & DNS Termination [NEW]
- `sys.exit()` is completely banned from background threads and low-level routines.
- A centralized `run_session()` execution boundary owns session lifecycle, mapping all outcomes to structured `RunOutcome` values with a guaranteed `finally` finalization block.
- DNS hangs and unresponsive sockets trigger inline deadline monitoring, socket shutdown, `CancellationFailed` handling, transport disable, and `INCIDENT-CANCEL` logging without orphan workers.

### 3.2 Byte-Exact Memory Budgets (`INCIDENT-MEMORY`) [NEW]
- **Per-Response Cap:** 4 MiB maximum response body. Enforced via header pre-checks and chunked streaming reads that abort immediately upon exceeding `MAX_BODY_BYTES`.
- **Session Aggregate Budget:** 50 MiB session total enforced via a pre-dispatch guard.
- Exceeding either cap triggers an immediate, sealed `INCIDENT-MEMORY` abort outcome.

---

## 4. Signal State Machine & Incident Matrices

### 4.1 Signal State Machine [NEW]
- **States:** `PRE-FLIGHT` → `RUNNING` → `STOPPING` → `SEALING` → `VERIFYING` → `COMMITTING` → `COMMITTED` (or `EMERGENCY`).
- **First SIGINT/SIGTERM:** Sets a deferred interrupt flag checked at ≤100 ms sleep intervals. Stops dispatching new requests, finalizes active work, and performs graceful sealed abort.
- **Second SIGINT:** Triggers immediate emergency exit (`os._exit`) leaving no manifest (fail-closed), with a millisecond deferral only if inside the `COMMITTING` atomic rename critical section.

### 4.2 Complete Incident & Crash Persistence Matrices [EXISTS]
- **N1–N14 (Network & Transport):** Complete coverage including 12.0 s read timeouts, connection drops, and inline PACE-8 enforcement.
- **T1–T9 (Timing & Clock):** Monotonic regression checks, wall-clock jumps, and NTP slew handling.
- **P1–P8 (Pacing & Admission):** Rolling cap enforcement and PACE-7 strict boundary checks.
- **E1–E12 (Execution & Environment):** Signal handling, memory budgets, and process locks.
- **K0–K12 (Staging Crash Table):** 13 deterministic persistence failure scenarios with fail-closed guarantees.

---

## 5. Provenance & Success Invariants

### 5.1 Outer Evidence Index (`obs-outer-index/1`) [EXISTS]
- The core run artifact schema (`obs-run-manifest/1`) remains strictly frozen at 8 keys.
- All session provenance, Python versions, OS data, and commit SHAs are recorded in a separate sibling outer index (`obs-outer-index/1`).

### 5.2 Terminal Success Invariant (Invariant M & Predicate $S$) [NEW]
- **Invariant M:** A run attempt must terminate as either successfully published and verified, quarantined (`*.unverified/`), or entirely absent—never partial.
- **Strict Success Predicate ($S$):** 
  $$S \iff \text{COMMITTED} \land \text{RECEIPT} \land \text{VERIFIED} \land \text{AUDITED} \land \text{EGRESS\_CLEAN} \land \text{PLAN\_TERMINAL}$$