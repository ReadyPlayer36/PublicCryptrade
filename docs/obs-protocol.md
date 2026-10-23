# OBS-01 / OBS-02 experiment protocol (DRAFT v0.2 for reviewer evaluation)

Status: **draft, not approved, nothing has been executed, no harness code exists.** Milestone 1 remains **BLOCKED**. No live data is collected until the reviewer approves this protocol AND a separately reviewed harness commit (section 11). Frozen files are untouched; this is a new document.

Scope: public read-only Binance Spot market data only. No keys, no orders, no private endpoints, no futures/margin.

## 0. Changes from v0.1 (reviewer blocking items)

| Item | Where addressed |
|---|---|
| 1. Rate pacing vs schedule, deterministic fail/inconclusive behavior | sections 5 and 6 |
| 2. All 12 kline fields, app conflict fields, stability criteria | section 7 |
| 3. Conservative lag bound, rounding, formula/table consistency | section 8 |
| 4. Two separate UTC days, including a busier market period | section 9 |
| 5. Corrected OBS-01 pass condition; U1-U3 documentation conclusions | sections 1 and 4 |

## 1. Facts, documentation conclusions (U1-U3), assumptions

Facts from the repository (`ef9fe11`): the client uses `startTime = start`, `endTime = end - 1`, `limit <= 1000`; finality is `close_time_ms < B`, `B = S - L`; one `/api/v3/time` snapshot `S` per fetch; no local-clock fallback; `L` has no default (LAG-01); stored candles are conflict-checked on close time, OHLC, volume, quote volume and trade count with numeric Decimal equality.

Frozen matrix text: OBS-01 = fixed historical candle, `endTime = C, C+1`, `startTime = O, O+1`, retain raw responses, update the client convention if observation disagrees. OBS-02 = offsets `+0 s, +2 s, +10 s, +60 s` ("approximately") over `>= 12` consecutive 5m boundaries and `>= 2` 4h boundaries where 5m/15m/1h/4h close together, comparing open/high/low/close; lag = maximum observed time-to-stable plus an explicit reviewer-approved margin.

Documentation conclusions. These are my reading of the official Binance developer docs on 2026-10-23 (`developers.binance.com`: Spot REST API general information; Market > Kline/Candlestick data; General > Check server time; FAQ "Market Data Only URLs"). If the reviewer's own reading differs, the reviewer's governs.

- **U1 (start/end semantics): NOT resolved by the docs.** For `/api/v3/klines` the docs say klines are identified by their open time, and the general section says: with `startTime` the oldest items from `startTime` up to the limit are returned, with `endTime` the most recent items up to `endTime`, with both it behaves like `startTime` but does not exceed `endTime`. They do NOT say whether `startTime`/`endTime` are compared with open time or close time, nor whether the bounds are inclusive. OBS-01 therefore remains required; the docs only fix the limit/ordering behavior used in the probe design. The `timeZone` parameter (default UTC) is never sent.
- **U2 (weights, limits): partly resolved.** Documented: `/api/v3/klines` IP weight 2; `/api/v3/time` IP weight 1; HTTP 429 on exceeding a limit; HTTP 418 for an automatic IP ban after continuing past 429s, with ban durations scaling from 2 minutes to 3 days; `Retry-After` (seconds) sent with 418/429; HTTP 403 may indicate a WAF block or a rate-limit violation; limits are per IP; API-side processing timeout is 10 s (error -1007). The actual limits are published in `exchangeInfo` `rateLimits`; the docs' example payload shows 6000 weight per minute and 61000 raw requests per 5 minutes, but that is an example, and the live values for `data-api.binance.vision` are NOT verified here. The pacing caps below are far below that example, and the harness records the `X-MBX-USED-WEIGHT-*` headers.
- **U3 (host): partly resolved.** The FAQ lists `/api/v3/klines` and `/api/v3/time` among the endpoints served by `data-api.binance.vision`, and lists `api1-api4`, `api-gcp`, testnet and demo hosts elsewhere (all excluded by the frozen policy). The docs do NOT state that timing/finality of `data-api.binance.vision` equals that of `api.binance.com`. Observations therefore apply to `data-api.binance.vision` only; the fallback host is not covered (open question Q6).
- Supporting context for H-B below: the docs say the system is asynchronous, so some delay in responses is expected, and list the kline endpoint's data source as "Database", the source with the most potential for update delay. This motivates the experiment; it is not a guarantee of any delay.

## 2. Safety and isolation controls (both experiments)

- Hosts/paths: only `https://data-api.binance.vision`, exactly `/api/v3/time` and `/api/v3/klines`, GET only. Anything else is refused before a socket is opened. Only the parameters `symbol`, `interval`, `startTime`, `endTime`, `limit` are ever sent.
- No credentials: no API-key header, no signature, no `recvWindow`; asserted on every request. Responses are stored with a whitelist of headers (status, `Date`, `Content-Type`, `Retry-After`, `X-MBX-USED-WEIGHT*`), no cookies.
- Redirects off; any 3xx is an incident. Single attempt per request (a retry would distort the timing being measured).
- The cooldown file `data/binance_cooldown.json` is honored and written on 418/429; a corrupt or active cooldown aborts the run.
- The harness lives outside `src/trading_app/` and outside pytest collection, runs only on the owner's machine (never CI), and refuses to start without `--live`. Offline tests (fake HTTP, fake clock, fake pacer) cover the harness and the analysis code in CI.
- The local clock is used ONLY to schedule sleeps. All finality-relevant times come from `/api/v3/time`, and local monotonic time is used only to measure elapsed durations. Production code is unchanged.
- Timeouts: connect 5 s, read 12 s (above the documented 10 s API processing timeout, so a documented -1007 response is not cut off).

## 3. Pacing rules (apply to EVERY request, including `/time`)

- PACE-1: one request in flight at a time (no concurrency).
- PACE-2: the start of any request is at least 0.6 s after the start of the previous request AND after the previous request has finished. This gives at most 2 starts in any 1-second window (actually 1.67 per second).
- PACE-3: at most 60 request starts in any rolling 60-second window; timed-out and failed attempts count.
- PACE-4: one single pacer object issues every request type (clock sync, observation `/time`, klines, reference, sweep, pre-registration query, OBS-01). No bypass, no exemptions.
- PACE-5 (post-run audit, deterministic): the analysis step recomputes the minimum gap between starts, the maximum starts in any 1 s window and the maximum in any 60 s window from the recorded local monotonic start times. If the gap is below 0.6 s, or any window exceeds its cap, the whole run is INVALID-PACING (harness defect, treated as an incident, no results used).
- OBS-01 uses a stricter pace: at least 2.0 s between starts (at most 30 per minute), and its two passes are at least 60 s apart.

## 4. OBS-01: boundary semantics

Fixed fixture: BTCUSDT, candle open `O = 1767571200000` (2026-01-05T00:00:00Z), aligned for 5m, 15m, 1h and 4h (checked: remainder 0 for each). Interval `I`, close `C = O + I - 1`. All probed candles are months old (finality irrelevant).

Hypotheses, four combined readings (start rule x end rule), plus an exclusive start rule as a negative control:
- Start: H1 `open >= startTime`; H1' `close >= startTime`; H1x `open > startTime` (exclusive, negative control).
- End: H2 `open <= endTime`; H2' `close <= endTime`.

Start probes, per timeframe, `startTime = s`, no `endTime`, `limit = 3` (oldest from `startTime`, per the docs). Entry = open time of the FIRST returned row, as a multiple of `I` relative to `O`:

| Probe | `s` | H1 | H1' | H1x |
|---|---|---|---|---|
| a | `O` | `O` | `O` | `O + I` |
| b | `O + 1` | `O + I` | `O` | `O + I` |
| a2 | `O - 1` | `O` | `O - I` | `O` |

End probes, per timeframe, `startTime = O - 2I`, `endTime = e`, `limit = 5` (with both bounds the docs say it behaves like `startTime` but does not exceed `endTime`). Entry = open time of the LAST returned row:

| Probe | `e` | H2 | H2' |
|---|---|---|---|
| c | `C` | `O` | `O` |
| d | `C + 1` | `O + I` | `O` |
| e | `C - 1` | `O` | `O - I` |
| f | `O` | `O` | `O - I` |
| g | `O - 1` | `O - I` | `O - I` |

Each probe is run twice (two passes at least 60 s apart). Probes a, b, c, d are the matrix minimum; a2 and e, f, g are added so that every hypothesis pair differs on at least one probe (a2/b separate H1 from H1'; d/e/f separate H2 from H2'; a separates H1x).

Pass condition (corrected). Evaluate per timeframe, then across timeframes:
1. The returned first/last rows of ALL start probes are predicted by exactly one start hypothesis, and ALL end probes by exactly one end hypothesis (so exactly one combined reading fits), the same reading for all four timeframes.
2. The two passes are byte-identical.
3. Every row is structurally valid (section 7.1) and `close = open + I - 1`.
4. The fitted reading is one of the four inclusive combinations {H1, H1'} x {H2, H2'}. For any of these four, the client convention (`startTime = start`, `endTime = end - 1`, both aligned) selects exactly the candles `[start, end)`: probe a returns `O` first and probe c returns `O` last. Check explicitly that probes a and c match that. If so: client convention CONFIRMED, no client change.

Fail (stop all live work, report to the reviewer): no combined reading fits; H1x fits (exclusive start); the timeframes disagree; the passes differ; any malformed row. A convention change is made only through a new reviewed spec version.
Request count: 4 timeframes x 8 probes x 2 passes = 64 klines requests (plus 2 `/time` for UTC records) = 66, at 2 s spacing about 2.2 minutes of requests plus the 60 s gap.

## 5. OBS-02: schedule and pacing-compliant timetable

Definitions: `T` = a close boundary in server time (open time of the next candle); the observed candle has open `T - I`, close `T - 1`. OBS-02 starts only after OBS-01 has PASSED (its queries use `startTime = T - I`, `endTime = T - 1`, `limit = 1`, which relies on the OBS-01 conclusion).

An observation group for a set of timeframes is: one `/time` call (S1), then one klines request per timeframe, then one `/time` call (S2). Timeframes are requested in the order 4h, 1h, 15m, 5m (largest first: the candle most likely to be unstable is sampled earliest, which is conservative). A 5m-only boundary has group size 3 requests; a 4-timeframe boundary has group size 6.

Planned request starts, seconds after `T` in server time (each gap is exactly 0.6 s unless stated):

| Group | Nominal offset | 5m-only boundary | 4-timeframe boundary |
|---|---|---|---|
| resync | -30 | 3 `/time` calls at -30, -29, -28 (1 s apart) | same |
| g0 | +0 | 0.0, 0.6, 1.2 | 0.0, 0.6, 1.2, 1.8, 2.4, 3.0 |
| g1 | +2 | 2.0, 2.6, 3.2 | 3.6, 4.2, 4.8, 5.4, 6.0, 6.6 (earliest slot after g0, PACE-2) |
| g2 | +10 | 10.0, 10.6, 11.2 | 10.0 ... 13.0 |
| g3 | +60 | 60.0, 60.6, 61.2 | 60.0 ... 63.0 |
| ref | +180 | 180.0, 180.6, 181.2 | 180.0 ... 183.0 |

Because six requests cannot be completed before +2 s at 1.67 requests per second, the 4-timeframe g1 group starts at +3.6 s instead of +2.0 s. The matrix says "approximately +2 s", so the validity window for the group START is `[nominal, nominal + 2.5 s]` (sections below): g1 at +3.6 s is inside `[2.0, 4.5]`. This is the only schedule deviation and it is explicit.

Peak load check: any 60-second window holds at most 3 + 6 + 6 + 6 = 21 request starts (resync plus g0, g1, g2), far below PACE-3's 60; weight in that window is at most 3 + 3 x 10 = 33 (klines weight 2, time weight 1).

Validity of one observation group (all conditions must hold; otherwise it is TIMING-INVALID):
- V1 start window: `S1 - T` in `[o, o + 2.5 s]` for `o` in {0, 2, 10}, and in `[o, o + 5.0 s]` for `o` in {60, 180}. S1 is the server timestamp of the first `/time` call. The harness aims 0.1 s late of nominal so that S1 is not early.
- V2 duration cap: local monotonic time from the start of the S1 request to the end of the S2 request is at most 2.0 s (3.8 s for the 4-timeframe group).
- V3 consistency: `S2 - S1` lies inside `[start(S2) - end(S1), end(S2) - start(S1)]` of the local monotonic clock (plus 50 ms). A violation means a server/local rate anomaly.
- V4 every request returned HTTP 200 within the timeout, with a well-formed body.

Request counts (estimates). Per 5m-only boundary 3 + 15 = 18; per 4-timeframe boundary 3 + 30 = 33. Session type X (12 consecutive 5m boundaries ending at a 4h boundary): 11 x 18 + 33 = 231, plus initial sync 10, plus sweep 15: about 256. Session type Y (a second 4h boundary with 5m controls at -5 min and +5 min): 18 + 33 + 18 = 69, plus sync 10 and sweep 6: about 85. One day (X + Y + 1 pre-registration query): about 342. Two days: about 685, plus OBS-01 66: about 750.

## 6. Deterministic outcomes when timing windows cannot be met

Every classification below is computed by the pure analysis function from the evidence files; no human judgment is involved.

| Event | Classification |
|---|---|
| V1 early or late, V2 exceeded, V3 violated, a timeout or connection failure on any request in the group | the group is TIMING-INVALID; its boundary is TIMING-INVALID (kept in the evidence, never counted) |
| 3 consecutive requests without an HTTP response | ABORT (INCIDENT-NETWORK), run stops |
| HTTP status other than 200 (including 403, 418, 429, any 3xx, any 5xx), non-JSON, wrong shape, wrong host/path, a row with a wrong open time, `X-MBX-USED-WEIGHT-1M` above 600, server time going backwards by more than 1 s | ABORT (INCIDENT), cooldown written for 418/429, owner reports to the reviewer before any rerun |
| PACE-5 violated in the post-run audit | INVALID-PACING, whole run unusable, reported as a harness defect |
| the `+180 s` reference row missing for a candle | REFERENCE-MISSING: session FAILED and reported (a final candle missing 3 minutes after close is itself a finding) |

Session outcomes:
- COMPLETE-VALID: every required boundary valid and all run-validity conditions of section 7.4 hold.
- INCONCLUSIVE-TIMING: at least one required boundary is TIMING-INVALID, so the consecutive-boundary or all-timeframes requirement is not met. No lag is derived from that session's conclusions, but every valid sample in it still counts toward the maximum in section 8 (including them can only raise the lag). The owner may rerun the session from a fresh window, at most 2 reruns per UTC day (3 attempts), all attempts kept and reported; no attempt is dropped from the evidence. If all attempts fail, report to the reviewer (the protocol may need slower offsets via an amendment).
- FAILED: reference missing, post-sweep mismatch, or a sample not stable within +60 s (section 8). Stop and report; no automatic rerun.
- ABORTED: any incident above.

## 7. Stability tuple and criteria

### 7.1 The 12 kline fields (official docs, `/api/v3/klines`; tuple of exactly 12 elements)

| Index | Field | Type in response | Matrix tuple | App conflict set (stored and conflict-checked) | Observation-all set |
|---|---|---|---|---|---|
| 0 | open time | integer | no (identity key, must equal the expected `O`) | key | key |
| 1 | open | decimal string | yes | yes | yes |
| 2 | high | decimal string | yes | yes | yes |
| 3 | low | decimal string | yes | yes | yes |
| 4 | close | decimal string | yes | yes | yes |
| 5 | volume (base asset) | decimal string | no | yes | yes |
| 6 | close time | integer | no | yes (compared) | yes |
| 7 | quote asset volume | decimal string | no | yes | yes |
| 8 | number of trades | integer | no | yes | yes |
| 9 | taker buy base asset volume | decimal string | no | no (not stored) | yes |
| 10 | taker buy quote asset volume | decimal string | no | no (not stored) | yes |
| 11 | ignore ("unused field") | string | no | no | no (recorded verbatim, never compared) |

The three comparison tuples: `T_matrix` = indices 1-4 (the frozen matrix); `T_app` = indices 1-8 (exactly what the repository stores and conflict-checks: close time, OHLC, volume, quote volume, trade count); `T_all` = indices 1-10.

Structural validity of a returned row: exactly 12 elements; indices 0, 6, 8 integers (not boolean); indices 1-5, 7, 9, 10 strings parseable as finite Decimals; index 0 equals the expected open; index 6 equals `open + I - 1`. Any violation is an INCIDENT (wrong shape), not an instability.

### 7.2 Equality
Two observations are equal on a tuple iff every index is equal: integers by value; decimal strings by NUMERIC Decimal equality (the application's rule, so `1.0` equals `1.00`). A raw-text-only difference (same number, different text) is recorded and reported but is not instability. An absent row (the klines response is an empty array) is "not equal" to any reference.

### 7.3 Stability criteria (per sample = one timeframe at one boundary)
Observations `i = 0..3` (groups g0-g3) and the reference `R` (group ref). The sample is STABLE FROM `i*` if `i*` is the smallest index such that observations `i*..3` all equal `R` on the tuple. If observation 3 (+60 s) differs from `R`, the sample is UNBOUNDED within +60 s (section 8). Results are computed separately for `T_matrix`, `T_app`, `T_all`.

### 7.4 Run validity (all must hold for a COMPLETE-VALID session)
1. All observation groups of every required boundary are valid (section 5) and the per-boundary reference exists.
2. Post-session sweep: every observed candle is fetched again at least 10 minutes after the last boundary; its `T_all` tuple must equal `R` (a candle changing after +180 s makes the lag unboundable by these offsets, so it is FAILED).
3. No incident and no pacing violation.
4. Required boundary counts per day (section 9).

## 8. Lag bound, rounding, formula

All values are integer milliseconds. Per klines request `k` in observation `i` of a group, the upper bound on the true server instant of that request, relative to the boundary:
`bound_k = (S1 - T) + (mono_end_k - mono_start_S1)`, rounded UP to a whole millisecond. S1 is the server timestamp, and `mono_*` are local monotonic times (elapsed time only; the local wall clock is never used). This assumes the server and local monotonic clocks advance at the same rate over at most 4 s; V3 checks the consistency.

For a STABLE FROM `i*` sample, its time-to-stable bound is `bound_k` of the klines request of observation `i*`. Then:

- `L_obs` = the maximum of those bounds over ALL valid samples of ALL timeframes, both days, all attempts, computed for `T_app` (the recommended basis); `T_matrix` and `T_all` results are reported alongside.
- If any valid sample is UNBOUNDED within +60 s, or `L_obs > 60000`, no lag is proposed (INCONCLUSIVE, protocol amendment needed).
- Margin: `M = max(2000, L_obs)`.
- `L_raw = L_obs + M`.
- Rounding: `L = ceil(L_raw / 1000) * 1000`, i.e. ALWAYS rounded UP to a whole second, never to nearest and never down.
- `L >= 2000` always (since `M >= 2000`).

Tier table (derived from the formula, so it is consistent by construction; reviewer may raise `L`, never lower it below the formula):

| `L_obs` (ms) | `L_raw` | `L` | Examples |
|---|---|---|---|
| 0 | 2000 | 2000 | |
| 1 to 2000 | `L_obs + 2000` (2001 to 4000) | `ceil_1000(L_obs + 2000)`: 3000 to 4000 | 1 -> 3000; 1234 -> 4000; 2000 -> 4000 |
| 2001 to 10000 | `2 * L_obs` (4002 to 20000) | `ceil_1000(2 * L_obs)`: 5000 to 20000 | 2001 -> 5000; 3200 -> 7000; 10000 -> 20000 |
| 10001 to 60000 | `2 * L_obs` (20002 to 120000) | 21000 to 120000 | 10001 -> 21000; 60000 -> 120000 |
| above 60000, or any unbounded sample | none | none (INCONCLUSIVE) | 60001 -> none |

Expected floor from the measurement design: even an instantly stable candle has `bound_k` of roughly 0.7 s to 2.9 s (the klines request positions inside the group), so with the global maximum over timeframes `L_obs` is unlikely to be below about 1-3 s and `L` below about 4000-7000. This is a conservative measurement artifact, not an exchange delay; the reviewer may decide whether to accept it.

## 9. Scope: two separate UTC days and a busier market period

- Two distinct UTC calendar days, `D1` and `D2` (`D2` later than `D1`, not the same day). On EACH day both sessions are run: session X (12 consecutive 5m boundaries ending at a 4h boundary, with all four timeframes observed at that 4h boundary) and session Y (a second, different 4h boundary on the same day, all four timeframes, with 5m controls at -5 and +5 minutes). So each day on its own satisfies the matrix minimum (>= 12 consecutive 5m boundaries and >= 2 four-hour boundaries), and the lag uses all valid samples from both days.
- Eligible 4h boundaries are 04:00, 08:00, 12:00, 16:00, 20:00 UTC (00:00 is excluded so that no session straddles midnight). Session Y is a different eligible boundary on the same day, adjacent to X's boundary where possible.
- Busier market period, pre-registered and mechanical. Before each day's sessions, one klines request (BTCUSDT, 4h, `startTime = 00:00Z` of the previous UTC day, `limit = 6`) returns the previous day's six 4h candles. Among the five whose closing boundary is eligible, rank by quote asset volume (index 7, Decimal). On `D2`, session X must end at the same time of day as the closing boundary of the HIGHEST-volume window; on `D1`, at the same time of day as the LOWEST-volume window. This gives a quiet day-part and a busy day-part measured by data, not by assumption. The classification, the ranking and the chosen boundaries are written to a pre-registration file (UTC timestamped) before the session starts, and the harness refuses to start a session whose anchor boundary differs from it.
- If the pre-registered boundary has already passed, the session is run on the next UTC day instead (the day then counts as `D1` or `D2` by its own classification), not at a different time of day.

## 10. Initial lag candidates

No lag is selected or assumed. If the data show the typical structure of section 8 (stable at the first or second observation), the formula yields roughly 4000 to 7000 ms; a clearly slower exchange behavior would give the larger tiers of the table. These are only illustrations of the formula; the approved value comes from the evidence.

## 11. Execution plan and gates; relationship to other rows

1. Reviewer approves this protocol (possibly amended).
2. Harness, pacer, analysis code and offline tests (fake HTTP, fake clock, golden vectors for stability, `bound_k`, the lag formula, pacing audit and the timetable) are written and reviewed as a separate commit.
3. The owner runs OBS-01, and only if it passes, OBS-02 on both days, on their own machine with `--live`.
4. Evidence (JSONL requests, manifest with commit SHA/Python/host/UTC range/stdout/stderr/exit code/SHA-256 of every file, pre-registration file, analysis output) is returned to the reviewer; the lag is proposed from the data and approved or rejected by the reviewer.
- LAG-01/OBS-03: config keeps requiring an explicit lag until approval; `matrix.yaml` keeps `OBS-01`/`OBS-02` as `open` (a test pins this), so recording results does not edit the frozen matrix. LIVE-01..05 run only after OBS-02 and the lag are approved.

## 12. Open questions for the reviewer

1. Q1: lag basis `T_app` (recommended) versus `T_all`.
2. Q2: acceptance of the additions beyond the matrix: probes a2/e/f/g, the -30 s resync, the +180 s reference, the post-session sweep, and the +3.6 s start of the 4-timeframe g1 group.
3. Q3: numeric parameters: tolerances 2.5 s / 5.0 s, duration caps 2.0 s / 3.8 s, spacing 0.6 s, weight guard 600, margin rule `M = max(2000, L_obs)`, round-up to whole seconds.
4. Q4: is the quiet (D1) / busy (D2) contrast by quote volume an acceptable definition of a "busier market period"?
5. Q5: after approval, may the lag become a configured default (LAG-01 would need a new spec version) or must it stay explicit?
6. Q6: the fallback host `api.binance.com` is not observed. Either require a reduced OBS-02 on it, or restrict acceptance runs and any approved lag to the primary host (fallback use then fails the run).
7. Q7: confirm or correct the U1-U3 documentation conclusions in section 1.
