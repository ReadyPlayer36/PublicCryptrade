**Milestone 1.2 — Revision Specification ****&**** Acceptance Checklist**

*Binance Spot Historical Market-Data Layer*

# 1. Purpose

This document converts the latest assessment into the required engineering specification and acceptance gate for the next Milestone 1 revision. The goal is to harden the existing public market-data implementation and produce reproducible evidence. No trading functionality is to be added.

# 2. Current approval status

**STATUS: BLOCKED**

The previous revision addressed the major code-level findings in the right direction, but those fixes are not yet independently evidenced. Clean-environment installation and live Binance acceptance runs are still missing.

# 3. Scope constraints

No strategy, indicators, backtesting, sizing, order management, or execution logic.

No API-key handling, request signing, private endpoints, or order submission.

Public Binance market-data endpoints only.

Preserve the existing modular architecture; do not rewrite unnecessarily.

Do not silently repair suspicious market data.

Do not claim milestone completion when required tests or evidence are missing.

# 4. Mandatory code changes

**R3 — Server-time clamp and fail-closed behavior**

Do not silently change the requested end without exposing the effective range.

Return or record both requested and effective start/end values.

If /api/v3/time fails, times out, returns malformed JSON, or returns an invalid timestamp, abort the fetch.

Never fall back to the local system clock for candle-finality decisions.

Handle the exact interval-boundary case correctly.

Handle a candle that closes during pagination correctly.

**R4 — Endpoint and URL hardening**

Use exact-match against a normalized path allowlist.

Reject path traversal such as /api/v3/klines/../order.

Reject encoded traversal and encoded path variants.

Reject lookalike paths such as /api/v3/timeX.

Ignore/reject query-string tricks that attempt to alter endpoint selection.

Disable automatic redirects for the public HTTP client.

Validate configurable BINANCE_BASE_URL scheme and host.

Do not permit a redirect or configuration change to send credentials or requests to an unintended host.

**R5 — File-backed SQLite concurrency**

Use a real file-backed SQLite database for concurrency tests.

Use separate processes, not only same-process threads or in-memory SQLite.

Verify overlapping inserts do not produce duplicate rows.

Verify a conflict does not leave a partially committed batch.

Confirm SQLite WAL and busy-timeout behavior is actually active.

Add *.db-wal and *.db-shm to .gitignore.

**R6 — Duplicate/conflict policy**

Define exactly which fields participate in equality comparison: symbol, timeframe, timestamps, OHLCV, quote volume, and trade count as applicable.

Identical rows must be idempotent and insert zero new rows.

Same key with different values must raise CandleConflictError.

A conflict must abort the current transaction/fetch rather than partially committing the batch.

Document the policy for legitimate upstream revisions.

Add a scan/check for existing databases that may contain forming candles from the previous implementation.

**R7 — Retry and rate-limit hardening**

Retry only statuses/errors that are explicitly considered retryable.

Do not retry 400, 403, or 418 automatically.

Honor Retry-After for 429/418 where provided.

Cap Retry-After and backoff delays.

Add jitter to retry delays.

Add a cross-call cooldown after repeated 429 responses.

Test exact request counts and sleep durations for 400, 403, 418, 429, 500, timeout, and malformed JSON.

# 5. Required regression tests

1. [ ] Server-time endpoint failure causes the fetch to abort.

2. [ ] Malformed /api/v3/time response causes the fetch to abort.

3. [ ] Invalid server timestamp causes the fetch to abort.

4. [ ] Server time exactly on an interval boundary is handled correctly.

5. [ ] A candle that closes during pagination is not stored as final.

6. [ ] Future end request reports the effective clamped range.

7. [ ] The client never falls back to local time when server-time retrieval fails.

8. [ ] Exact allowlist blocks /api/v3/klines/../order.

9. [ ] Exact allowlist blocks encoded traversal variants.

10. [ ] Exact allowlist blocks /api/v3/timeX.

11. [ ] Query-string endpoint tricks are rejected or ignored safely.

12. [ ] Changed/untrusted host is rejected.

13. [ ] Redirects are disabled.

14. [ ] Two separate processes insert overlapping ranges into a file-backed SQLite database.

15. [ ] Concurrent insertion leaves no duplicate rows.

16. [ ] A conflict causes the entire transaction to roll back with no partial batch.

17. [ ] Identical re-insertion is idempotent and inserts zero new rows.

18. [ ] A conflicting row raises CandleConflictError.

19. [ ] Conflict comparison covers the documented complete field set.

20. [ ] Retry behavior is tested for 400, 403, 418, 429, and 500.

21. [ ] 429 Retry-After handling is capped and jittered.

22. [ ] Timeout retry behavior is tested.

23. [ ] Malformed JSON retry behavior is tested.

24. [ ] Repeated 429 responses trigger the cross-call cooldown.

25. [ ] No URL, header, API key, token, or secret-like environment value appears in logs.

26. [ ] download_candles.py runs successfully against a mocked public-data client.

27. [ ] Python Decimal/string comparisons are used for acceptance checks instead of CAST AS REAL.

# 6. Metadata and audit-trail requirements

[ ] Define precisely what the SHA-256 hash covers.

[ ] Document whether the hash is over raw Binance rows or normalized candle records.

[ ] Define deterministic serialization and field ordering.

[ ] Include symbol, timeframe, requested range, and effective range in the fetch metadata.

[ ] Add a schema version to data_fetches.

[ ] Clearly state that data_fetches is an audit trail and not itself a frozen dataset snapshot.

# 7. Unchanged/previously identified items to verify

[ ] Verify scripts/download_candles.py still works after client/service changes.

[ ] Create the data directory automatically before SQLite connection if required.

[ ] Review the unused FastAPI dependency; remove it from Milestone 1 dependencies if it provides no current value, or explicitly document why it remains.

[ ] Confirm Python >=3.12 remains the supported baseline and the artificial <3.13 upper bound is removed.

[ ] Confirm tests execute on an actual Python 3.12 interpreter.

# 8. Required source evidence

[ ] Provide the complete revised source tree or a complete diff.

[ ] Provide raw pytest output, not only a summarized pass count.

[ ] Run pytest -ra --cov=trading_app --cov-branch --cov-report=term-missing.

[ ] Report total branch coverage and every uncovered line.

[ ] Explain any test-suite warnings and confirm they are resolved or explicitly accepted.

# 9. Clean-environment verification

python --version

python -m venv .venv

source .venv/bin/activate  # POSIX; use the platform equivalent on Windows

python -m pip install --upgrade pip

pip install -e ".[dev]"

pip freeze

pytest -ra --cov=trading_app --cov-branch --cov-report=term-missing

Acceptance requirement: the clean environment must install successfully and the complete suite must pass. If network/package-index access prevents this, the gate remains blocked and that limitation must be reported.

# 10. Required live Binance evidence

1. [ ] 12-candle BTCUSDT 5m run using the public API.

2. [ ] Immediate re-run of the same range showing 0 newly inserted rows.

3. [ ] More than 1,000 candles (approximately four days of 5m data) to exercise pagination and chunked storage.

4. [ ] Request with a future end time demonstrating the effective-range clamp.

5. [ ] Record command, start/end, output, and exit status for every live run.

6. [ ] Provide relevant SQLite verification queries and their outputs.

7. [ ] Provide the resulting data_fetches rows for the live runs.

8. [ ] Verify no duplicate candle keys.

9. [ ] Verify candle timestamp spacing.

10. [ ] Verify OHLC relationships and positive/valid prices.

11. [ ] Verify decimal values without CAST AS REAL.

# 11. Official Binance documentation evidence

[ ] Klines endpoint documentation reviewed.

[ ] Server-time endpoint documentation reviewed.

[ ] Rate-limit / retry behavior documentation reviewed.

[ ] Implementation behavior compared directly with the current official documentation.

Official documentation starting point: https://developers.binance.com/docs/binance-spot-api-docs

# 12. Required answers

[ ] Does CandleConflictError abort the whole fetch/transaction or only the offending page? The required behavior is whole-transaction rollback with no partial batch.

[ ] Was the Python <3.13 pin intentionally dropped? Document the decision.

[ ] Are all tests run on a Python 3.12 interpreter? Provide python --version evidence.

# 13. Final acceptance gate

| Gate | Required evidence | Status |
| --- | --- | --- |
| Code hardening | R3–R7 implemented and regression-tested | [ ] |
| Security boundary | Exact path/host/redirect controls tested | [ ] |
| Concurrency | Separate-process file-DB test passes with rollback proof | [ ] |
| Conflict policy | Complete comparison policy documented and tested | [ ] |
| Retry policy | Exact retry/sleep/cooldown behavior tested | [ ] |
| Branch coverage | Raw pytest + branch coverage + uncovered lines supplied | [ ] |
| Clean install | Fresh venv install and test run supplied | [ ] |
| Live 12-candle run | BTCUSDT 5m run + idempotent rerun supplied | [ ] |
| >1,000 candle run | Real API pagination/chunking evidence supplied | [ ] |
| Future-end run | Clamp/effective-range evidence supplied | [ ] |
| SQLite evidence | Queries and data_fetches output supplied | [ ] |
| Official docs | Klines/time/rate-limit behavior verified | [ ] |

**Approval rule: **Milestone 1 remains BLOCKED if any mandatory code/test/evidence gate is missing, if the complete test suite fails, if clean installation cannot be demonstrated, or if the live public-data acceptance runs are not supplied.

# 14. Expected disposition after successful evidence

If all mandatory gates pass, the milestone may move from BLOCKED to APPROVED WITH CONDITIONS, subject to documenting any explicitly accepted residual risks. No profitability or trading-performance conclusion is implied by this approval.