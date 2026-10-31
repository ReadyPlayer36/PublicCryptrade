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

---

### Part 2: Sections 3 to 6

```markdown
## 3. Adversarial Edge Cases & Safety Guards

### 3.1 DNS Isolation Boundary [NEW]
- Uses a killable `_resolve.py` subprocess with `RESOLVE_TIMEOUT_S=5.0` during pre-flight resolution. Unkillable hangups map to unsealed T0 outcomes (`cause: PUBLISH-UNSUPPORTED` or DNS failure).

### 3.2 Byte-Exact Streaming Memory Budgets (`INCIDENT-MEMORY`) [NEW]
- **Streaming Enforcement:** Chunk-level `retained + len(chunk) > SESSION_BODY_BUDGET_BYTES` (50 MiB session total, 4 MiB per-response cap) enforced inside the streaming read loop. Domain B transient buffer raised to 6 MiB.

### 3.3 Protocol v0.5 Alignment [NEW]
- Maps harness outcomes to record shapes and protocol incident tables without breaking frozen schemas.

---

## 4. Signal State Machine & Incident Matrices

### 4.1 Signal State Machine & Commit Checkpoints (CP1–CP3) [NEW]
- **States:** `PRE-FLIGHT` → `RUNNING` → `STOPPING` → `SEALING` → `VERIFYING` → `COMMITTING` → `COMMITTED` (or `EMERGENCY`).
- **Checkpoints:** CP1 (after rename), CP2 (after parent fsync), CP3 (after index fsync) with a single deferred-signal consumer.

### 4.2 Complete Incident & Crash Persistence Matrices [EXISTS]
- Fully enumerated **N1–N14**, **T1–T9**, **P1–P8**, **E1–E12**, and **K0–K12** staging crash tables.

---

## 5. Provenance & Terminal Success Invariants

### 5.1 Outer Evidence Index (`obs-outer-index/1`) [EXISTS]
- Frozen `obs-run-manifest/1` schema remains untouched at 8 keys; session provenance resides in sibling `obs-outer-index/1`.

### 5.2 Refusal Journal (`obs-refusal/1`) & Terminal States (T0–T6) [NEW]
- **T0 vs T2:** Decided by a durable, fsynced refusal journal (`obs-refusal/1`). Torn journals ⇒ T2.
- **T4 Strictness:** Strictly represents verified runs lacking a receipt. Tampered runs map to T3.

### 5.3 Strict Success Predicate ($S$) & Invariant M [NEW]
- $S \iff \text{COMMITTED} \land \text{RECEIPT} \land \text{VERIFIED} \land \text{AUDITED} \land \text{EGRESS\_CLEAN} \land \text{PLAN\_TERMINAL}$.

---

## 6. Gates & Reviewer Decisions

### 6.1 Validation Gates (G-R1 through G-R12) [NEW]
- Automated assertion checks covering all adversarial remediation rounds.

### 6.2 Reviewer Decisions (D1 through D10) [NEW]
- Formal architectural decisions regarding memory budgets, host policies, and execution boundaries.