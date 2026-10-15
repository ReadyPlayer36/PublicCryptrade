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

## Stage C decisions (klines download, security tests)
- `get_historical_klines` returns the raw Binance rows (lists) exactly as received, after validation; the service layer converts them. Keyword-only arguments.
- Order of operations: input validation (naive, alignment, order, symbol, timeframe) before any network call -> `begin_fetch()` -> one server-time snapshot S -> configured-lag check -> effective end -> empty-range error -> pagination.
- A missing `finality_lag_ms` fails the fetch with `BinanceClientError` after the server-time snapshot (as `test_finality_lag_has_no_default` requires). `finality_lag_ms=0` is valid by design (`lag_min_ms: 0`) and is used only by offline tests; any live run needs the lag approved after OBS-02.
- Pagination continues until the cursor reaches the effective end (a short page is not a terminator). An empty page stops paging, and the result is ALWAYS validated: an empty response for a non-empty effective range raises `DataValidationError` (`EMPTY_RESULT`); an empty page after data fails with `UNEXPECTED_END`. (Reviewer finding C1, preferred fail-closed default. Several Stage-2 tests had used `[]` as an incidental payload while asserting only the `endTime` clamp; they now supply real rows. If a legitimately empty range must be supported later, that needs an explicit spec change and a way for callers to distinguish it.)
- Non-final rows (`close_time_ms >= S - L`) raise `NonFinalCandleError` before structural validation; they are never dropped silently.
- Existing tests corrected in Stage C: tests that relied on an implicit zero lag now pass `finality_lag_ms=0`; `test_b_not_final_vectors_shrink_to_explicit_empty_range` now uses each vector's own `L_ms` (the 60s-lag cases were previously never exercised); LIVE-01/03 fake payloads were empty lists while asserting 12 and 1152 rows, so they now generate real rows. These remain offline stand-ins: the matrix still requires genuine live evidence for LIVE-01..04, which is a separate gate.
- Eight security tests (M1-04 x3, M1-16, TRIP-01/02, LOG-01/02) were hollow placeholders that called `get_historical_klines()` with no arguments and asserted nothing. They are replaced by real tests plus `tools/tripwire.py` (AST scan of `src/` and `scripts/`; `tests/` exempt; exact scanned-file count printed) and a client logging policy: only fixed labels, counts and status codes; never URLs, headers, params or exception text; transport errors are raised outside the `except` block so neither `__cause__` nor `__context__` carries the original exception text.
- Not covered yet: storage, repository conflicts, transactions, config, CLI/service wiring (Stage D); evidence, mutation runner, coverage gates and `pip-audit` (final gate).
- Review round on Stage C (C1-C4): empty responses are rejected (C1); the tripwire now detects aliased imports, attribute references, `getattr` string calls and the `/papi/` family (C2); cooldown persistence and corrupt-cooldown errors carry only fixed text or an exception type name, raised outside `except` blocks (C3); LOG-02 now injects an `httpx.HTTPStatusError` carrying a poisoned URL from the HTTP client itself (C4).
