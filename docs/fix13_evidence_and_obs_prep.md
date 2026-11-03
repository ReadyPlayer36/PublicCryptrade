# Fix 13 evidence package and OBS-01/OBS-02 preparation

Branch `impl-obs-harness`, commit `2661934a84a4df0ce8ef85e79131487292966d95` (Fix 13, "approved with conditions" per the user; no written reviewer record seen by Claude).
Milestone 1 remains **BLOCKED**. Nothing here authorizes a live request.

## Part 1. Verification summary (run by Claude, Python 3.12.3, fresh venv, clean checkout)

| Check | Result |
|---|---|
| HEAD | 2661934a84a4df0ce8ef85e79131487292966d95 (diff vs a433fb5: `tests/tools/obs/test_zz_edge_draft.py` only) |
| Full suite | **1322 passed**, 0 failures, 0 errors, 0 skipped (JUnit tests="1322"), 78.4 s |
| `tools/check_freeze.py` | FREEZE CHECK PASSED |
| `tools/validate_matrix.py` (CI args) | PASS: 104 rows, 58 item bindings, 18 mutation killers bound |
| `tools/spec_check.py` (CI args) | exit 0, 13 passed |
| `tools/hollow_scan.py` | exit 0 |
| `tests/tools/obs/test_zz_edge_draft.py` | SHA-256 776fca5a03ed16a875780ca7f4f6cb6ad5cffee1b257e360c5edce515f16a7b4; 12 tests; 10/10 repeat runs passed |

Housekeeping: `spec_check.py` rewrites `evidence/spec_check.log` (reverted, not committed). `src/*.egg-info/` is untracked and `.gitignore` has no entry for it.

Not verified: reviewer approval record; `pip-audit`; any live request (none made).

## Part 2. Mutation verification note (archive)

- Target: `tools/obs/transport.py`, `call()` -> `deadline_allows()`, the pre-write deadline check.
- Mutant: `return not over()` replaced by `return True`.
- Killer: `tests/tools/obs/test_zz_edge_draft.py::test_a_deadline_that_expires_between_the_connect_check_and_the_write_check_blocks_the_write`.
- Result: with the mutant, 1 failed / 11 passed (only the killer failed). Original restored; `git status` clean for `tools/`.
- Observed on two separate runs (at a433fb5 and at 2661934).
- Limit: ad hoc, not in the matrix's 18 bound killers; the test is not yet registered as a killer.

## Part 3. OBS-01 / OBS-02 preparation outline

Sources: `matrix.yaml` (observations, LAG-01, OBS-01/02/03 rows), `docs/obs-protocol.md` v0.5, `docs/obs-harness-map.md`. Binance behavior below is as stated in the protocol's own reading of the docs; Claude has not re-verified it today.

### 3.1 What is required (frozen)
- Hosts/paths: `https://data-api.binance.vision`, exactly `/api/v3/time` and `/api/v3/klines`, GET only, no redirects, no credentials.
- OBS-01: fixed historical candle (BTCUSDT, O = 1767571200000); probe `endTime` = C and C+1, `startTime` = O and O+1 (protocol adds a2/e/f/g); keep raw responses; change client convention only via a new reviewed spec version.
- OBS-02: offsets about +0, +2, +10, +60 s; >= 12 consecutive 5m boundaries and >= 2 four-hour boundaries where 5m/15m/1h/4h close together; compare open/high/low/close (protocol also reports volume, quote volume, trade count); two UTC days.
- Lag = maximum observed time-to-stable + reviewer-approved margin. No hard-coded default (`lag_default: null`, `lag_min_ms: 0`); OBS-02 must finish and the lag be approved before any LIVE run (OBS-03).

### 3.2 State of readiness
| Item | State |
|---|---|
| Protocol v0.5 | approved per project notes; open questions Q1-Q8 listed in section 12 |
| Harness building blocks (pacer, audit, estimator, admission, watchdog, transport) | built and tested offline (this branch) |
| Session runner, OBS-01 probe runner, pre-registration step, evidence writer, analysis function (stability, `bound_k`, lag formula), `--live` entry point | **not built** (per `obs-harness-map.md`); needs its own reviewed commit |
| `tests/observations/*` | gate tests only; `matrix.yaml` keeps OBS-01/02 `open` |
| Fallback host `api.binance.com` | not covered by observation (protocol Q6) |

### 3.3 Proposed next steps (for review, in order)
1. Reviewer answers protocol Q1-Q8 (esp. Q1 basis T_app vs T_all, Q3 margin, Q5 default vs explicit lag, Q6 fallback host).
2. Implement and review, as a separate commit: analysis function with golden vectors first (stable-from index, `bound_k`, lag formula, tier table), then OBS-01 probe runner, then session runner and pre-registration.
3. Offline dry run of the runner against the fake transport; PACE-5 audit must pass.
4. Owner runs OBS-01 on their machine with `--live`; stop and report on any failure condition. Only if it passes, OBS-02 on D1 and D2.
5. Evidence returned (JSONL, manifest with commit SHA and file hashes, pre-registration file, analysis output); reviewer proposes/approves lag.
6. Verify rate limits (`exchangeInfo` `rateLimits` for the host) and re-read current Binance docs for klines/time before the live run; the protocol's example limits are not verified for this host.

### 3.4 Lag candidates (illustrative, NOT proposed values, NOT for config)
Protocol section 8 formula: `M = max(2000, L_obs)`, `L_raw = L_obs + M`, `L = ceil(L_raw/1000)*1000`; `L_obs > 60000` or any unbounded sample means no lag (INCONCLUSIVE). The table is the formula applied to hypothetical `L_obs` values; no real observation exists.

| Hypothetical L_obs (ms) | L (ms) |
|---|---|
| 0 | 2000 |
| 1000 | 3000 |
| 2000 | 4000 |
| 3200 | 7000 |
| 10000 | 20000 |
| 60000 | 120000 |

The protocol's own expectation (unverified assumption, not Binance behavior): measurement design alone puts `L_obs` near 0.7-2.9 s, so the formula would give roughly 4000-7000 ms. The approved lag must come from evidence; until then config must require an explicit non-negative value (LAG-01).

## Findings
| Sev | Location | Issue | Fix |
|---|---|---|---|
| Medium | Readiness | No session runner/analysis/`--live` code exists, so OBS-01/02 cannot be run yet | Separate reviewed implementation commit (3.3 step 2) |
| Low | Evidence | Fix 13 approval not on record | Attach reviewer message to the evidence folder |
| Low | Mutation | New killer not registered in the matrix | Register via a new spec version if wanted |
| Low | Repo | `.gitignore` lacks `*.egg-info/`; `spec_check` rewrites a committed log | Separate small commit; revert the log after each run |

Approval status: Fix 13 evidence **verified as stated**; OBS-01/02 **not ready to execute**; Milestone 1 **BLOCKED**.
