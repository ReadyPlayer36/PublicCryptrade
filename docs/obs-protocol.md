# OBS-01 / OBS-02 experiment protocol (DRAFT v0.1 for reviewer evaluation)

Status: **draft, not approved, nothing has been executed.** Milestone 1 remains **BLOCKED**. No live data is collected until the reviewer approves this protocol AND the harness commit (section 9). Frozen files (`matrix.yaml`, schema, source docs, frozen tools) are untouched; this is a new document.

Scope: public read-only Binance Spot market data only. No keys, no orders, no private endpoints, no futures/margin.

## 1. Facts, assumptions, unverified items

Facts (from the repository at `ef9fe11`):
- Client convention: `startTime = start`, `endTime = end - 1`, `limit = 1000`; finality is `close_time_ms < B`, `B = S - L`; `S` is one `/api/v3/time` snapshot; no local-clock fallback; `L` has no default (LAG-01).
- Frozen matrix text: OBS-01 = fixed historical candle with `endTime = C, C+1` and `startTime = O, O+1`, retain raw responses, update the client convention if observation disagrees. OBS-02 = offsets `+0s, +2s, +10s, +60s` over `>= 12` consecutive 5m boundaries and `>= 2` 4h boundaries where 5m/15m/1h/4h close together, comparing open/high/low/close; lag = max observed time-to-stable + a reviewer-approved margin.

Unverified (must be checked against the official Binance Spot API docs by the reviewer before execution; I have not verified them and do not rely on them):
- U1: whether `startTime`/`endTime` filter on kline open time or close time, and whether each is inclusive. This is what OBS-01 measures; the docs are a cross-check, not a substitute.
- U2: request weight of `/api/v3/klines` and `/api/v3/time`, and the current rate-limit/ban rules (429/418). The bounds in section 5 are set far below any plausible limit and must be confirmed.
- U3: whether `data-api.binance.vision` serves the same kline timing/finality as `api.binance.com`. Observations apply to the host used; the fallback host is NOT observed here.

## 2. Safety and isolation controls (both experiments)

- Hosts/paths: only `https://data-api.binance.vision` with exactly `/api/v3/time` and `/api/v3/klines`, GET only. Anything else is refused by the harness before a socket is opened.
- No credentials: no API-key header, no signature, no `recvWindow`; the harness asserts their absence on every request. Responses are stored with a whitelist of headers (status, `Date`, `Content-Type`, `Retry-After`, `X-MBX-USED-WEIGHT*`), no cookies.
- Redirects off; any 3xx is an incident. Explicit timeouts (section 5). Single attempt per request (no retry: a retry would distort the timing being measured).
- Existing cooldown file `data/binance_cooldown.json` is honored and written on 418/429; a corrupt or active cooldown aborts the run.
- The harness lives outside `src/trading_app/` and outside pytest collection, runs only on the owner's machine (never CI), and refuses to start without an explicit `--live` flag. Offline tests (fake HTTP, fake clock) cover the harness and analysis code, in the CI suite.
- Local clock is used ONLY to schedule sleeps. All finality-relevant times come from `/api/v3/time`. The production code is not changed by these experiments.
- Any unexpected status/shape/host/path, any 3xx, 418 or 429, or a malformed payload ends the run immediately (incident, section 5).

## 3. OBS-01: boundary semantics

Fixed fixture: BTCUSDT, candle open `O = 1767571200000` (2026-01-05T00:00:00Z), which is aligned for 5m, 15m, 1h and 4h (verified: remainder 0 for each). Interval `I`, close `C = O + I - 1`. All probed candles are historical (months old), so finality is not a factor.

Hypotheses:
- H1 (start): `startTime` is compared with open time, inclusive (returned rows have `open >= startTime`).
- H2 (end, open-time): `endTime` is compared with open time, inclusive (`open <= endTime`).
- H2' (end, close-time): `endTime` is compared with close time, inclusive (`close <= endTime`).
- The current client convention is correct if H1 holds and either H2 or H2' holds (for aligned `end`, `endTime = end - 1` selects the same last candle under both).

Probes, per timeframe in {5m, 15m, 1h, 4h}, each with `limit = 5` and an anchor `startTime = O - 2I` unless the probe sets its own `startTime`:

| Probe | Parameters | Expected under H1+H2 | Expected under H1+H2' |
|---|---|---|---|
| a | `startTime = O` | first row open `O` | same |
| b | `startTime = O + 1` | first row open `O + I` | same |
| c | `endTime = C` | last row open `O` | last row open `O` |
| d | `endTime = C + 1` | last row open `O + I` | last row open `O` |
| e | `endTime = C - 1` | last row open `O` | last row open `O - I` |
| f | `endTime = O` | last row open `O` | last row open `O - I` |
| g | `endTime = O - 1` | last row open `O - I` | last row open `O - I` |

Probes a-d are the matrix minimum; e-g are added because c and d alone cannot tell H2 from H2' unless d is read carefully, and e-g make the discrimination explicit (reviewer may strike them).
Each probe is run twice, at least 60 s apart. Raw response bodies, request parameters and UTC timestamps are retained.

Pass: every probe on every timeframe matches exactly one of the two combined hypotheses, the same one for all timeframes; repeats are byte-identical; every row has 12 fields, `close = open + I - 1`, and open aligned to `I`. Outcome: client convention CONFIRMED, no client change.
Fail: any probe matches neither combined hypothesis, timeframes disagree, or repeats differ. Then STOP all live work, report to the reviewer, and the client convention is changed only through a new reviewed spec version (frozen matrix wording requires this).
Request count: 4 timeframes x 7 probes x 2 repeats = 56 klines requests, plus ~10 time requests.

## 4. OBS-02: time-to-stable

Definitions (`T` = the close boundary in server time, i.e. open time of the next candle; the observed candle has open `T - I`, close `T - 1`):
- Observation: `S1` (a `/time` call), then the klines request(s), then `S2` (a `/time` call). Offsets are `S1 - T` and `S2 - T`.
- Reference `R`: the same candle fetched at about `T + 180 s` (after the largest matrix offset, before the next 5m boundary at `T + 300 s`).
- Post-session sweep: after the session, every observed candle is fetched again (at least 10 minutes after the last boundary). It must equal `R`.
- Compared tuples: matrix = (open, high, low, close). Full = (close time, open, high, low, close, volume, quote volume, trade count), which is exactly what the repository's conflict check compares (a stored candle that later differs raises `CandleConflictError`).
- A missing row counts as "not equal to R".
- Time-to-stable of a sample = `S2 - T` of the first observation `i` such that every observation `j >= i` equals `R` (upper bound on the true value). If no observation up to +60 s equals `R`, the sample is "unbounded within +60 s".

Hypotheses:
- H-A: at `+60 s` the candle equals `R` for every sample (the stable time is below 60 s).
- H-B: at `+0 s` the candle may be missing or differ from `R`.
- H-C: the 4h/1h candles may take longer than 5m candles.

Schedule (UTC, boundaries are multiples of 5 min; 4h boundaries are 00:00, 04:00, 08:00, 12:00, 16:00, 20:00):
- Session A: 12 consecutive 5m boundaries ending at a 4h boundary (e.g. 03:05, 03:10, ..., 04:00). At every boundary observe the 5m candle; at 04:00 also observe the 15m, 1h and 4h candles, which close then.
- Session B: the next 4h boundary (e.g. 08:00), observing all four timeframes; boundaries 07:55 and 08:05 are included for the 5m candle as controls. Sessions A and B together give 12 consecutive 5m boundaries and 2 four-hour boundaries (the matrix minimum).
- Offsets per boundary: nominal `+0 s, +2 s, +10 s, +60 s`, then the reference at `+180 s`. Sampling is sequential.

Validity of an observation: `S1 >= T + offset`, and `S2 - T <= offset + tolerance` with tolerance 2.0 s for offsets 0/2/10 s and 5.0 s for 60 s and the reference; all requests returned 200 within the timeout. Invalid observations are kept in the evidence but do not count. A boundary counts only if all five observations of every required timeframe are valid.
Multi-timeframe boundaries use one time pair per offset: `S1`, the four klines requests back to back, `S2`.

Run validity (pass conditions for the experiment itself):
1. >= 12 consecutive 5m boundaries fully valid.
2. >= 2 four-hour boundaries fully valid for all four timeframes.
3. Post-session sweep equals `R` for every candle.
4. No incident (section 5).

Fail / inconclusive: condition 3 fails (candles change after `+180 s`, so the lag cannot be bounded by these offsets); or any sample is unbounded within +60 s. Then the offsets are extended only through a reviewed protocol amendment (e.g. add +120 s, +300 s), never ad hoc.

Result: `L_obs = max` over all valid samples and timeframes of time-to-stable, reported separately for the matrix tuple and the full tuple, per timeframe and overall. The recommendation uses the larger (full tuple) value. A single global lag is used (the frozen design has one `finality_lag_ms`), so it is the maximum over timeframes.

## 5. Request-rate bounds, timeouts, abort rules

- Timeouts: connect 5 s, read 10 s, per request, no retry. A timeout invalidates that observation; 3 consecutive failures abort the run.
- Rate: at most 2 requests per second and 60 per minute from the harness, enforced by the harness itself. The heaviest moment (a 4h boundary offset) is 6 requests in under 3 s, then idle until the next offset. Estimated totals: OBS-01 about 66 requests; Session A about 250; Session B about 90; sweeps about 30.
- Abort immediately (incident, no continuation, evidence kept): HTTP 418 or 429 (cooldown written, honoring `Retry-After` is not attempted inside the run), any 3xx, any status other than 200, non-JSON body, unexpected shape, wrong host/path, timestamps that are not integers, `S` going backwards by more than 1 s.
- An incident means the owner reports it to the reviewer before anything is rerun.

## 6. Data recorded and evidence layout

Per request, one JSONL record: scheduled boundary `T`, nominal offset, request id, method/host/path, params, local monotonic start/end (diagnostic only), UTC ISO-8601 with `Z` plus epoch ms for `S1`/`S2`, HTTP status, whitelisted headers, raw body and its SHA-256. Run manifest (LIVE-05 style): command, commit SHA, Python version, host used, UTC range, stdout, stderr, exit code, SHA-256 of every evidence file. Layout: `evidence/OBS-01/` and `evidence/OBS-02/` (written by the owner, attached to the review; not committed to the reviewed code commit). The analysis step (stable-time computation, lag recommendation) is a pure function with offline golden vectors computed independently.

## 7. Initial lag candidates (proposals only; no lag is selected until data exist and the reviewer approves)

The observed time-to-stable is only known on the offset grid {0, 2, 10, 60} s, so the plausible outcomes of `L_obs` are those grid values (plus measurement overhead up to the tolerance). Proposed rule: `L = L_obs + M`, with `M = max(2000 ms, L_obs)` (at least double, never less than 2 s). A larger lag only delays when the newest candle becomes available; it cannot make data less correct.

| Observed `L_obs` | Proposed `L` |
|---|---|
| about 0-2 s | 4000 ms |
| about 10 s | 20000 ms |
| about 60 s | 120000 ms |
| above 60 s or not stable by the reference | no value; protocol amendment |

## 8. Relationship to other rows

- LAG-01/OBS-03: config keeps requiring an explicit lag until the reviewer approves one; the matrix keeps `OBS-01`/`OBS-02` status `open` (a test pins this), so recording results does not edit `matrix.yaml`.
- LIVE-01..05 run only after OBS-02 and the lag are approved.

## 9. Execution plan and gates

1. Reviewer evaluates and approves this protocol (possibly amended).
2. Harness + analysis code + offline tests are written (fakes only, no network in CI) and reviewed as a separate commit.
3. The owner runs OBS-01, then OBS-02 Sessions A and B, on their own machine with `--live`.
4. Evidence is returned to the reviewer; the lag is proposed from the data; the reviewer approves or rejects it.

## 10. Open questions for the reviewer

1. Q1: use the full tuple (including volume and trade count) for the lag, since stored candles are conflict-checked on all fields? Recommended: yes.
2. Q2: accept the extra probes e-g in OBS-01 and the +180 s reference plus post-session sweep in OBS-02 (not in the matrix text)?
3. Q3: is one pair of sessions on one day enough, or should a second day / a busier market hour be required before the lag is approved?
4. Q4: tolerances (2 s, 5 s), rate bounds (2/s, 60/min), timeouts (5 s/10 s) and the margin rule `M = max(2000 ms, L_obs)`: approve or change.
5. Q5: after approval, may the lag become a configured default, or must it stay explicit? (A default change needs a new spec version because of LAG-01.)
6. Q6: confirm items U1-U3 against the official docs, including whether the fallback host needs its own observation.
