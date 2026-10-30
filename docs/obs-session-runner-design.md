# OBS-01 / OBS-02 Session Runner & Evidence Writer Blueprint

- **Document Version:** v1.0
- **Target Branch:** `impl-obs-harness`
- **Protocol Spec:** `docs/obs-protocol.md` v0.5 (Commit `7ef4986`)
- **Status:** Architectural Design Blueprint (Pre-Implementation)
- **Scope:** Execution runner (`--live`), single-pacer concurrency, evidence writer, manifest sealing, and fail-closed error handling.

---

## 1. Concurrency Guardrails & Thread Inventory

### 1.1 Strict Thread Inventory
To eliminate scheduling jitter, thread races, and silent pacer bypasses, the runner enforces a hard **Two-Thread Inventory** at the process level:

1. **Pacing / Orchestration Thread (Main Thread):**
   - Executes all wall-clock and monotonic clock reads (`time.monotonic_ns()`).
   - Evaluates the estimator offset bounds ($\theta_{\text{lo}}, \theta_{\text{hi}}$) and fixed-point deadlines ($D(X)$).
   - Manages all inline re-reading sleep loops and watchdog scheduling.
   - Appends events to the `EventLog` and executes the `execute()` loop.
2. **Request Worker Thread (At Most One Active):**
   - Created exclusively for transport socket operations via `http.client`.
   - Has zero access to time reads or pacing decisions.
   - Exists strictly because a socket blocked on `recv()` cannot be interrupted in-thread without socket shutdown.

> **Enforcement Rule:** The codebase explicitly bans `threading.Timer`, `asyncio`, background scheduler threads, or `Event.wait(timeout)` used as a pacer. This is enforced via structural unit tests.

### 1.2 Normative Pacing Execution Loop
The pacer execution loop maintains *never-early* and *never-catch-up* invariants by construction:

```python
def execute_paced_request(target_fn, clock_fn, min_gap_ns=600_000_000):
    """
    Evaluates target_fn() on each wake cycle to account for moving fixed points.
    Guarantees no early execution and no phase accumulation.
    """
    while True:
        now_ns = clock_fn()
        earliest_ns = max(last_completion_ns, last_start_ns + min_gap_ns, rolling_release_ns(now_ns))
        target_ns = target_fn(now_ns)
        start_at_ns = max(earliest_ns, target_ns)

        if now_ns >= start_at_ns:
            # Sample start_ns on the pacing thread immediately before worker execution
            sampled_start_ns = clock_fn()
            return dispatch_worker(sampled_start_ns)
        
        # Micro-sleep / spin yield loop re-evaluated against clock
        precise_sleep_until(start_at_ns)
```

### 1.3 PACE-1 through PACE-8 Enforcement Matrix

| Rule | Description | Live Mechanism | Audit Verification |
| :--- | :--- | :--- | :--- |
| **PACE-1** | Single-flight execution | Thread lock + single request worker | `check_non_overlapping()` |
| **PACE-2** | Sequential request ordering | Completion timestamp check before next start | `check_completion_order()` |
| **PACE-3** | Open-left, closed-right rolling caps | `bisect_right()` on window intervals $(t-W, t]$ | `check_rolling_caps()` |
| **PACE-4** | Minimum 0.6s start gap | `start_ns >= prev_start_ns + 600ms` | `check_start_spacing()` |
| **PACE-5** | Exact-integer monotonic audit | Recorded nanosecond arrays | Full `audit_pace()` verification |
| **PACE-6** | Shifted multi-timeframe group starts | Slot offsets +3.6s for 4-timeframe groups | `check_group_ordering()` |
| **PACE-7** | Strict boundary admission | `m_e = max(decided_at, earliest)` $\rightarrow$ immediate skip or fixed point | `validate_missed_window_decision()` |
| **PACE-8** | Hard 17.0s request watchdog | `socket.shutdown(SHUT_RDWR)` at `start_ns + 17s` | `check_request_durations()` |

---

## 2. Manifest Sealing & Persistence Architecture

### 2.1 Atomic Evidence Writing Recipe
To prevent partially written or corrupted run directories from being mistaken for valid evidence, data is buffered in memory during the execution and written atomically at session end:

1. **In-Memory Buffering:**
   - All `RequestRecord` items and `LogEvent` items are accumulated in memory during the run.
   - An untrusted `.partial/spool.jsonl` file is maintained purely for crash forensics.
2. **Atomic Three-File Persistence Sequence:**
   - Step A: Write `records.jsonl` $\rightarrow$ `fsync()` file $\rightarrow$ `fsync()` directory.
   - Step B: Write `events.jsonl` $\rightarrow$ `fsync()` file $\rightarrow$ `fsync()` directory.
   - Step C: Compute record/event digests and write `manifest.json` **last** $\rightarrow$ `fsync()` file $\rightarrow$ `fsync()` directory.
3. **Emit SHA-256 Pin:**
   - Output the SHA-256 digest of `manifest.json` as the immutable run pin.

```
[In-Memory Buffer] ──► Write records.jsonl ──► Write events.jsonl ──► Write manifest.json (COMMIT POINT)
                            │                       │                       │
                            ▼                       ▼                       ▼
                         fsync()                 fsync()                 fsync()
```

### 2.2 Write-Read-Audit Self-Verification Loop
Before reporting successful completion to the CLI or caller, the runner immediately self-audits the persisted artifact:

```python
def finalize_and_verify_run(run_dir, records, event_log, profile):
    # 1. Atomic Write
    pinned_manifest_sha256 = runstore.write_run(run_dir, records, event_log)
    
    # 2. Reload from Disk
    loaded_manifest, loaded_records, loaded_events = runstore.load_run(
        run_dir, pinned_manifest_sha256=pinned_manifest_sha256
    )
    
    # 3. Independent Audit Execution
    audit_result = audit.audit_run(
        run_dir=run_dir,
        pinned_manifest_sha256=pinned_manifest_sha256,
        wrapper_count=len(records),
        profile=profile
    )
    
    if not audit_result.passed:
        raise EventLogError(f"Self-audit failed post-persistence: {audit_result.reasons}")
    
    return pinned_manifest_sha256
```

### 2.3 Fail-Closed Crash Matrix

| Crash Point | State on Disk | Recovery / Audit Result |
| :--- | :--- | :--- |
| **Crash before Step A** | No files or `.partial/spool` only | **FAIL-CLOSED:** No manifest exists. Loader rejects directory. |
| **Crash during Step A** | Incomplete `records.jsonl` | **FAIL-CLOSED:** No manifest exists. Directory untrusted. |
| **Crash between A and B** | Complete `records.jsonl`, no `events.jsonl` | **FAIL-CLOSED:** No manifest exists. Directory untrusted. |
| **Crash during Step B** | Complete `records.jsonl`, partial `events.jsonl` | **FAIL-CLOSED:** No manifest exists. Directory untrusted. |
| **Crash between B and C** | Both `.jsonl` files complete, no `manifest.json` | **FAIL-CLOSED:** No manifest exists. Loader rejects. |
| **Crash during Step C** | Malformed/partial `manifest.json` | **FAIL-CLOSED:** `load_manifest()` fails JSON parse or self-digest check. |
| **Post-Step C Crash** | All files written and `fsync`'d | **SUCCESS:** Manifest verified via external SHA-256 pin. |

---

## 3. Adversarial Edge Cases & Incident Matrix

### 3.1 Network & Connection Anomaly Matrix (N1–N14)

| ID | Failure Mode | Detection Point | Countermeasure | Outcome Code |
| :--- | :--- | :--- | :--- | :--- |
| **N1** | DNS Resolution Timeout | `connect()` phase | Watchdog threshold or 17s cap; exit process if worker hangs | `INCIDENT-DNS` |
| **N2** | TCP Connection Refused | `connect()` phase | Transport catch `ConnectionRefusedError` | `CONNECT_ERROR` |
| **N3** | TCP Handshake Drop / Timeout | `connect()` phase | Hard 5.0s connect timeout | `CONNECT_TIMEOUT` |
| **N4** | TLS Handshake Failure | SSL layer | Transport catch `SSLError` | `TLS_ERROR` |
| **N5** | Mid-Body Socket Drop | `read()` phase | Catch `RemoteDisconnected` / `BrokenPipeError` | `READ_ERROR` |
| **N6** | Mid-Body Stalled Read | `read()` phase | Hard 10.0s read timeout | `READ_TIMEOUT` |
| **N7** | Total Request Exceeds 17s | Watchdog thread | `socket.shutdown(SHUT_RDWR)` | `PACE8_CANCELLATION` |
| **N8** | Non-200 HTTP Status (e.g., 429) | HTTP response parse | Set transport `_disabled = True`, trigger incident abort | `INCIDENT-HTTP-STATUS` |

### 3.2 Timing & Clock Anomaly Matrix (T1–T9)

| ID | Anomaly | Detection Point | Countermeasure | Outcome Code |
| :--- | :--- | :--- | :--- | :--- |
| **T1** | Backward Monotonic Shift | Clock read | Catch monotonic regression in pacer | `INVALID-PACING` |
| **T2** | Wall-Clock NTP Jump | Clock read | Pacer strictly uses `monotonic_ns()`, ignoring wall clock | N/A (Isolated) |
| **T3** | OS Suspend / Resume | Estimator check | Uncertainty $W > 250\text{ ms}$; skip boundaries; 3 skips aborts | `INCIDENT-SYNC` |
| **T4** | Pacing Wake-Up Delay | Sleep wake-up | Re-evaluate $now \ge start\_at$; skip if window expired | `MISSED-WINDOW` |

### 3.3 Memory & Resource Guardrails

- **Body Memory Cap:** Max 4 MiB per HTTP response body. Total accumulated response memory capped at 50 MiB across a session (~750 requests).
- **Orphan Worker Prevention:** If a request worker thread fails to join within $1.0\text{ s}$ of `socket.shutdown()`, the runner immediately seals the session as `INCIDENT-ORPHAN-WORKER` and calls `sys.exit(1)`.

---

## 4. Offline Verification Plan & Open Questions

### 4.1 Dry-Run Verification Requirements
Before any live network execution (`--live`), the session runner must pass the following offline simulation gates against `FakeClock` and `ScriptedTransport`:

1. **Full OBS-01 Simulation:** Run all multi-probe combinations against synthetic candle boundaries. Verify all 12-field kline tuple parsed correctly.
2. **Full OBS-02 Session A & B Simulation:** Execute 12 consecutive 5m boundaries + 4h boundary. Verify `SYNC-SKIPPED` handling and estimator intersection calculations.
3. **Thread Inventory Check:** Assert zero unapproved threads spawned during execution.
4. **Crash Matrix Injection:** Inject process kills at all 7 crash points and verify fail-closed loader rejection.

### 4.2 Open Questions for Reviewer Agent (Alex)

1. **Outer Evidence Indexing:** Should runner execution metadata (Python version, OS, host, commit SHA) be written to a top-level `summary.json` alongside the frozen `obs-run-manifest/1` structure?
2. **Body Memory Abort Condition:** Should exceeding the 50 MiB aggregate response body memory limit be designated as an explicit fourth abort condition (`INCIDENT-MEMORY`)?
3. **Fallback Host Policy:** Does protocol approval strictly forbid fallback to `api.binance.com` if `data-api.binance.vision` experiences DNS outages?
4. **Uncertainty Fallback Retry Count:** Confirm if 4 extra `/time` samples is the absolute ceiling before skipping a boundary when uncertainty exceeds $250\text{ ms}$.
5. **Orphan Worker Termination:** Is immediate process exit (`sys.exit(1)`) after a $1.0\text{ s}$ worker join timeout the approved fail-closed behavior for hung DNS resolution?
6. **SIGINT Single vs. Double Signal:** Confirm that single SIGINT initiates a graceful sealed abort, whereas double SIGINT exits immediately leaving no manifest (untrusted directory).
7. **Post-Run Self-Audit Failure Action:** If self-audit fails post-persistence, should the runner rename the directory to `.failed_audit/` to prevent accidental publication?
8. **Rate Cap Margin:** Confirm that $0.6\text{ s}$ minimum start gap (1.66 req/s) is acceptable as our operational floor for the 2 req/s Binance cap.
