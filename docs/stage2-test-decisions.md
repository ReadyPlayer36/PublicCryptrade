# Stage 2 test-design decisions (tests-only revision)

This document records acceptance-test decisions only. It does not authorize production implementation or alter the frozen v2.9 matrix.

- **Determinism:** constructors will accept injected `sleep`, `jitter`, `now_ms`, and `http_client`; tests will not monkeypatch global time/sleep functions.
- **Sleep budget:** abort before sleeping when `total_slept + next_wait > 30`; exactly 30 seconds is allowed.
- **Timeouts:** `ConnectError` and `ConnectTimeout` are connect failures and may trigger host fallback only before the first successful server-time call. `ReadTimeout`, `WriteTimeout`, and `PoolTimeout` retry on the same host.
- **Cooldown file:** JSON shape is `{"until_ms": int, "reason": str}` and is global across allowed hosts. An active cooldown blocks all network I/O, including the time endpoint. Missing, corrupt, non-integer, or negative values fail closed.
- **Finality:** the client sends `endTime = effective_end - 1`. If upstream still returns any candle with `close_time_ms >= B`, abort; never silently drop it. The independent vectors live under `tests/fixtures/vectors/`.
- **Conflict comparison:** numeric `Decimal` equality for prices, base volume, and quote volume; integer equality for close time and trade count.
- **Exception contracts:** `EmptyEffectiveRangeError` for an effective end not greater than requested start; `NaiveDatetimeError` for naive input datetimes; `NonFinalCandleError` when upstream returns a non-final candle; `CorruptCooldownError` for invalid cooldown persistence. Tests assert type and diagnostic message.
- **Red-reason gate:** a failure is an expected red only when JUnit traceback includes `NotImplementedError` raised from `src/trading_app/`. Test-body placeholders, assertion failures, skips, collection errors, and unexpected passes are rejected. Passing tooling/CI/hygiene rows are explicitly allowlisted in `tools/red_reason_gate.py`.
- **Provenance:** the public baseline `a88a843` has tree `408a6a42…`; the local bundle's original commit identity is `de1bd38…` and is not present in public history. The revised commit message records that gap. Any push of original history is a separate, optional branch operation.

Any test expectation that conflicts with `matrix.yaml` requires a new spec version and reviewer sign-off; no frozen matrix or frozen tooling file is changed by this revision.

## Stage B2 decisions (client request engine)
- `cooldown_path=None` keeps cooldown in memory per client; production wiring must pass `data/binance_cooldown.json` so cooldown is global across processes.
- `now_ms` is used only for cooldown timestamps; finality never reads the local clock (server time or abort).
- Sleep budget (30s) and host lock are per fetch; the fetch owner calls `begin_fetch()`. `get_server_time` alone does not reset them.
- Connect/DNS failure before the first successful `/api/v3/time` switches once to the fallback host (counts as an attempt, no sleep). Afterwards connect failures are ordinary retryable transient errors on the locked host.
- Unparsable or non-integer `Retry-After` is treated as absent (exponential backoff). Only integer seconds are honored.
- A 429 whose backoff (no `Retry-After`) would exceed the sleep budget trips the budget cooldown (600s minimum). Non-429 retryable errors that would exceed the budget abort without cooldown.
- Out-of-range injected jitter is a programming error (`ValueError`), never silently clamped.
- Unknown transport errors (e.g. `ReadError`) are not retried.
- Two Stage-2 tests were defective and corrected in Stage B2: `test_retry_after_cap_and_no_jitter[429]` supplied one response while expecting four requests; `tests/unit/test_time_snapshot.py::test_no_local_clock_fallback` called the real network with no assertion (now hermetic). `tests/integration/test_time_snapshot.py` had the same real-network defect; it was rewritten hermetically in Stage B2 and stays red (stub) until Stage C implements the klines download.
- Cooldown is re-checked before every HTTP attempt (including retries after a sleep), so a cooldown written by another process while this client sleeps stops the next request.
- Cooldown updates use `extend_cooldown`: one exclusive file lock (sidecar `<name>.lock`) around read-compare-write, so the longest deadline always survives concurrent writers; the atomic temp-file replace is kept for crash safety.
- Evidence note: the mutation experiments for B2 were run locally by the implementer; CI does not run a mutation suite yet (planned for the final gate).
