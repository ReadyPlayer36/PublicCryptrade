# OBS-01/02 Session Runner and Evidence Writer — Architectural Blueprint v1.2

- **Document Version:** v1.2 — supersedes v1.1 (commit `4fdfbe3`). Resolves Reviewer (Alex) re-audit amendments **R1–R12** in full. Disposition remains **NOT APPROVED** until R1–R12 are accepted; **Milestone 1 (implementation) stays BLOCKED** until then.
- **Target Branch:** `impl-obs-harness`
- **Protocol Spec:** `docs/obs-protocol.md` v0.5 (commit `7ef4986`)
- **Status:** Architectural Design Blueprint (Pre-Implementation)
- **Scope:** execution runner (`--live`), single-pacer concurrency, evidence writer, staging publication, outer provenance index, signal handling, fail-closed error handling.

Notation: **[EXISTS]** implemented and regression-tested on this branch; **[NEW]** specified here, to be built; **[DECISION R#]** a choice the reviewer must confirm (§6.2). Constants cited throughout are the real ones: `DEADLINE_NS = 17 s`, `AUDIT_MAX_DURATION_NS = 18 s`, `CANCEL_GRACE_NS = 1 s`, `SPACING_NS = 600 ms`, `WINDOWS = ((1 s, 2), (60 s, 60))`, `OBS01_SPACING_NS = 2 s`, `OBS01_WINDOWS = ((2 s, 1), (60 s, 30))`, `CONNECT_TIMEOUT_S = 5.0`, `READ_TIMEOUT_S = 12.0`, `SEND_TIMEOUT_S = 0.25`, `MAX_BODY_BYTES = 4 MiB`, `MAX_CONSECUTIVE_NO_RESPONSE = 3`, `W_MAX_NS = 250 ms`, `RETENTION_NS = 600 s`, `DELTA = 10⁻⁴`.

---

## 0. Revision Map (R1–R12)

The AR-01…AR-12 amendments of the v1.1 review remain incorporated; R1–R12 are refinements demanded at re-audit and each supersedes the corresponding v1.1 text where they differ.

| Amendment | Requirement | Sections | What v1.2 adds beyond v1.1 |
| :--- | :--- | :--- | :--- |
| **R1** | Genuinely enforceable DNS termination | 3.1, 4.2 (N1) | Killable resolver subprocess; pinned-address connects eliminate all run-path resolution; v1.1's implicit "deadline monitoring handles DNS hangs" claim withdrawn; residual in-process hang reclassified as an **unsealed, untrusted execution failure (T2)**, never as background-thread termination. |
| **R2** | Reconcile S1 (pacing sample) with S6 (network handoff) | 1.1, 1.3 | **Logical dispatch timestamp semantics adopted explicitly**; worker scheduling/connect delay modeled (`wire_ns = start_ns + δ`); one observational worker clock read for diagnostics that feeds no decision; S1–S6 restated without contradiction. |
| **R3** | Full normative loop pseudocode with GV-6/GV-7 oracles | 1.2 | Complete `execute()` listing (admission → commit loop → dispatch → incident ladder) plus executable GV-6 and GV-7 oracle blocks with the protocol's exact expected values and a double-read tripwire. |
| **R4** | Complete combined rolling-release algorithm + all four GV-8 vectors | 1.4 | Per-window release components combined by `max`, correctness argument, both-caps-bind worked examples (OBS-02 vector (iii) and the OBS-01 exact-tie vector), and all four GV-8 (i)–(iv) vectors fully computed. |
| **R5** | Chunk-level aggregate budget enforcement | 3.2 | Normative check `retained + len(chunk) > 50 MiB` inside the streaming loop; pre-dispatch guard demoted to advisory fast-path only. |
| **R6** | Byte domains and compressed-transfer rules | 3.2 | Domains A (retained payload), B (transient per-request), C (serialized artifacts) with exact caps; never-decompress rule in the run path; offline expansion caps (`MAX_DECOMPRESSED_BYTES`, `MAX_EXPANSION_RATIO`). |
| **R7** | No-replace collision semantics and symlink/path protection | 2.1 | `renameat2(RENAME_NOREPLACE)` primary, parent-fd `flock`, `O_NOFOLLOW` opens, `(st_dev, st_ino)` identity checks, `lexists` collision rule; plain `os.rename` documented as **not** no-replace (it silently replaces empty directories). |
| **R8** | Receipt/index publication gap relative to S | 5.2 | `RECEIPT := fsynced outer index` (stdout pin demoted to best-effort mirror); the unavoidable two-location window is named as terminal state **T4 SEALED-UNRECEIPTED** with the deterministic `obs-index finalize` recovery. |
| **R9** | Atomic quarantine publication rules | 2.3 | Quarantine is a publication with the same no-replace/flock/fsync discipline via one shared `publish_dir()` helper; trigger rules (verdict-only), quarantine index, rename-failure fallback to T2. |
| **R10** | Emergency exit and manifest visibility during parent `fsync()` | 2.1.1, 4.1, 5.2 | Rename = visibility, fsync = durability (stated precisely); emergency landing table for every bytecode boundary inside COMMITTING; hung-syscall residual classified honestly. |
| **R11** | Fully enumerated incident/crash matrices | 4.2, 4.3 | Every row of N1–N14, T1–T9, P1–P8, E1–E12, K0–K12 written out in full with condition, detection, countermeasure, audit effect, and terminal state — no row defers to another. |
| **R12** | Exhaustive terminal invariant | 5.3 | Terminal state set **T0–T6**, the total `observe()` resolver, cause→state and conjunct→state tables, the exit-code function, and a totality/mutual-exclusion argument covering every crash, cancellation and receipt failure. |

---

## 1. Concurrency Model & Pacing Mechanics

### 1.1 Thread Inventory [EXISTS / RECONCILED / amended by R2]

The OBS session runner enforces a **two-thread ceiling**:

1. **Main pacing / orchestration thread** (the process main thread) — owns all *authoritative* monotonic clock reads, pacing computations, inline watchdog deadline monitoring, socket-shutdown triggers, event-log mutations, and finalization. It reads the **wall clock only inside the outer-index writer** (§5.1), where the value is labeled diagnostic and never consumed by logic.
2. **Request worker thread** (name `obs-request`, `daemon=True`) — at most one alive at any time; performs network I/O exclusively. Clock reads: **zero for decisions**, plus exactly **one observational read per request** (`wire_ns`, §1.3) whose value feeds only the diagnostics aggregate — never admission, pacing, deadline, classification or audit.

The v1.0 "watchdog thread" is eliminated: `run_with_deadline` executes on the calling (pacing) thread; its `_wait_until` loop recomputes the remaining time from the absolute deadline on every iteration, calls `state.cancel()` (socket `shutdown(SHUT_RDWR)` + close) inline, and enforces the 1 s `CANCEL_GRACE_NS`.

**Structural tests (fail CI before any `--live` cut):**

- no `threading.Timer`, no `asyncio`, no `Event.wait(timeout)` used as a pacer;
- no `threading.Thread` construction outside `watchdog.run_with_deadline`;
- no socket/connection construction outside `transport.py` (single connection factory, `auto_open = 0`, no pool);
- no `socket.getaddrinfo` / `gethostbyname` outside the resolver module `_resolve.py` (**R1**);
- no `time.time()` / `datetime.now()` outside the outer-index writer;
- no `sys.exit` / `os._exit` outside `main()` and the signal handler of §4.1;
- worker-side clock reads limited to the single `wire_ns` site (**R2**), with no consumer outside the index writer.

### 1.2 Normative `execute()` Loop — Full Pseudocode with GV-6/GV-7 Oracles [R3]

The three drift-gap sites of the pre-v1.1 design are (1) a scalar target computed once before the loop (stale `D` → early start), (2) the check-then-sample gap (condition read and recorded `start_ns` are different reads), and (3) the double clock read at PACE-7 admission (`decided_at` vs `earliest_possible_start_ns()`'s own read). The normative listing below closes all three.

```python
def execute(spec, plan, target_fn=None):        # pacing thread only.
    # target_fn: (int) -> int | None.  None for in-group requests.
    # For first-of-group: target_fn(now) = ceil_ns(deadline_exact(X, now)) — the fixed point D re-evaluated
    # at every wake, never captured as a scalar before the loop.   [gap 1 closed]

    # ---------- pre-dispatch gates (no clock read) ----------
    if pacer.abort_reason is not None:            raise PacerAborted(pacer.abort_reason)
    if stop_requested:                            raise OperatorStop()
    validate_spec(spec)                           # allow-list: HOST, /api/v3/ prefix, no credentials [EXISTS]
    if retained_total + MAX_BODY_BYTES > SESSION_BODY_BUDGET_BYTES:      # advisory fast path, R5
        raise MemoryIncident("session budget reserve exhausted")

    # ---------- PACE-7 admission (first-of-group only) ----------
    if spec.group_kind == "first":
        decided_at = clock.now_ns()                                   # (A) THE single decision read
        m_e = max(decided_at, pacer.earliest_start_ns())              # earliest from RECORDS only [gap 3 closed]
        decision = decide_admission(estimator, m_e_ns=m_e, boundary_ms=spec.boundary_ms,
                                    offset_ms=plan.offset_ms, tol_ms=plan.tol_ms, decided_at_ns=decided_at)
        writer.append_decision(boundary_ms=spec.boundary_ms, group_name=spec.group_name,
                               decided_at_ns=decided_at, m_e_ns=m_e, records=pacer.records)   # immediately
        if not decision.admitted:
            skips[(spec.boundary_ms, spec.group_name)] = decision      # skip: nothing is dispatched
            return None

    # ---------- single-read commit loop ----------
    while True:
        now = clock.now_ns()                                          # (R) THE one read of this iteration
        earliest = pacer.earliest_start_ns()                          # records-only: end, start+spacing, releases
        start_at = earliest if target_fn is None else max(earliest, target_fn(now))   # re-evaluated every wake
        if spec.window_end_ns is not None and earliest > spec.window_end_ns:          # missed window (P5)
            writer.append_decision(..., decision="MISSED-WINDOW", records=pacer.records)
            return None
        if now >= start_at:                                           # admission predicate == this read [gap 2 closed]
            break
        if stop_requested:                                            # checked at every wake slice (§4.1)
            raise OperatorStop()
        clock.sleep_until_ns(start_at)                                # inline monotonic wait; re-reads each wake
    start_ns = now                                                    # committed WITHOUT any further clock read

    # ---------- commit-time invariants (pure functions of stored integers; no clock read) ----------
    if start_ns < pacer.earliest_start_ns():                          raise ClockInvariant(...)      # P1 guard
    if target_fn is not None and start_ns < target_fn(start_ns):      raise FixedPointInvariant(...) # GV-6/7 guard

    # ---------- dispatch ----------
    result = transport.send(spec, deadline_at_ns=start_ns + DEADLINE_NS)   # absolute deadline; §1.3 handoff
    end_ns = clock.now_ns()
    record = RequestRecord(seq=len(pacer.records) + 1, role=spec.role, path=spec.path,
                           start_ns=start_ns, end_ns=end_ns, status=result.status, error=result.error,
                           group_name=spec.group_name, group_kind=spec.group_kind,
                           boundary_ms=spec.boundary_ms, body=result.body,
                           headers=tuple(sorted(result.headers.items())))
    pacer.records.append(record)                                      # append-only; never mutated afterwards

    # ---------- incident ladder (abort latching matches audit derived rules exactly) ----------
    if cancel_failed:
        pacer.abort("INCIDENT-CANCEL"); raise CancellationFailed(...)
    if result.status != 200:
        pacer.abort(f"HTTP-{result.status}"); raise NonOkResponse(record)         # derived == abort_seq ✓
    if result.status is None:
        no_response_streak += 1
        if no_response_streak >= MAX_CONSECUTIVE_NO_RESPONSE:
            pacer.abort("INCIDENT-NETWORK"); raise NetworkIncident(...)          # derived == abort_seq ✓
    else:
        no_response_streak = 0

    retained_total += len(record.body) + header_bytes(record.headers)   # retained-domain accounting (R5)
    runner.validate_body(spec, record)                                 # JSON/shape/host/open-time → INCIDENT
    return record
```

Supporting rules in the listing: `earliest_start_ns()` (§1.4) recomputes from the record list every iteration — no accumulator, no phase state; `SyncInadequate` raised by `target_fn` is caught pre-dispatch and routed to the skip path (T9); a commit-time invariant failure aborts **before** dispatch, so no invalid record can ever be appended (the previously appended records seal normally).

**Exactness lemma.** For integer `now`, `now ≥ ⌈D(now)⌉ ⇔ now ≥ D(now)`. Therefore the commit instant satisfies the fixed point *at the recorded value*: `start_ns ≥ D(start_ns)`, with no dependence on where `D` moves afterwards.

**GV-6 oracle (protocol v0.5 line 191) — mandatory executable test:**

```python
# One sample (a=0, b=200, s=1,700,000,000,200), X = 1,700,000,300,000, DELTA = 1e-4.
# In nanoseconds: D(m) = 300,000,000,000 + 1e-4 * m    (equivalent to D_ms = 300,000 + delta*m)
D6  = lambda m: 300_000_000_000 + Fraction(1, 10_000) * m
trace = run_commit_loop(clock=FakeClock(0), target_fn=D6)      # instrumented: logs (now, D(now), admitted)

assert [w.now for w in trace] == [0,
                                  300_000_000_000,        # D moved later here   -> wake-up 1
                                  300_030_000_000,        # D moved later again  -> wake-up 2
                                  300_030_003_000,        # D(now) = ...000.30003 > now -> sleep to ceil
                                  300_030_003_001]        # admitted
assert trace[3].admitted is False                          # condition FALSE at 300,030,003,000 ns
assert trace.committed_start_ns == 300_030_003_001         # protocol's exact first integer-ns instant
assert len(trace) >= 4                                     # protocol requires >= 2 wake-ups
assert trace.committed_start_ns >= D6(trace.committed_start_ns)   # fixed point holds AT the record
assert reads_per_iteration == 1                            # tripwire: a 2nd clock read raises
assert committed_value_is_the_admitted_value               # Gap-2 guard: same read, same integer
```

**GV-7 oracle (protocol v0.5 line 193) — mandatory executable test:**

```python
# Two samples: (a=0,        b=200,     s=1,700,000,000,200)
#              (a=100_000,  b=100_060, s=1,700,000,100_062);  X = 1,700,000,300,000
est = build_estimate(samples)                               # [EXISTS] estimator machinery
assert (est.lo, est.hi) == (1_699_999_999_982.0, 1_700_000_000_083.0)   # Theta intersection, width 101.0
assert per_sample_roots == [300_030.0030003, 300_018.00180018]          # ms, protocol's values
assert min(per_sample_roots) == 300_018.00180018                        # m* = min over samples

trace = run_commit_loop(clock=FakeClock(...), target_fn=lambda now: ceil_ns(deadline_exact(X, est, now)))
assert trace.committed_start_ns == 300_018_001_801         # first valid integer-ns instant
assert predicate_at(300_018_001_800) is False              # previous nanosecond fails
assert trace.committed_start_ns == closed_form_start_ns(X, ...)    # closed-form cross-check [EXISTS]
assert reads_per_iteration == 1                            # same tripwire as GV-6
```

### 1.3 Authoritative `start_ns` — Logical Dispatch Timestamp Semantics [R2]

**Adopted semantics.** `start_ns` is the **logical dispatch timestamp**: the single monotonic read on the pacing thread at which the admission predicate held (§1.2). It is the sole authority for GV-6/GV-7 oracles, PACE-1…PACE-8, audit checks (b)–(f), and every offline V-series input derived from records. There is no second authoritative start anywhere in the design.

**Acknowledged gap — worker scheduling and setup delay.** The actual first byte reaches the wire strictly later:

```
wire_ns = start_ns + δ_queue + δ_connect + δ_tls + δ_write
  δ_queue   — worker thread start latency (GIL acquisition, OS scheduling)   >= 0, measured
  δ_connect — TCP connect to the pinned address                             <= CONNECT_TIMEOUT_S = 5.0 s
  δ_tls     — TLS handshake                                                  bounded by socket timeouts
  δ_write   — request head write                                             <= SEND_TIMEOUT_S = 0.25 s
  invariant: wire_ns <= start_ns + DEADLINE_NS - epsilon   (worker deadline rechecks at post-setup and
              pre-write cut the request off at 17 s)   and   wire_ns < end_ns
```

**Measurement without violating clock ownership.** Two observational reads, both outside the decision path:

- `dispatch_ns` — a **pacing-thread** read taken inside `transport.send` immediately before `thread.start()`; `queue_lag = dispatch_ns − start_ns` measures pacing-side queueing. Warn at `HANDOFF_WARN_NS = 1 ms` (an excess means harness-side oversubscription — an `EXEC_DIAGNOSTIC` warning).
- `wire_ns` — the **single worker-side observational read**, taken immediately before the first `sendall()` of the request head (after TCP+TLS); `setup_lag = wire_ns − dispatch_ns`.

Both values flow only into transport-side aggregate counters (`handoff.{max_queue_lag_ns, max_setup_lag_ns, samples, warn_flags}`, jitter warn at `WIRE_JITTER_WARN_NS = 50 ms`) which are copied into the outer index at finalization. A structural test asserts that no module outside `transport.py` and the index writer can read `wire_ns`/`dispatch_ns`, and that no pacing, admission, deadline or classification expression references them.

**Why not make the wire instant authoritative.** The pacing thread is blocked while the worker performs setup; reading after `send` returns would yield ≥ `end_ns`, not the handoff. Moving authority to the worker would race admission (two threads deciding `start_ns`) and shatter the single-thread clock-ownership invariant that makes GV-6 testable. Dispatch semantics plus one observational worker read is the only arrangement that keeps both single ownership and honest measurement.

**S1–S6, final:**

| ID | Invariant |
| :--- | :--- |
| **S1** | Single source: `start_ns` is produced by exactly one pacing-thread read (the commit read (R)); recorded verbatim, never adjusted or re-derived. |
| **S2** | Self-consistent at the recorded instant: `start_ns ≥ earliest_start_ns()` always, and `start_ns ≥ D(start_ns)` for first-of-group — both asserted pre-dispatch (no clock read). |
| **S3** | Sole anchor: the deadline `start_ns + 17 s`, PACE-2/3 spacing and windows, PACE-5 audit recomputations, and PACE-7 `m_e ≤ start_ns` all derive from this one value. |
| **S4** | Distinct neighbors: `decided_at ≤ start_ns ≤ dispatch_ns ≤ wire_ns < end_ns`; transport-internal reads (remaining/over, watchdog waits) are enforcement only and never become a start. |
| **S5** | Never derived: no `prev + spacing`, no wall clock, no re-sampling after the fact. |
| **S6** | **Audit-equivalent, handoff-delimited:** the audit's authority is `start_ns`; `wire_ns` is observational, bounded, indexed, and can never reclassify a record. Server-visible arrival (`wire_ns + RTT`) is explicitly **out of protocol scope** — protocol GV oracles and audit checks are harness-timestamp-defined. A `queue_lag` or jitter warning raises `EXEC_DIAGNOSTIC` in the index; it never alters a record or an outcome (deterministic: warnings do not change terminal state, §5.3). |

### 1.4 Rolling Release — Complete Combined Algorithm [R4]

**Definitions.** A window `(t − W, t]` over integer nanoseconds is **open-left, closed-right**: start `s` counts iff `t − W < s ≤ t`. `window_count(starts, t, W) = bisect_right(starts, t) − bisect_right(starts, t − W)` — shared verbatim by pacer and audit.

**Normative algorithm** (recomputed from the record list on every loop iteration; inputs are records only — no clock read):

```python
def earliest_start_ns(records, windows, spacing_ns):
    if not records:
        return 0
    last = records[-1]
    e = max(last.end_ns,                                    # PACE-1: completion
            last.start_ns + spacing_ns)                     # PACE-2: spacing
    for (W, cap) in windows:                                # PACE-3: BOTH windows always evaluated
        if len(records) >= cap:
            e = max(e, records[-cap].start_ns + W)          # release component of this window
    return e
```

**Correctness argument.** With `n ≥ cap` existing starts, the earliest `t` at which window `(t − W, t]` holds at most `cap − 1` *existing* starts (so the new one makes `cap`) is `t = starts[n − cap] + W`: at that `t`, `t − W = starts[n−cap]` is excluded by the open left edge, leaving exactly `cap − 1` later starts inside; any `t` one nanosecond smaller pulls `starts[n−cap]` inside, giving `cap` existing + the new one. Because each window is an independent constraint, the conjunction of all constraints is the `max` of their individual releases, together with the PACE-1/PACE-2 floors (the floors also guarantee `t ≥ starts[n−1]`, which the release component alone does not assume). Taking `max` per iteration and never an accumulator makes the function memoryless: slow responses only push later starts later (PACE-6 by construction).

**Both caps binding — worked examples.**

*OBS-02, GV-8 (iii) vector* — 60 starts at `k × 600,000,000 ns` (last at `35.4 s`); components for the 61st:

| Component | Value (ns) | Binding? |
| :--- | ---: | :--- |
| PACE-1 completion (`last.end`) | ≈ 35,400,000,000 + RTT | no |
| PACE-2 spacing (`last.start + 600e6`) | 36,000,000,000 | no |
| 1 s window, cap 2 (`starts[58] + 1e9`) | 34,800,000,000 + 1,000,000,000 = 35,800,000,000 | no |
| 60 s window, cap 60 (`starts[0] + 60e9`) | 0 + **60,000,000,000** | **YES** |
| **combined earliest** | **60,000,000,000** | — |

At `59,999,999,999 ns` the 60 s window `(−1, 59,999,999,999]` would contain all 61 starts → count 61 > 60 → violation; PACE-2 alone would have allowed `36.0 s`.

*OBS-01 exact-tie vector (both caps bind simultaneously)* — 30 starts at `OBS01_SPACING_NS = 2 s` (`starts[k] = 2k × 10⁶` ns, last at `58 s`):

| Component | Value (ns) | Binding? |
| :--- | ---: | :--- |
| PACE-2 spacing (`58e9 + 2e9`) | 60,000,000,000 | **YES (tie)** |
| 2 s window, cap 1 (`starts[29] + 2e9`) | 58,000,000,000 + 2,000,000,000 = 60,000,000,000 | **YES (tie)** — cap-1 window ≡ spacing rule |
| 60 s window, cap 30 (`starts[0] + 60e9`) | 0 + 60,000,000,000 = 60,000,000,000 | **YES (tie)** |
| **combined earliest** | **60,000,000,000** | all three coincide |

At `59,999,999,999 ns`: spacing gap `1,999,999,999 < 2e9` → fail **and** window count 31 > 30 → fail. Every constraint independently rejects the early start; the earliest admissible instant is exactly `60,000,000,000 ns`.

*Observation (documented, not a change):* under OBS-02 parameters the 1 s/cap-2 window can never exceed the spacing floor for legal starts (two starts need ≥ 600 ms separation, so 3 starts cannot fit in any 1 s window) — it is therefore an independent **audit guard** against pacing bugs rather than a binding release constraint, and the algorithm still evaluates it every iteration.

**GV-8 (i)–(iv) — all four boundary vectors as mandatory gates**, each run through (a) the pacer functions, (b) a live-loop dry run, and (c) the independent audit recount, plus a re-derivation straight from the protocol text so a shared implementation bug cannot self-confirm:

| GV-8 | Vector (protocol line 195) | Components evaluated | Required verdict |
| :--- | :--- | :--- | :--- |
| **(i)** | 61 starts at `0, 1e9, …, 60e9` (spacing 1 s); the new start at `60e9` | 1 s/cap 2: `starts[59] + 1e9 = 60e9` ✓; 60 s/cap 60: `starts[0] + 60e9 = 60e9` ✓; spacing `60e9 − 59e9 = 1e9` ✓; window at `60e9`: `(0, 60e9]` holds exactly 60 | **PASS** |
| **(i′)** | same, but the new start at `59,999,999,999` | 60 s release `60e9 > 59,999,999,999`; window `(−1, 59,999,999,999]` holds 61 | **FAIL** |
| **(ii)** | starts `0, 600e6, 1e9` | 1 s/cap 2: window `(0, 1e9]` holds 2 → PASS; spacing `1e9 − 600e6 = 400e6 < 600e6` | spacing check (c) **FAIL** |
| **(ii′)** | starts `0, 600e6, 999,999,999` | 1 s/cap 2: window `(−1, 999,999,999]` holds 3 (release required `starts[0] + 1e9 = 1e9`) | 1 s cap **FAIL** |
| **(iii)** | pacer release: 60 starts at `k × 600e6`, last `35.4 s`; 61st request | combined earliest = `60,000,000,000` (table above) | must start at **exactly `60,000,000,000 ns`**; `59,999,999,999` **FAIL** |
| **(iv)** | spacing boundary | gap `599,999,999` vs `600,000,000` | `599,999,999` **FAIL**; `600,000,000` **PASS** |

All attempts count: the lists fed to the algorithm are *all* recorded starts, including timed-out, cancelled and failed requests.

---

## 2. Persistence, Sealing & Self-Verification

### 2.1 Durable Staging Publication with No-Replace Collision Semantics [R7]

**Defect lineage.** v1.0 wrote files directly into the final run directory; v1.1 added staging but specified plain `os.rename`, which on POSIX **silently replaces an empty target directory** — not a no-replace primitive. v1.2 makes publication collision-proof and symlink-safe end to end.

```python
# 0. PREFLIGHT
if os.path.lexists(run_dir):                      # ANY occupant: dir, file, symlink, dangling symlink
    raise CollisionIncident(run_dir)              # never merge, never overwrite, never follow
runs_root_real = os.path.realpath(runs_root)      # pinned once; unexpected symlink components -> refuse
attempt = f"{utc_stamp}-{pid}-{counter}"          # unique; collision doubly impossible

# 1. STAGING (same parent directory => same filesystem => atomic, O(1) rename)
staging = parent / f".staging-{attempt}"
os.mkdir(staging)                                 # fails EEXIST even if a symlink occupies the name
st_dev, st_ino = os.lstat(staging)                # identity recorded for the swap check in step 5

# 2. WRITE (strict "xb" per file, single write each; manifest last — it commits the triple)
write_records(staging / "records.jsonl");  fsync_file(fd)         # [EXISTS write, fsync NEW]
write_events(staging / "events.jsonl");    fsync_file(fd)         # [NEW fsync]
write_manifest(staging / "manifest.json"); fsync_file(fd)         # [NEW fsync]; schema untouched (§5.1)

# 3. STAGING DIR FSYNC (durability of the three dirents, no symlink follow)
fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); os.fsync(fd); os.close(fd)   # [NEW]

# 4. VERIFY — write-read-audit over reloaded artifacts (§2.2), performed ON STAGING

# 5. PUBLISH — guaranteed no-replace, under an exclusive lock
pfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)     # same fd reused for the fsync
fcntl.flock(pfd, fcntl.LOCK_EX)                                       # serialise harness processes
st = os.lstat(staging)
assert os.path.isdir(st.st_mode) and (st.st_dev, st.st_ino) == (st_dev, st_ino)   # defeat swap attacks
if os.path.lexists(run_dir):
    raise CollisionIncident(run_dir)
renameat2(AT_FDCWD, staging, AT_FDCWD, run_dir, RENAME_NOREPLACE)      # primary: truly no-replace
#   fallback (ENOSYS/EINVAL, non-Linux) valid ONLY under the flock + lexists check:
#     os.rename(staging, run_dir); require lstat(run_dir).st_ino == st_ino  (swap detection), else incident
#   ENOTEMPTY / EEXIST => CollisionIncident
os.fsync(pfd)                                                          # same fd: no re-open TOCTOU
os.close(pfd)                                                          # releases the flock

# 6. RECEIPT — outer index written and fsynced (§5.2)
```

Rules stated as normative:

- **No-replace is mandatory.** `renameat2(RENAME_NOREPLACE)` is the primary primitive; plain `os.rename` is *not* accepted as no-replace because it silently replaces an empty target. The portable fallback is licensed only under the parent-fd `flock` with the `lexists` precheck and the `(st_dev, st_ino)` post-verify.
- **Symlink/path protection:** `O_NOFOLLOW | O_DIRECTORY` on every directory open (staging fsync and parent fsync); `os.mkdir` for staging creation (rejects a pre-planted symlink at the name); `lexists` treats symlinks of any kind as collisions; the runs-root path is `realpath`-pinned at startup; publication happens under an exclusive lock so check and rename cannot interleave with another harness process.
- **Commit point** = step 5 (rename); **durable commit** = the parent fsync; **receipt** = step 6. On any failure in steps 5–6 the staging directory remains as debris — never a partial run directory (terminal T2/T4, §5.3).
- Run and quarantine renames share one helper `publish_dir(staging, target)` — a single implementation, one test battery (§6.1).

### 2.1.1 Visibility and Durability During Parent `fsync()`; Emergency Landings [R10]

**Visibility semantics.** The rename is the visibility event: the instant it returns, the run directory is visible to every reader and internally consistent — all three files were fsynced *before* the rename, and rename is atomic, so no reader can ever observe a partial triple. The parent `fsync()` is a **durability barrier, not a visibility barrier**: it makes the directory entry survive power loss; it changes nothing that concurrent readers can see. A recovery tool (or a second process) may safely open and read the run directory at any point after the rename.

**Emergency landings.** The signal handler runs only at bytecode boundaries in the main thread — never mid-syscall — so a pending second-signal emergency lands between steps, never inside one:

| Pending emergency lands… | Observable state | Terminal state (§5.3) | Exit |
| :--- | :--- | :--- | --- |
| before the rename | staging debris only | **T2** | 130/143 |
| between rename and parent fsync | run dir visible & complete; durability pending | **T4** — if the system survives, recovery finalises it; if power then fails, the entry vanishes *wholly* → observed as **T2** (never partial) | 130/143 |
| between parent fsync and index fsync | durable, verified run dir; no receipt | **T4** | 130/143 |
| after index fsync | complete commit | **T6** (S true) or **T5** | 130/143 |

SIGKILL or power loss mid-`fsync` cannot construct partial state: it is one kernel syscall over a directory entry whose contents are already durable — post-reboot the entry is either durable (T4) or wholly absent (T2).

**Hung syscall residual (honest classification).** If `fsync` (or any COMMITTING syscall) blocks in an uninterruptible kernel wait, neither PEP-475 retry nor our handler can run: the process cannot self-classify while stuck. Declared as a residual risk with deterministic post-mortem resolution: cause = `EXEC-FAILURE`, terminal state = whatever `observe()` (§5.3) reads after the process dies (T4 or T2 by artifact presence). The design does **not** claim to terminate uninterruptible kernel waits — the same honesty rule R1 imposes for resolution.

### 2.2 Write-Read-Audit Self-Verification [AR-06 / R8 inputs]

Verification reads the artifacts back from disk and audits *those bytes*; in-memory objects serve only as the comparison baseline:

```python
pin  = write_run(staging, records, events)                      # persists; returns sha256(manifest bytes)
loaded = load_run(staging, pinned_manifest_sha256=pin)          # re-parsed from disk

if loaded.records != tuple(records) or loaded.events != tuple(events):        # element-wise equality
    quarantine(staging, reason="persisted != in-memory"); return Failure      # (i)
result = audit_run(staging, pinned_manifest_sha256=pin,
                   wrapper_count=transport.sent,               # independent runtime instrument
                   profile=plan.profile,                       # from the plan, never from data
                   abort_seq=pacer.abort_seq,
                   skips=skips, boundary_skips=boundary_skips,
                   expected_boundaries=plan.expected_boundaries)              # (ii)
if not result.ok:
    quarantine(staging, failures=result.failures); return Failure
```

Argument sources (every audit input traceable to something outside the objects under audit): records/events/manifest from `load_run` (reloaded bytes); `jsonl_count`/`manifest_count` derived by `audit_run` from the persisted files [EXISTS]; `wrapper_count = transport.sent` (independent counter); profile and expected boundaries from the plan; skip decisions from the plan + the DECISION events; `abort_seq` from the pacer latch (reconciled against `abort_condition_seq(records)` by check (a)).

**Forbidden patterns (each an explicit failing test):** `wrapper_count=len(records)` (comparing memory with itself — v1.0's defect); auditing in-memory tuples via `audit_records` instead of `audit_run(dir, …)`; re-serializing in-memory bytes for digest comparison instead of `load_run` output; declaring success before both `load_run` and `audit_run` return on the persisted path; trusting an in-memory manifest dict as the authentication input (the pin must cover the on-disk bytes).

### 2.3 Atomic Quarantine Publication Rules [R9]

Quarantine is a **publication of a different kind** and obeys the same discipline:

1. **Trigger — verdict only.** The sole trigger is a completed verification/audit *failure* (persisted ≠ in-memory, pin/auth/digest/count/chain failure, or any audit check failing). A crash before the verdict is *not* quarantine — it leaves ordinary staging debris (K7), because quarantine means "written, then rejected", while debris means "unknown".
2. **Preconditions.** Staging holds the fully-written, fully-fsynced triple (verification only ever runs after §2.1 steps 2–3).
3. **Target.** `qdir = runs/<session>/<attempt>.unverified` — unique per attempt; `lexists` precheck; published through the same `publish_dir()` helper: parent-fd `flock`, `(st_dev, st_ino)` identity, `renameat2(RENAME_NOREPLACE)`, parent fsync on the same fd. Collision at the quarantine name (practically impossible; unique attempt ids) leaves the staging debris → T2, exit 2.
4. **Atomicity.** One rename: readers see either nothing or the complete rejected triple; never a partial quarantine directory.
5. **Receipt for quarantine.** The outer index is written with `terminal_state: "QUARANTINED"`, `quarantine_path`, the full `audit_failures[]` list, and `manifest_sha256` (pin), then fsynced. If the index write fails, the state remains T3 (defined by directory presence); the index is recovered later by `obs-index finalize --quarantine`.
6. **Never delete, never retry in place.** The quarantine directory is retained indefinitely; no run directory may ever be created for that attempt; a rerun receives a fresh attempt id. Verification failure therefore never risks evidence: the rejected bytes are preserved exactly as written.

### 2.4 Evidence-at-Rest Defenses (A1–A12) [retained from AR-06 scope]

| ID | Attack / failure | Detection | Verdict |
| :--- | :--- | :--- | :--- |
| **A1** | flip any byte in `records.jsonl` / `events.jsonl` | file SHA-256 vs manifest | `ManifestError` → audit (a) rejects the run |
| **A2** | truncate a jsonl file (even after re-pinning) | digest mismatch; missing final newline; count mismatch | rejected |
| **A3** | drop / insert / reorder / duplicate an event | hash chain + `records_before` + `records_digest` prefix binding + `TIMELINE_END`-must-be-final | `EventLogError` → audit (a) |
| **A4** | edit a manifest field | manifest self-digest; recompute self-digest and re-pin → pin check fails | rejected |
| **A5** | fully consistent re-digest forgery of the triple | survives only if the out-of-band pin record is also rewritten — the stated trust limit of §5.1/§5.2 | accepted risk, documented |
| **A6** | substitute another run's `records.jsonl` | digest + record binding vs manifest | rejected |
| **A7** | mutate a loaded manifest in place (`object.__setattr__`) | off-instance seal + weak-identity registry + `ManifestSnapshot` TOCTOU closure [EXISTS] | `ManifestTrustError` |
| **A8** | forge a manifest object (`__new__` / `dataclasses.replace`) | identity registry check [EXISTS] | rejected |
| **A9** | `NaN`/`Infinity`, bool-as-int, float timestamps, duplicate JSON keys, CRLF, huge ints | strict parsers/validators on load [EXISTS]; `allow_nan=False` on canonical write [NEW] | `ManifestError` |
| **A10** | crash during persistence | crash matrix K0–K12 (§4.3) | namespace all-or-nothing; never a partial run directory |
| **A11** | pre-existing/partial directory or symlink at the target path | §2.1 preflight + no-replace rename + `"xb"` per file | collision incident → T2, exit 2; never merge/overwrite |
| **A12** | corrupted or active cooldown file; stale/mismatched pre-registration file | fail-closed pre-flight validation (protocol §2 / §9) | run refuses to start → T0, exit 2 |

---

## 3. Adversarial Edge Cases & Safety Guards

### 3.1 Execution Boundary & DNS Termination [R1]

**Withdrawn claim.** v1.1 implied that inline deadline monitoring handles DNS hangs "without orphan workers". It cannot. During `socket.getaddrinfo` the worker holds no Python-level cancel handle: `state.cancel()` shuts down only sockets we own (none exists yet), an `Event` cannot preempt a C call, daemon status only affects interpreter shutdown nondeterministically (a thread blocked in C may delay or destabilize `Py_Finalize` rather than being cleanly stopped), and no code path can safely force it. The watchdog can *detect* the condition (grace expiry → `CancellationFailed` → transport disable) but **cannot terminate the resolution**. v1.2 therefore never claims background-thread termination for DNS.

**Normative mechanism — process-isolated resolution with pinned addresses.**

1. **All name resolution moves out of the run path** into a dedicated child module `tools/obs/_resolve.py` whose entire body is `socket.getaddrinfo(host, 443, type=SOCK_STREAM)` → prints addresses as JSON → exits.
2. **Bounded, killable wait:** the parent runs it via `subprocess.Popen([sys.executable, "-m", "obs._resolve", host, "443"], stdout=PIPE)` and waits `proc.communicate(timeout=RESOLVE_TIMEOUT_S)` with `RESOLVE_TIMEOUT_S = 5.0` [NEW]. On `TimeoutExpired`: `proc.kill()` (SIGKILL) → `proc.wait(timeout=REAPER_GRACE_S = 2.0)`. A resolver child blocked in a normal (interruptible) libc/DNS wait dies on SIGKILL; if the child is *unkillable* (kernel D-state NSS module), it is **abandoned, not claimed terminated** — and the parent, which never performs resolution itself, still refuses the run.
3. **Resolution happens exactly once per run, at PRE-FLIGHT** — before staging, before any record, before any socket.
4. **Pinned-address connects:** the resolved address is cached; per-request connections go to the pinned IP through the single connection factory, with TLS `server_hostname` and the `Host` header unchanged (certificates validated against the hostname). **The run path performs zero DNS lookups afterwards**; a structural test forbids `getaddrinfo`/`gethostbyname` anywhere except `_resolve.py`. If the pinned address becomes unreachable, TCP connect fails → N2/N3-class `CONNECT_ERROR` — no DNS is involved mid-run, so a mid-run DNS hang is impossible by construction.
5. **Failure classification (R1's fallback clause).** Resolution failure, timeout, or an unkillable child means the run **does not start**: terminal **T0 REFUSED**, exit 2, **no artifacts, no seal, no egress ever**, index `cause: "DNS-UNRESOLVED"`. This is stated as an **unsealed, untrusted execution failure, not a session result** — it must never be reported as a completed `ABORTED` session, and a rerun requires investigation, not blind retry. The same explicit classification (unsealed, untrusted, `EXEC-FAILURE`) applies if in-process resolution is ever observed at runtime despite the structural test (guard trips pre-flight → T0) or if a worker is found stuck unkillable and the process cannot exit (E12 → post-mortem `observe()`, §5.3).

**Lifecycle boundary (unchanged from AR-07, restated):** `run_session()` is the only lifecycle owner — every incident becomes a `RunOutcome` value, its `finally` guarantees finalize (TIMELINE_END → seal → verify → publish/quarantine → receipt) and never raises; `main()` is the only place mapping outcomes to exit codes (§5.3); `sys.exit`/`os._exit` are banned below `main()` and the signal handler by structural test.

### 3.2 Byte-Exact Memory Budgets (`INCIDENT-MEMORY`) [R5, R6]

**Normative streaming enforcement (R5) — the aggregate budget is checked chunk-by-chunk:**

```python
# constants: SESSION_BODY_BUDGET_BYTES = 50 MiB [NEW], MAX_BODY_BYTES = 4 MiB [EXISTS],
#            BODY_CHUNK_BYTES = 64 KiB [NEW], MAX_HEADER_BYTES = 64 KiB [NEW]
declared = headers.get("content-length")
if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
    close(conn); return TransportResult(None, "BODY-LIMIT")        # refuse BEFORE buffering (N9)

total = 0                                                          # this response
while True:
    chunk = response.read(min(BODY_CHUNK_BYTES, MAX_BODY_BYTES + 1 - total))   # hard per-body bound
    if not chunk:                                                  # clean EOF within the cap
        break
    if retained_total + len(chunk) > SESSION_BODY_BUDGET_BYTES:    # R5: CURRENT retained + INCOMING chunk
        close(conn); return TransportResult(None, "BODY-LIMIT")    # checked BEFORE the append
    retained_total += len(chunk)                                   # only ever incremented after the check
    total += len(chunk)
    if total > MAX_BODY_BYTES:
        close(conn); return TransportResult(None, "BODY-LIMIT")    # cap reached with data still coming (N10)
body = buf.getvalue()
if retained_total + header_bytes(headers) > SESSION_BODY_BUDGET_BYTES:   # retained headers count too
    return TransportResult(None, "BODY-LIMIT")
```

Invariants: buffered bytes for one response never exceed `4 MiB + 1`; `retained_total` never exceeds `50 MiB` at any instant (the check precedes every increment); exactly `4 MiB` with clean EOF is accepted; a non-integer `Content-Length` is ignored (the loop governs; the header check can only refuse *earlier*, never buffer more). The pre-dispatch check of §1.2 is retained only as an **advisory fast path** — it avoids *starting* a request that would certainly be aborted (keeping the last record clean) — and is explicitly **not** the enforcement point (R5). Trip behavior: `BODY-LIMIT` record (status `None` → counts as a no-response record for the 3-streak) plus immediate `pacer.abort("INCIDENT-MEMORY")` → sealed abort T5, exit 1; a pre-dispatch trip likewise seals with `abort_seq = len(records)` (audit-consistent: derived `None`, `abort_seq == len(records)`).

**Byte domains (R6):**

| Domain | Contents | Cap | Enforcement |
| :--- | :--- | :--- | :--- |
| **A — retained payload** | `Σ (body bytes + response header bytes)` over all records, held in memory for the whole run | `SESSION_BODY_BUDGET_BYTES = 50 MiB` | bodies: chunk-level check above (normative); headers: post-parse check; overflow → `BODY-LIMIT` → `INCIDENT-MEMORY` |
| **B — transient per-request** | one reused `BODY_CHUNK_BYTES` read buffer, response head ≤ `MAX_HEADER_BYTES = 64 KiB`, TLS record buffers (~16 KiB × small constant), `http.client` internals | `OVERHEAD_BUDGET_BYTES = 1 MiB` | bounded header reader (a `HTTPResponse` subclass accumulating header lines, refusing past the cap → `HEADER-LIMIT`), single reused buffer, `validate_spec` path cap `MAX_PATH_BYTES = 2048`; verified by a `tracemalloc` peak assertion in tests |
| **C — serialized artifacts** | `records.jsonl`, `events.jsonl`, spool — written streamed, never fully materialized again | bounded by Domain A + per-record structural overhead (headers already capped) | streamed writes; spool appended line-by-line under `RETENTION_NS` handling |

**Compressed transfer expansion rules (R6):**

- **The run path never decompresses.** No `gzip`/`zlib`/`bz2`/`lzma`/brotli decode exists anywhere under `tools/obs` (structural test). `Content-Encoding` is recorded as an opaque whitelisted header; budgets count **wire (encoded) bytes as received**, so a compression bomb is capped at `4 MiB` of received data no matter its expansion ratio. `Transfer-Encoding: chunked` chunk sizes are strictly hex-parsed (invalid → `CONNECT_ERROR` class).
- **Offline analysis guard:** any decompression in the V-series/analysis layer must stream under `MAX_DECOMPRESSED_BYTES = 64 MiB` and `MAX_EXPANSION_RATIO = 1000:1` [DECISION R6]; breach → refuse, classified `INCIDENT-MEMORY (analysis)`, with the **raw record bytes kept as the record of truth** — decompressed output never replaces stored evidence.

---

## 4. Signal State Machine, Incident & Crash Matrices

### 4.1 Signal State Machine [AR-09 / R10]

**States:** `PRE-FLIGHT → RUNNING → STOPPING → SEALING → VERIFYING → COMMITTING → COMMITTED`, plus terminal `EMERGENCY`. `COMMITTING` (rename → parent fsync → index fsync) is the critical section; its landing semantics are specified in §2.1.1.

**Handler** (installed on the main thread only by the run boundary; restored in its `finally`; allocates nothing, takes no locks, performs no I/O — the sole permitted `os._exit` site):

```python
def handler(signum, frame):
    signals_seen += 1
    if signals_seen >= 2:
        if state != COMMITTING:
            os._exit(130 if signum == SIGINT else 143)     # untrusted emergency: no finally, no seal
        emergency_pending = True                           # inside COMMITTING: defer to next bytecode
```

**First signal — graceful sealed abort:**

| State on signal #1 | Behavior |
| :--- | :--- |
| `PRE-FLIGHT` | abandon before staging: no artifacts → **T1**, exit 130/143 |
| `RUNNING` | set `stop_requested` → `STOPPING` |
| `STOPPING` / `SEALING` / `VERIFYING` / `COMMITTING` / `COMMITTED` | idempotent: current phase runs to completion; the commit is never interrupted |

**Check points for `stop_requested` (exact):** (1) inside every wait — live sleeps are sliced at ≤ **100 ms**, each slice re-reading the monotonic clock *and* the flag (PEP 475 would otherwise resume a long sleep and delay the flag to its natural end; slicing never breaks never-early because each slice re-tests `now ≥ start_at`); (2) **before the commit read** — a not-yet-committed request is never started; (3) between requests, groups, boundaries and plan steps.

**Drain rule (exact):** an in-flight request **always finishes** (bounded by 17 s + 1 s grace) and is **never cancelled to stop faster** — a mid-request cancel would produce a `DEADLINE` record with duration < 17 s, failing audit (e) and converting a clean operator stop into a quarantined run. Afterwards: append `TIMELINE_END` → `pacer.abort("OPERATOR-SIGINT"/"OPERATOR-SIGTERM")` (sets `abort_seq = len(records)`, matching audit (a)'s derived-`None` rule and the trailing-justification rule) → seal → verify → receipt → exit.

**Second signal:** immediate `os._exit(130/143)` from `PRE-FLIGHT` (no staging → T1), `RUNNING`/`STOPPING` (staging debris → T2), `SEALING`/`VERIFYING` (staging debris → T2); inside `COMMITTING` it is deferred per §2.1.1 (lands T2/T4/T6-or-T5 at a bytecode boundary, never mid-syscall). Deferral never spans a seal step; the `COMMIT_BOUND_NS = 5 s` soft bound on the critical section means the deferred exit executes at the first opportunity once the syscalls return — and if a syscall never returns, §2.1.1's honest EXEC-FAILURE classification applies instead of a false claim.

**Exit codes (authoritative function lives in §5.3):** `0` = invariant S holds; `1` = sealed but S false (incident/operator/plan-incomplete); `2` = refused, quarantined, or receipt-failed (nothing trustworthy published — or, for T4-by-failure, a run dir awaiting recovery); `130`/`143` = SIGINT/SIGTERM termination.

### 4.2 Incident Matrices — Full Rows [R11]

Categories as defined in v1.1: **N** = Network & Transport, **T** = Timing & Clock, **P** = Pacing & Admission, **E** = Execution & Environment. Terminal states reference §5.3; "non-terminal" rows continue the run unless stated. Every row is self-contained: no row defers its analysis to another row.

#### N1–N14 — Network & Transport

| ID | Condition | Detection & countermeasure | Record / audit effect | Terminal state |
| :--- | :--- | :--- | :--- | :--- |
| **N1** | DNS resolution fails, times out (5 s), returns no addresses, or the resolver child is unkillable (§3.1) | `communicate(timeout=RESOLVE_TIMEOUT_S)` → `TimeoutExpired` → `kill()` + `wait(REAPER_GRACE_S)`; non-zero exit / empty JSON → same refusal | no records exist; no egress ever; no seal attempted | **T0**, exit 2 — `cause: DNS-UNRESOLVED`, explicitly an unsealed untrusted execution failure, not a session result. Mid-run DNS is impossible: the address is pinned (§3.1) |
| **N2** | TCP connect refused by pinned address:443 | worker raises `ConnectionRefusedError` → classified `CONNECT_ERROR` | `status=None`, `error=CONNECT_ERROR`, duration ≤ 5 s; no-response streak +1; audit (a): derived `None` (streak < 3) or seq (= 3) | single → run continues; **3 consecutive → `abort("INCIDENT-NETWORK")` → T5**, exit 1 |
| **N3** | TCP connect timeout against a blackholed pinned IP (`CONNECT_TIMEOUT_S = 5.0`) | `socket.timeout`/`TimeoutError` in connect → outcome `TIMEOUT` (transport maps timeout types to TIMEOUT) | `error=TIMEOUT`, `status=None`, duration ≤ 18 s (audit (e) ✓); streak +1 | as N2 → run-ending case **T5**, exit 1 |
| **N4** | TLS handshake failure (protocol/cipher/cert mismatch against `server_hostname`) | `ssl.SSLError`/`CertificateError` in worker → `CONNECT_ERROR`; connection closed | `error=CONNECT_ERROR`, `status=None`; streak +1 | as N2 → **T5**, exit 1 |
| **N5** | mid-body disconnect (`RemoteDisconnected`/`BrokenPipeError`/EOF before Content-Length) | read path raises → `CONNECT_ERROR`; partial bytes discarded (never retained as a body) | `status=None`; streak +1 | 3 consecutive → **T5**, exit 1 |
| **N6** | stalled read (`READ_TIMEOUT_S = 12.0`) or stuck write (`SEND_TIMEOUT_S = 0.25`) | socket timeout in read/write → `TIMEOUT`; `cancel()` also unblocks writes instantly | `error=TIMEOUT`; duration ≤ 18 s (audit (e) ✓) | run-ending case → **T5**, exit 1 |
| **N7** | total request time reaches `DEADLINE_NS = 17.0 s` from `start_ns` | inline `_wait_until` on the pacing thread (no watchdog thread) → `state.cancel()` → `socket.shutdown(SHUT_RDWR)` + close; 1 s grace → `CancellationFailed` → transport disabled → pacer appends record + `abort("INCIDENT-CANCEL")` | `error=DEADLINE` (duration ∈ [17 s, 18 s]) or `CANCEL_FAILED` (duration ∈ [17 s, 19 s]) — audit (e) ✓; `abort_seq` = record seq = derived ✓ | seal → **T5**, exit 1 |
| **N8** | HTTP status ≠ 200 (403 / 418 / 429 / any 3xx / any 5xx) | transport latches `disable("HTTP-{status}")` permanently; pacer aborts with the same reason → `NonOkResponse` | record carries `status`, `error=None`; derived = seq = `abort_seq` ✓ audit (a); egress counter cross-check (g) | **T5**, exit 1; 418/429 additionally write the cooldown file → the *next* run refuses at pre-flight (**T0**) until expiry |
| **N9** | declared `Content-Length` > 4 MiB or non-integer | header pre-check closes the connection **before buffering a byte** → new outcome `BODY-LIMIT` | `status=None`, `error=BODY-LIMIT` (free-form error string; `_req_str` parser and audit accept it), duration ≤ 18 s; immediate `abort("INCIDENT-MEMORY")`, `abort_seq = len(records)` ✓ | **T5**, exit 1 — sealed `ABORT (INCIDENT-MEMORY)` |
| **N10** | streamed body exceeds 4 MiB despite header (chunked or lying header) | chunk loop hits `MAX_BODY_BYTES + 1` or the aggregate check (§3.2) → `BODY-LIMIT`, connection closed | as N9 | **T5**, exit 1 |
| **N11** | 3xx redirect with `Location` header | status ≠ 200; no redirect-following code exists (`auto_open = 0`, exactly one request per record) | record with `status=3xx`; derived abort = its seq; transport disabled | **T5**, exit 1 |
| **N12** | `X-MBX-USED-WEIGHT-1M` > 600, or non-integer / unparseable | runner parses whitelisted headers right after append: strict integer parse; unparseable **counts as a violation** (under-limit cannot be proven) | the record itself is a clean 200 → derived `None`, `abort_seq = len(records)` ✓ audit (a) | **T5**, exit 1, abort reason `INCIDENT-WEIGHT` → protocol `ABORT (INCIDENT)` [DECISION R6: subcode naming] |
| **N13** | 200 but non-JSON body / wrong shape / wrong host or path / kline row open time ≠ boundary | strict parse immediately after append, before the next dispatch → incident | record ends the run (`abort_seq = len(records)`); raw bytes retained in `body_b64` → digest-bound | **T5**, exit 1 — `ABORT (INCIDENT)` |
| **N14** | non-allow-listed spec reaches dispatch: path outside `/api/v3/`, HOST mismatch, credentials, proxy env, socket constructed outside the transport, second connection factory | `validate_spec` raises `UnsafeRequest` **before any socket**; at plan build this refuses the run; mid-run (harness defect) the run boundary seals records so far with `UNSAFE-SPEC` | pre-flight: no records; mid-run: existing records seal audit-consistently | pre-flight → **T0**, exit 2; mid-run → **T5**, exit 1 |

#### T1–T9 — Timing & Clock

| ID | Condition | Detection & countermeasure | Record / audit effect | Terminal state |
| :--- | :--- | :--- | :--- | :--- |
| **T1** | monotonic regression (`end < start`, or `now < last.end`) | assertion at the read **before** append — the bad record is never created; existing records seal with abort `CLOCK-INVARIANT` | if caught at runtime, only clean records persist → audit passes; if discovered only offline on an already-persisted record, audit (b)/(c) reject it | runtime → **T5**, exit 1; offline → **T3**, exit 2 |
| **T2** | wall-clock jump (NTP step, `settimeofday`, DST) | the wall clock is never read in the run path (structural test); index wall fields are labeled diagnostic | zero effect on records or audit — the value is never an input | **non-terminal by construction**; cannot cause a state transition |
| **T3** | system suspend/resume (monotonic jumps forward) | estimator intersection empties at the next admission → `SyncInadequate` → per-boundary `SYNC-SKIPPED` ladder with DECISION events recorded | each skip is audit-legal (check (f)); a run of 3 consecutive skips is protocol-terminal for coverage, not for the runner | run seals → **T6**, exit 0 (session verdict `INCONCLUSIVE-TIMING` is analysis-side); if a skip cannot be recorded, seal fails → §4.3 mapping |
| **T4** | NTP slew / clock-rate change beyond `DELTA = 10⁻⁴` | Θ widens; `width > W_MAX_NS = 250 ms` → inadequate → up to 4 extra `/time` samples under the issuance guard `now + 17 s + 1 s < D(T − 10 s)`; still inadequate → `SYNC-SKIPPED` ladder | as T3 | **T6**, exit 0 (offline V2/V3 verdicts are analysis-side and do not alter the runner's terminal state) |
| **T5** | spurious wake-up / EINTR interrupts the sleep | the loop re-reads the clock on every wake; exit only when the predicate holds on that read | none — early start is structurally impossible | **non-terminal** |
| **T6** | oversleep / timer coalescing / GIL stall before a start | lateness computed in-loop from values already read (`now − start_at` at commit, no extra clock read) | all pacing rules are lower bounds → a late start is legal; `> 500 ms` recorded in `index.wake_lateness` | **non-terminal** (V1 judges window validity offline) |
| **T7** | deadline D moves later between wakes (fixed-point drift) | `target_fn(now)` re-evaluated each wake on the single read; commit guarded pre-dispatch by `assert start_ns ≥ target_fn(start_ns)` (pure, no clock read) | a violation aborts **before dispatch** — the invalid record is never created; prior records seal | guard holds by construction (GV-6/7 CI gates); if it ever trips → **T5**, exit 1 |
| **T8** | deadline already elapsed when `send` is entered | unreachable: `start_ns` and `deadline_at_ns = start_ns + 17 s` are produced and consumed with no intervening read (~17 s margin); transport's `remaining_ns ≤ 0` check retained | if observed: a zero-duration `DEADLINE` record fails audit (e) (`DEADLINE_NS ≤ duration`) | **T3**, exit 2 — cause class `EXEC-FAILURE` bug |
| **T9** | `SyncInadequate` raised inside the commit loop (no estimate at that instant) | caught pre-dispatch → re-run `decide_admission`; still inadequate → record DECISION with `MISSED-WINDOW` and return without dispatch | audit-legal skip (check (f)); nothing sent | **non-terminal** — run continues |

#### P1–P8 — Pacing & Admission

| ID | Condition | Detection & countermeasure | Record / audit effect | Terminal state |
| :--- | :--- | :--- | :--- | :--- |
| **P1** | computed start would violate PACE-1 (start before `last.end`) or leave `earliest` (early start) | pre-dispatch assertion `start_ns ≥ earliest_start_ns()` — a records-only recompute with no clock read; the single-read loop makes a violation structurally impossible | invalid record never created; prior records seal | runtime trip → **T5**, exit 1; offline discovery → audit (b) fails → **T3**, exit 2 |
| **P2** | spacing violation (gap < `SPACING_NS` = 600 ms; OBS-01 2 s) | same pre-dispatch assertion (`earliest` includes `last.start + spacing`); audit (c) recounts offline with the exact 599,999,999-fails / 600,000,000-passes boundary | as P1 | runtime → **T5**, exit 1; offline → **T3**, exit 2 |
| **P3** | rolling-cap violation (either window count would exceed its cap) | pre-dispatch assertion `window_count(starts, start_at, W) ≤ cap` for every window; audit (d) recounts with the shared formula plus the independent GV-8 re-derivation | as P1 | runtime → **T5**, exit 1; offline → **T3**, exit 2 |
| **P4** | PACE-7 admission decision inconsistent with its recorded inputs (`m_e + θ_lo ≤ T + o + tol` recorded as skip, or the converse) | decision computed from single-read inputs; offline `validate_decision_evidence` / `validate_missed_window_decision` recompute exactly | records and DECISION events are immutable; the mismatch is discoverable only offline | **T3**, exit 2 (audit (f) fails) |
| **P5** | boundary admitted but the start would fall after window end, with no recorded `MISSED-WINDOW` decision | live path records the skip when `earliest > window_end_ns` at commit (§1.2); audit (f) requires a recorded justification for every non-dispatched boundary | a missing decision fails audit (f) | recorded skip → **non-terminal**; missing → **T3**, exit 2 |
| **P6** | duplicate dispatch of the same boundary / group (replay) | the plan tracks dispatched boundaries; a second attempt raises pre-dispatch (harness invariant); offline expected-boundary counts must match DECISION counts exactly | pre-dispatch: nothing sent; if persisted, audit (f) count mismatch fails | runtime guard → **T5**, exit 1; offline → **T3**, exit 2 |
| **P7** | concurrent / re-entrant `execute` (single-flight violation) | non-blocking single-flight lock; a second entrant raises `ConcurrentExecution` — nothing sent, nothing recorded; the §1.1 inventory makes it impossible in production | no record; the run boundary seals existing records with abort `CONCURRENT-EXEC` | production trip → **T5**, exit 1; test-only detection → no state change |
| **P8** | plan parameters inconsistent with the protocol profile (spacing/window/cap/drift constants) or pre-registration file mismatch | fail-closed pre-flight validation of the plan against profile constants and the prereg file — before staging, before resolution, before egress | no records exist | **T0**, exit 2 |

#### E1–E12 — Execution & Environment

| ID | Condition | Detection & countermeasure | Record / audit effect | Terminal state |
| :--- | :--- | :--- | :--- | :--- |
| **E1** | first SIGINT while `RUNNING` | handler flag checked at ≤ 100 ms slices, pre-commit, between steps → STOPPING: drain in-flight (never cancel), `TIMELINE_END`, `abort("OPERATOR-SIGINT")` | audit (a) ✓ (derived `None` → `abort_seq == len(records)`), trailing rule ✓ | **T5**, exit 130; if the plan was already terminal and S otherwise holds → **T6**, exit 0 with `signal_observed`; in PRE-FLIGHT → **T1**, exit 130 |
| **E2** | first SIGTERM while `RUNNING` | identical to E1 | identical | **T5**, exit 143 (T1 in PRE-FLIGHT) |
| **E3** | second SIGINT/SIGTERM before `COMMITTING` | `os._exit(130/143)` from the handler — no `finally`, no seal | artifacts exactly as they stand (see §4.3) | no staging → **T1**; staging exists → **T2**; exit 130/143 |
| **E4** | second SIGINT/SIGTERM during `COMMITTING` | deferred to the next bytecode boundary (never mid-syscall); lands per §2.1.1; if a syscall hangs past `COMMIT_BOUND_NS`, the handler cannot run → EXEC-FAILURE residual | per §2.1.1 landing table | pre-rename → **T2**; post-rename → **T4**; post-index → **T6**/**T5**; exit 130/143 (or post-mortem `observe()` after a hang) |
| **E5** | aggregate retained bytes would exceed `SESSION_BODY_BUDGET_BYTES` = 50 MiB during streaming | chunk-level check `retained_total + len(chunk) > 50 MiB` **before** appending (§3.2) → close → `BODY-LIMIT` → `abort("INCIDENT-MEMORY")` | record with `error=BODY-LIMIT` (or, on a pre-dispatch trip, none — last record stays clean); `abort_seq = len(records)` ✓ | **T5**, exit 1 — sealed `ABORT (INCIDENT-MEMORY)` |
| **E6** | single response body exceeds `MAX_BODY_BYTES` = 4 MiB | header pre-check (pre-buffer) or the `MAX_BODY_BYTES + 1` chunk cap → `BODY-LIMIT` → immediate abort | as N9 | **T5**, exit 1 |
| **E7** | response headers exceed `MAX_HEADER_BYTES` = 64 KiB (header bomb) | bounded header reader accumulates line lengths; past the cap → close → `HEADER-LIMIT` (same handling class as `BODY-LIMIT`) → `abort("INCIDENT-MEMORY")` | `status=None`, `error=HEADER-LIMIT`; duration ≤ 18 s ✓ audit (e) | **T5**, exit 1 |
| **E8** | a second harness process attempts to start while the run lock is held | `flock(LOCK_EX | LOCK_NB)` on `data/.obs_run.lock` fails at pre-flight → refuse before resolution, staging or egress | no records | **T0**, exit 2 |
| **E9** | staging or run-dir path occupied at publication (dir, file, symlink, dangling symlink) or the runs root resolves through unexpected symlinks | §2.1: `lexists` + `renameat2(RENAME_NOREPLACE)` + `(st_dev, st_ino)` identity + `realpath` pin → `CollisionIncident`; staging retained as debris | nothing published; no partial run directory | **T2**, exit 2 |
| **E10** | `ENOSPC` / `EIO` / `EDQUOT` at any write, fsync or rename | `OSError` caught by the run boundary: incomplete staging → abandoned debris; complete staging but failed rename → debris; report `SEAL-FAILED` | no run directory (quarantine applies only to verified-then-rejected artifacts, §2.3) | **T2**, exit 2 |
| **E11** | banned primitive detected (`threading.Timer`, `asyncio`, `Event.wait` pacer, wall-clock read in the run path, `sys.exit` below `main`, second connection factory, in-process `getaddrinfo`) | structural repo tests (dev gate) plus the runtime registry check at pre-flight | no records — refused before staging | **T0**, exit 2 (gate failures block any `--live` cut) |
| **E12** | orphaned worker after the cancel grace expires (`CancellationFailed`) | transport disabled + shared cancel state; the run boundary seals, `main` returns, and process exit reaps the daemon worker — **thread termination is never claimed**; if the worker is stuck unkillable and the process cannot exit, cause = `EXEC-FAILURE` | sealed artifacts already exist (the seal precedes the exit attempt) | normal → **T5**, exit 1; process cannot exit → eventual state by `observe()` (**T5**/**T4** by artifact presence), reported as EXEC-FAILURE (R1 honesty rule) |

### 4.3 Crash Persistence Matrix K0–K12 (full rows) [R11]

The namespace is the `runs/…` directory; staging, spool and quarantine are distinct paths, and only `publish_dir()` creates a run directory. Each row gives the on-disk state at the crash and the state `observe()` (§5.3) resolves.

| ID | Crash point | State on disk | Run namespace | Terminal state |
| :--- | :--- | :--- | :--- | :--- |
| **K0** | during RUNNING, before staging exists | memory + `.partial/spool.jsonl` only | empty | **T2** (exit null; spool is forensics, not evidence) |
| **K1** | after staging `os.mkdir`, before any file | empty staging directory | empty | **T2** |
| **K2** | after `records.jsonl` fsync, before events | staging + records file | empty | **T2** |
| **K3** | after `events.jsonl` fsync, before manifest | staging + two files | empty | **T2** |
| **K4** | during `manifest.json` write (torn manifest) | staging + two files + torn manifest | empty | **T2** (never read: only renames make runs) |
| **K5** | after manifest fsync, before staging-dir fsync | complete triple, directory durability pending | empty | **T2** |
| **K6** | after staging-dir fsync, before verification | complete, loadable staging | empty | **T2** (loadable ≠ published) |
| **K7** | during verification/audit, or after the FAIL verdict but before the quarantine rename was initiated | complete staging (rejection unpublished) | empty | **T2** — debris, **not** quarantine: quarantine requires a published rejection (§2.3 rule 1) |
| **K8** | after the quarantine rename, before the quarantine index write | `<attempt>.unverified/` complete | quarantine present | **T3**; index recovered by `obs-index finalize --quarantine` (audit failures re-derived) |
| **K9** | after the run-dir rename, before parent fsync | live: run directory visible and complete, durability pending | run dir (or, after power loss, wholly absent) | system survives → **T4**; power lost → entry vanishes wholly → **T2**; **never partial** — resolved by `observe()` at the next inspection |
| **K10** | after parent fsync, before index (receipt) fsync | durable, verified run directory; no receipt | run dir | **T4**; recovery `obs-index finalize` → **T6** (S then true) or **T5**, with `receipt: "recovered"` |
| **K11** | after index fsync, before process exit | full commit: run directory + receipt | run dir | **T6** (S true) or **T5** (S false); exit code null (no exit executed); no repair needed |
| **K12** | `ENOSPC`/`EIO` caught at any write step (contrast K0–K7: uncaught death) | partial staging | empty | **T2**, exit 2 |

---

## 5. Provenance & Success Invariants

### 5.1 Outer Evidence Index (`obs-outer-index/1`) [AR-11]

- **Frozen schema untouched:** `obs-run-manifest/1` keeps its exact eight keys — `format`, `record_count`, `records_file_sha256`, `records_digest`, `event_count`, `events_file_sha256`, `event_log_head`, `manifest_digest`. v1.2 adds durability plumbing only (fsync/rename discipline, §2.1); no field is added, no format string is bumped, the strict key-set validator and every authenticated digest keep their current semantics, and the run directory still contains **exactly three files**.
- **Path:** `runs/<session>/<attempt>.index.json` — a sibling of the run directory, never inside it, never an input to any audit decision.
- **Fields (`obs-outer-index/1`):** `session_id`, `attempt_id`, `run_dir`, `manifest_sha256` (the pin), `receipt` (`fresh` | `recovered` | `none`), `plan_sha256`, `profile` {name, spacing_ns, windows}, `git_commit`, `git_dirty`, `python` {version, implementation}, `platform`, `hostname`, `started_utc`, `ended_utc` (wall clock — diagnostic per protocol §2), `start_monotonic_ns`, `end_monotonic_ns`, `terminal_state` (T0–T6 name), `exit_code`, `cause` (e.g. `DNS-UNRESOLVED`, `INCIDENT-NETWORK`, `OPERATOR-SIGINT`, `SEAL-FAILED`, `EXEC-FAILURE`), `incident` (null or {code, seq}), `plan_status`, `wrapper_count`, `record_count`, `transport_disabled_reason` (null for success), `handoff` {max_queue_lag_ns, max_setup_lag_ns, warn_flags} (R2), `wake_lateness` {max_ns, over_500ms_count}, `audit_failures` (for T3), `quarantine_path`, `stdout_log` + sha256, `stderr_log` + sha256, `spool_path`, `writer_version`.
- **Trust statement:** the index is provenance, not evidence. Its integrity rests on the pin it carries (recorded out of band — captured log line and reviewer receipt); wall-clock values are explicitly diagnostic. Losing the index costs context, never validity; it is never repaired by inference — recovery *re-derives* every field from the artifacts (§5.2).

### 5.2 Receipt Publication and the `SEALED-UNRECEIPTED` Gap [R8]

**Definition (normative):** `RECEIPT := the outer index file, written and fsynced, containing the pin`. The stdout pin line is a **best-effort mirror only** — stdout may be a pipe and is not durably ours — and is explicitly **not** part of S.

**Ordering:** rename → parent fsync (publish durable) → index write + fsync (receipt) → `COMMITTED` → exit. Two consequences:

- **"Pinned-but-unsealed" is unreachable:** the index is written only after the parent fsync returns, so a receipt can never exist without its run directory. (A crash-time anomaly — an index whose run directory is later found missing — is flagged `orphan_index` by `observe()` and never creates a state.)
- **The gap is real and now named:** no single syscall commits a directory entry and a sibling file, so death between the two fsyncs leaves a verified, durable run directory with no receipt. That is terminal state **T4 `SEALED-UNRECEIPTED`**: S is **false at death**, deterministically, and detectably (index absent).

**Recovery (deterministic, idempotent):** `obs-index finalize <run_dir>` recomputes `pin = sha256(manifest bytes)` from the published artifacts, re-runs `load_run` **and** `audit_run` over them, writes the index with `receipt: "recovered"` plus the re-derived fields, and `observe()` then resolves the attempt to **T6** (all conjuncts hold) or **T5** (plan incomplete / egress dirty). Recovery never trusts crash-time memory.

**Live-path receipt failure:** if the index write fails with `OSError` on the normal path, the attempt **cannot exit 0**: report `RECEIPT-FAILED`, exit **2**, state **T4** — the verified run directory is retained for recovery and is **never quarantined** (quarantine is exclusively for failed verification, §2.3).

### 5.3 Exhaustive Terminal States, Invariant M and Predicate S [R12]

**Terminal state set — every process trace ends in exactly one of T0–T6:**

| State | Artifact signature (per attempt) | Receipt | S | Exit | Canonical causes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **T0 `REFUSED`** | nothing | none | false | **2** | pre-flight refusal: plan/profile mismatch (P8), lock held (E8), cooldown/prereg (A12), DNS unresolved (N1), banned primitive (E11), `UnsafeRequest` at plan build (N14) |
| **T1 `SIGNAL-ABANDONED`** | nothing | none | false | **130 / 143** | first signal in PRE-FLIGHT; second signal before staging |
| **T2 `DIED-UNSEALED`** | no run dir, no quarantine (staging/spool debris may or may not exist) | none | false | **130/143** (emergency) · **2** (caught failure) · **null** (SIGKILL/power) | crashes K0–K7, K12; emergency landing pre-rename (E3/E4); collision (E9); ENOSPC (E10); `EXEC-FAILURE` where the process never completed classification (hung fsync §2.1.1, unkillable worker E12, in-process DNS observed) |
| **T3 `QUARANTINED`** | `<attempt>.unverified/` | optional (recoverable) | false | **2** | verification/audit rejection (§2.2); offline-detected record violations (T1/P1–P4/P6 offline); T8-class audit failure |
| **T4 `SEALED-UNRECEIPTED`** | run directory (verified at publication) | **missing at observation** | false | **null** (kill/power) · **130/143** (emergency landing post-rename) · **2** (live `RECEIPT-FAILED`) | K9, K10; E4 landing post-rename; index write failure; recovery → T6 or T5 |
| **T5 `SEALED-ABORTED`** | run directory + receipt | present | false (`EGRESS_CLEAN` or `PLAN_TERMINAL` fails) | **1** | incidents N2–N14, operator stop E1/E2, memory E5–E7, runtime guards T7/P1–P3/P6/P7, clock invariant T1-runtime |
| **T6 `SEALED-SUCCESS`** | run directory + receipt | present | **true** | **0** | complete, verified, audited, egress-clean, plan-terminal run |

**`observe()` — the total resolver** (used by recovery tooling and post-mortem; artifact precedence is strict):

```python
def observe(fs, exit_code, refusal_journal) -> TerminalState:
    if fs.run_dir_exists():                       # precedence 1
        if fs.index_fsynced() and re_verify(fs.run_dir):          # pin re-derived, audit re-run
            return T6 if (plan_terminal and egress_clean) else T5
        return T4                                # durable run dir, no receipt
    if fs.quarantine_exists():                   # precedence 2
        return T3
    if fs.staging_exists() or fs.spool_exists(): # precedence 3
        return T2
    # empty filesystem — cause disambiguates:
    if exit_code in (130, 143):            return T1      # deliberate pre-staging abandon
    if exit_code == 2 and refusal_journal:  return T0      # classified refusal
    return T2                                   # died before any classification
```

At most one of {run directory, quarantine, staging} can exist per attempt — `publish_dir()` renames staging away in both directions, and attempt ids are unique — so the artifact classes are **mutually exclusive by construction**.

**Cause → state table (exhaustive partition):**

| # | Cause class | State |
| :--- | :--- | :--- |
| 1 | pre-flight refusal of any kind (config, lock, cooldown, DNS, banned primitive, spec) | T0 |
| 2 | signal abandon while no staging exists | T1 |
| 3 | death or forced exit before the publish rename; publish collision; caught seal I/O failure; `EXEC-FAILURE` (hung syscall, unkillable worker, in-process DNS observed) | T2 |
| 4 | verification or audit rejection (published quarantine) | T3 |
| 5 | death after rename without a durable receipt; live receipt failure | T4 |
| 6 | committed + receipted, but `EGRESS_CLEAN` or `PLAN_TERMINAL` fails | T5 |
| 7 | committed + receipted + all six conjuncts | T6 |

Every cause the runner can exhibit — crash at any K point, first/second signal in any state, incident from any N/T/P/E row, seal failure, receipt failure — appears in exactly one row; no cause is unlisted and no cause maps to two states. Consequently every trace terminates in exactly one state (**totality**), which is R12's requirement.

**S conjunct → state table** (the state each conjunct fails into when the others hold; `observe()` over artifacts is authoritative when several fail at once):

| Conjunct | Enforcement point | Fails → |
| :--- | :--- | :--- |
| `VERIFIED` | §2.2 step (i), `load_run` + element-wise equality, before rename | **T3** (quarantine) |
| `AUDITED` | §2.2 step (ii), `audit_run` over persisted artifacts, before rename | **T3** (quarantine) |
| `COMMITTED` | rename + parent fsync (§2.1 steps 5) | death before → **T2**; fsync durability lost → **T4** or **T2** (by presence) |
| `RECEIPT` | index fsync (§5.2) | **T4** |
| `EGRESS_CLEAN` | `transport.disabled_reason is None`, `transport.sent == record_count`, no orphan worker / `ConcurrentExecution` / `UnsafeRequest` event | **T5** |
| `PLAN_TERMINAL` | every plan step executed, verified-skip, or protocol-terminal stop | **T5** |

**Predicate S and invariant M, final:**

```
S  ⇔  state = T6  ⇔  COMMITTED ∧ RECEIPT(outer index fsynced) ∧ VERIFIED ∧ AUDITED ∧ EGRESS_CLEAN ∧ PLAN_TERMINAL
M  ⇔  every attempt terminates in exactly one of T0…T6;
       the run directory exists ⟺ state ∈ {T4, T5, T6};
       every run directory was verified and audited before publication (never partial, never unverified);
       the quarantine directory exists ⟺ state = T3
```

**Exit-code function:** `exit(T6) = 0`; `exit(T5) = 1`; `exit(T0) = exit(T3) = 2`; `exit(T1) = exit(T2-by-signal) = 130/143`; `exit(T2-by-failure) = 2`; `exit(T4-by-kill) = null`, `exit(T4-by-signal) = 130/143`, `exit(T4-RECEIPT-FAILED) = 2`. The exit code is therefore a pure function of (state, cause); `null` covers only uncatchable death (SIGKILL, power), which `observe()` still resolves to a single state.

**Scope note:** terminal states describe the *runner process and its artifacts*. Offline V-series verdicts (`TIMING-INVALID`, `COMPLETE-VALID`, …) are a separate analysis layer and never rewrite a terminal state; conversely no runner state claims a session-level verdict it does not own.

---

## 6. Verification Gates & Open Decisions

### 6.1 Gates — one per R (all must pass before any `--live` cut)

- **G-R1 (DNS):** resolver child that sleeps 60 s → parent kills within `RESOLVE_TIMEOUT_S + REAPER_GRACE_S`, refuses, exit 2, zero artifacts, zero sockets opened; unkillable-child drill (simulated) → same refusal with the "not terminated" note; structural grep `getaddrinfo` confined to `_resolve.py`; connects asserted to carry an IP literal while SNI/`Host` keep the hostname.
- **G-R2 (handoff):** import-graph/grep test that no pacing or audit module reads `wire_ns`/`dispatch_ns`; `queue_lag`/`setup_lag` populated in the index; `HANDOFF_WARN_NS` tripped by an injected artificial delay produces a warning, not a reclassification.
- **G-R3 (loop):** the GV-6 and GV-7 oracle blocks of §1.2 verbatim, including both tripwires (double read → raise; committed ≠ admitted → raise), plus the closed-form cross-check.
- **G-R4 (release):** GV-8 (i)–(iv) through the pacer functions, a live-loop dry run, and the independent audit recount; the OBS-01 exact-tie vector (all three components = `60,000,000,000`) asserted.
- **G-R5/R6 (memory):** injected `retained_total` near budget → trip on the exact chunk that crosses 50 MiB; exactly-4 MiB EOF accepted; header bomb → `HEADER-LIMIT`; `tracemalloc` peak ≤ Domain B cap; no-decompress grep; offline expansion-cap test with a synthetic bomb.
- **G-R7 (no-replace):** pre-created empty target → publication must fail (would pass with plain `rename`); symlink at run-dir name → fail; `(st_dev, st_ino)` swap between staging creation and rename → fail; two processes racing under `flock` → exactly one wins.
- **G-R8 (receipt):** kill between parent fsync and index fsync → `observe() == T4` → `obs-index finalize` → T6/T5 with `receipt: "recovered"`; injected index-write failure → exit 2, run dir retained, never quarantined.
- **G-R9 (quarantine):** injected audit failure → atomic quarantine publication; kill windows K7 (→ T2) and K8 (→ T3) asserted; quarantine index recovery path.
- **G-R10 (emergency):** inject a second signal at each COMMITTING boundary → assert the §2.1.1 landing table; a reader concurrently opening the run directory at every step observes a complete, consistent triple.
- **G-R11 (matrices):** traceability — every row of N1–N14, T1–T9, P1–P8, E1–E12, K0–K12 maps to a named test or structural check; no row is paper-only.
- **G-R12 (exhaustiveness):** enumerate all artifact configurations × cause classes and assert `observe()` returns exactly one state each, matching §4.3 and the cause table; crash-injection at K0–K12 asserts the documented state.

Existing batteries remain authoritative throughout: `test_pacer.py`, `test_audit.py`, `test_watchdog_transport.py`, `test_provenance.py`, `test_run_manifest_e2e.py`, `test_manifest_trust_and_types.py`, `test_snapshot_failure.py`, `test_estimator.py` (GV-1…GV-7), `test_admission.py`, `test_specs.py`, `test_harness_safety.py`.

### 6.2 Open decisions for the reviewer

1. **D1 (R1):** resolver-subprocess isolation adopted as mandatory mechanism, with `_resolve.py` + pinned-address connects. Confirm the protocol accepts that DNS is a pre-flight concern only (no mid-run resolution by design).
2. **D2 (R2):** logical dispatch timestamp semantics as normative, the single observational worker read, and the warn thresholds `HANDOFF_WARN_NS = 1 ms` / `WIRE_JITTER_WARN_NS = 50 ms` (warn-only, never state-changing).
3. **D3 (R5/R6):** new transport outcomes `BODY-LIMIT` and `HEADER-LIMIT` (free-form `error` strings — confirmed parser/audit-safe since records validate `error` as a plain string), and `INCIDENT-MEMORY` as an abort class not enumerated in protocol §6's incident table — needs protocol footnote or explicit acceptance. Carried: the 4-extra-sample ceiling and issuance guard (old OQ4), and no-fallback host policy (old OQ3).
4. **D4 (R8):** `RECEIPT := fsynced outer index`, stdout pin demoted to mirror, and the `obs-index finalize` recovery tool (name and behavior).
5. **D5 (R7):** `renameat2(RENAME_NOREPLACE)` primary with the flock + `lexists` + inode-verify fallback on non-Linux platforms.
6. **D6 (R12):** collapsing all pre-flight refusals (DNS, lock, config, spec) into exit 2 / T0 with `cause` distinguishing them in the index.
7. **D7 (carried naming):** `INCIDENT-CANCEL` (protocol: accept?), `INCIDENT-WEIGHT` subcode mapping to protocol `ABORT (INCIDENT)`, and `MAX_EXPANSION_RATIO = 1000:1` for offline decompression.