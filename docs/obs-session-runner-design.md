# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v2.3

## 0. Revision Map (R1–R12, V12-01–V12-08, AR-01–AR-12 & V22-01–V22-03)
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
- **V22-01 — V22-03 (Verified Byte Execution & Self-Test Hardening):** Resolved in §1.5, §5.4, and Appendix A.0 (In-memory `compile()` & `exec()` of descriptor-verified bytes, active TOCTOU fault injection, and honest test-case accounting).

---

## 1. Concurrency Model & Pacing Mechanics

### 1.1 Thread Inventory [EXISTS / RECONCILED]
The OBS session runner strictly enforces a **two-thread ceiling**:
1. **Main Pacing / Orchestration Thread:** Owns all monotonic clock reads, pacing calculations, watchdog absolute deadline monitoring, socket shutdown triggers, event log mutations, and finalization.
2. **Request Worker Thread (`obs-request`, daemon=True):** At most one worker exists at any time. It performs socket/network I/O exclusively and never reads clocks or makes pacing decisions. Zero clock reads for decisions; single observational `pre_write_ns` read feeding diagnostics only.

### 1.2 Normative `execute()` Loop & Fixed-Point Timing [NEW]
To eliminate drift-gap sites between target calculation and dispatch, the pacing loop executes a **single-read commit**:
- `target_fn(now)` is re-evaluated dynamically on every wake.
- Admission is decided using a single monotonic timestamp read: `now >= max(earliest_start_ns(), ceil(D(now)))`.
- The exact timestamp read that satisfies this condition **is** recorded as `start_ns`. No second timestamp read occurs between admission and dispatch.
- Normative acceptance criteria are governed by protocol golden vectors **GV-6** and **GV-7**, verifying exact first valid integer-nanosecond instants and fixed-point re-evaluation.
- **Incident Ladder Evaluation Order (V12-01):** Evaluated strictly matching `audit.abort_condition_seq`:
  1. `error == CANCEL_FAILED`
  2. `status is not None and status != 200`
  3. `status is None` (with single streak increment) and memory aborts.
  4. `status == 200` (resets streak).

### 1.3 Authoritative `start_ns` Invariants (S1–S6) [NEW]
- **S1:** Single source of truth sampled on the pacing thread immediately upon admission.
- **S2:** Self-consistent at the recorded instant (`start_ns >= D(start_ns)`).
- **S3:** Sole deadline anchor for PACE-2 and PACE-3 evaluations.
- **S4:** Strictly distinct from `decided_at` and `end_ns`.
- **S5:** Never derived retrospectively.
- **S6:** Audit-equivalent to authoritative network handoff timing. `pre_write_ns` records worker handoff timing before the first `sendall()` call.

### 1.4 Rolling Release Calculation [NEW]
Rolling rate caps (2 req/s, 60 req/min) are enforced using exact integer-nanosecond arithmetic (`max()` combination of 1s and 60s windows):
- `window_count = bisect_right(t) - bisect_right(t - W)`
- `release = starts[-cap] + W`
- All four **GV-8** boundary cases are enforced as mandatory validation gates tested across pacer functions, live loops, and independent re-derivation.

### 1.5 Verified Byte Execution Binding (V22-01) [NEW]
- After `check_manifest()` cryptographically verifies source bytes via hardened descriptors (`O_NOFOLLOW`, `lstat`, `samestat`), the driver compiles those exact verified bytes into memory (`compile()`) and executes them into isolated module objects (`exec()`), preventing unpinned `.pyc` caching or post-validation file substitution.

---

## 2. Persistence, Sealing & Self-Verification

### 2.1 Durable Staging-Directory Publication Recipe [NEW]
To ensure atomicity and fail-closed durability, evidence publication follows a strict staging pipeline:
1. Create a unique staging directory on the same filesystem as the final run directory.
2. Write records (`records.jsonl`) and events (`events.jsonl`) into staging; execute `fsync()` on each file.
3. Write `manifest.json` last; execute `fsync()` on the manifest file.
4. Execute `fsync()` on the staging directory.
5. Perform write-read-audit self-verification against the staging artifacts.
6. **No-Replace Publication (§2.2):** Uses normative `renameat_no_replace()` anchored to the locked parent directory file descriptor (`pfd`) via `renameat2(RENAME_NOREPLACE)`.
7. **Identity & Stat Checks:** Uses `stat.S_ISDIR(st.st_mode)` and `(st_dev, st_ino)` identity verification. Insecure plain `os.rename` fallbacks are removed.
8. Execute `fsync()` on the parent directory.
9. Emit receipt (pin + outer index).

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

## 5. Provenance, Success Invariants & Verification Gates (v2.3)

### 5.1 Outer Evidence Index (`obs-outer-index/1`) [EXISTS]
- The core run artifact schema (`obs-run-manifest/1`) remains strictly frozen at 8 keys.
- All session provenance, Python versions, OS data, and commit SHAs are recorded in a separate sibling outer index (`obs-outer-index/1`).

### 5.2 Terminal Success Invariant (Invariant M & Predicate $S$) [NEW]
- **Invariant M:** A run attempt must terminate as either successfully published and verified, quarantined (`*.unverified/`), or entirely absent—never partial.
- **Strict Success Predicate ($S$):** 
  $$S \iff \text{COMMITTED} \land \text{RECEIPT} \land \text{VERIFIED} \land \text{AUDITED} \land \text{EGRESS\_CLEAN} \land \text{PLAN\_TERMINAL}$$

### 5.3 Durable Refusal Journal (`obs-refusal/1`) [NEW]
- Records T0/T2 distinction and enforces strict T4 re-verification rules.

### 5.4 Verification Gates & Acceptance Criteria (G-V22) [NEW]

| Gate ID | Requirement | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **G-V22-01** | Verified bytecode execution binding (no unpinned cache/import race) | In-memory `compile()` & `exec()` of validated descriptor bytes | **PASSED** |
| **G-V22-02** | Active TOCTOU fault injection & self-test integrity harness | Automated `--self-test` (18 adversarial cases) | **PASSED** |
| **G-V22-03** | Honest test-case accounting (passed/failed/skipped tracking) | CLI structured reporting | **PASSED** |

---

## Appendix A.0 — Complete Suite Manifest (v2.3)
* **Schema:** `obs-probes/2`
* **Pinned Files:** 13 files pinned by `expected.json`, with `expected.json` independently pinned below. Total inventoried files: 14.

| Path | Bytes | SHA-256 Digest |
| :--- | :--- | :--- |
| `tools/obs/probes/README.md` | 13,175 | `bd6edc09db03adc6ae03184dfe40f4b5b644f4f57671e89e48e8c99c68925ddd` |
| `tools/obs/probes/__init__.py` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tools/obs/probes/alloc_peak.c` | 19,327 | `19064773bb13436d9386ac896fa9ab3021f01afe0e5bf05a03b1bfdca210efa3` |
| `tools/obs/probes/probe1_phase1.py` | 1,358 | `1f63e461fb71836d78c718d0f0ac98c64c46f4c64e99852c0afaf9e83fab38d2` |
| `tools/obs/probes/probe2_seal.py` | 2,326 | `455ef7b384c0057ea50a1e6ed711538bfa5ca6e904e22590a576be4bf4c7a20f` |
| `tools/obs/probes/probe3_decode.py` | 1,699 | `4320fbe9044b7bd4d9b70238d8d5731832e6348d28a710fe8f92368f1ae66066` |
| `tools/obs/probes/probe4_decode_fresh.py` | 815 | `e72afb89e85274c90db48ec32d03435b32dae6ffa1577adc0f83d0b68e4129eb` |
| `tools/obs/probes/probe5_byte_equality.py` | 2,647 | `61278c289c1ab2cb10ed7305e3e572e63debed8f1a9b6997a2a440b5c0572a47` |
| `tools/obs/probes/probe6_native.py` | 21,295 | `0c052217fccbdc86a602692c0bbc42f09e8db17a1060b72738e10bcce1ccb752` |
| `tools/obs/probes/probe7_structure.py` | 780 | `d1e1e15712c3cdbe0693b278e421da048680ba33e7dc264b8c746029341a58e4` |
| `tools/obs/probes/probe8_mmap_threads.py` | 17,934 | `ffb160e5b6559e5cc6e644b7383f75df6dd5f85bc4786e3fea58fa0a58b13081` |
| `tools/obs/probes/probe_common.py` | 4,044 | `c1662be01889bddbdba6426e566cd3da9b2bb7e50a955000c35670b9f7e5cca4` |
| `tools/obs/probes/run_all.py` | 52,242 | `6739c8339d51de771187b523d6f387414e5d3be6fc7956a7f74b71005cbad2cd` |
| `tools/obs/probes/expected.json` | 6,548 | `e510183d872fdbf47c916e545b405ef1cea1ef05feb8ca7076f98708ccf7fd3c` |

---
*End of Architectural Blueprint v2.3.*
