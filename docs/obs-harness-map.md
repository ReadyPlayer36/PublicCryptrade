# OBS harness building blocks: requirement map (protocol v0.5)

Scope of this commit (as authorized after the v0.5 sign-off): the offline-testable pieces of the OBS-01/OBS-02 harness. NOT included, and not runnable: a session runner, the OBS-01 probe runner, the pre-registration step, the evidence writer, the analysis function (stable-time and lag formula) or any `--live` entry point. No live request was made. Milestone 1 remains BLOCKED.

New code lives in `tools/obs/` (outside `src/trading_app/`, not imported by production code, standard library only). Tests: `tests/tools/obs/`, doubles `tests/fixtures/obs_fakes.py`, golden vectors `tests/fixtures/vectors/obs_estimator_vectors.json` with the independent generator `generate_obs_vectors.py` (it imports nothing from the harness; a test regenerates the vectors and compares).

| Protocol item | Module | Tests |
|---|---|---|
| PACE-1, 2, 3, 4, 6 completion-aware single pacer, rolling caps, no early start, no catch-up, abort after 3 no-response requests | `pacer.py` (`Pacer`, `release_ns`, `window_count`) | `test_pacer.py` |
| PACE-5 audit (a)-(g), OBS-01 profile, open-left/closed-right windows | `audit.py` | `test_audit.py` (GV-8) |
| PACE-7 admission (strict inequality, only `theta_lo` decides) | `admission.py` | `test_admission.py` (GV-5) |
| PACE-8 strict 17 s deadline with connection-closing watchdog; 18 s audit backstop | `watchdog.py`, `transport.py`, `audit.py` check (e) | `test_watchdog_transport.py` (GV-9, loopback) |
| 5.2 estimator, v0.5 interval `[s-b-delta(t-a), s+1ms-a+delta(t-a)]`, deadline `D(X)=X-theta_lo`, fixed point | `estimator.py` | `test_estimator.py` (GV-1 to GV-7, containment, 123.4 ms edge) |
| 5.3 SYNC adequacy (`w <= W_max`, empty intersection, 60 s fallback window) | `estimator.py` | `test_estimator.py` (GV-4, fallback) |
| Allow-list safety (host, two paths, exact klines parameters, GET only, no redirects, no proxies, no credentials) | `specs.py`, `transport.py` | `test_pacer.py`, `test_watchdog_transport.py`, `test_harness_safety.py` |

## Decisions and findings for the reviewer

1. PACE-8 mechanism (finding). An experiment (loopback only) showed that calling `httpx.Client.close()` from another thread does NOT interrupt a blocked read, whereas `socket.shutdown(SHUT_RDWR)` does. The transport is therefore built on `http.client` and the watchdog shuts the socket down and then closes the connection. The protocol sentence "closes its connection" is satisfied; the mechanism is the shutdown. The pacer takes `end_ns` after the cancellation has finished.
2. Cancellation limits. The connect phase has its own 5 s socket timeout (TLS handshake included). DNS resolution cannot be interrupted; if a request does not end within the 1 s cancellation allowance the run raises `CancellationFailed` (incident). Reviewer: accept?
3. Outcome codes without an HTTP response: `DEADLINE` (watchdog), `TIMEOUT` (socket timeout), `CONNECT_ERROR` (anything else). Check (e) requires a `DEADLINE` record to last between 17 s and 18 s.
4. Group audit (f) harness decisions (the protocol did not spell these out): a group whose last request failed (no 200) may be a PREFIX of the defined role order; a resync group has 3 to 7 `/time` calls (3 plus up to 4 extra), or fewer only when its last call failed; skipped groups inside a boundary are allowed (MISSED-WINDOW), but order must never go backwards.
5. Arithmetic. Decisions use exact rational arithmetic (`fractions.Fraction`); exported intervals are rounded outward to whole nanoseconds; deadlines are rounded up. The estimator retains samples with `b_j >= t - 600 s` evaluated at the decision time, and the deadline wake loop re-evaluates the retained set at each wake.
6. The pacer starts at `max(earliest, target)` and never reorders; a wake that is late is recorded as late and judged only by V1 (not part of this commit).
7. The default `HttpTransport` accepts only `https://data-api.binance.vision`; a loopback `http` base URL exists solely for offline tests.

## Evidence summary (this commit, Python 3.12.3)

See the evidence files delivered with this commit: full-suite JUnit and console output, coverage of `tools/obs`, the mutation log (29 mutants on the new code, own script, NOT the frozen 16-mutant matrix run), and the repository gate outputs.
