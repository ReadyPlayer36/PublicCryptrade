# OBS-01 / OBS-02 experiment protocol (DRAFT v0.3 for reviewer evaluation)

Status: **draft, not approved, nothing has been executed, no harness code exists, and no live request has been made.** Milestone 1 remains **BLOCKED**. No live data is collected until the reviewer approves this protocol AND a separately reviewed harness commit (section 11). Frozen files are untouched; this is a new document.

Scope: public read-only Binance Spot market data only. No keys, no orders, no private endpoints, no futures/margin.

## 0. Changes from v0.2 (reviewer findings)

| Item | Where addressed |
|---|---|
| 1. Completion-aware single pacer instead of fixed start times; expanded PACE-5 audit (completion order, non-overlap, rolling caps from monotonic timestamps) | sections 3, 5, 6 |
| 2. Exact server-time-to-monotonic estimation, uncertainty bounds, failure and fallback behavior | sections 5.2, 5.3, 6 |
| 3. Quote-volume window selection re-framed as a pre-registered historical activity proxy for time-of-day selection only | section 9 and Q4 |

Also adjusted for consistency: V3 and the `bound_k` formula (section 8) now carry the 1 ms timestamp truncation and the drift allowance `delta`.

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
- Finality-relevant times come only from `/api/v3/time`. The local MONOTONIC clock is the only local clock used (to schedule sleeps and to measure elapsed durations); the local wall clock is never used for scheduling or measurement. Production code is unchanged.
- Timeouts: connect 5 s, read 12 s (above the documented 10 s API processing timeout, so a documented -1007 response is not cut off).

## 3. Pacing rules and the completion-aware scheduler (every request, including `/time`)

A request record has: `seq` (1, 2, 3, ...), `start_ns` and `end_ns` (local MONOTONIC clock, integer nanoseconds) and an outcome (HTTP status, TIMEOUT or CONNECT_ERROR). "Completion" means the response was fully read, or an error/timeout was raised.

Rules:
- PACE-1: one request in flight; request `n+1` may start only after request `n` has completed.
- PACE-2: `start(n+1) >= start(n) + 0.6 s`.
- PACE-3: for every request start `t`, at most 2 starts in `(t - 1 s, t]` and at most 60 starts in `(t - 60 s, t]`. Timed-out and failed attempts count.
- PACE-4: one pacer object issues every request type (clock sync, observation `/time`, klines, reference, sweep, pre-registration query, OBS-01); it is the only network egress of the harness. No bypass, no exemptions.
- PACE-6 (completion-aware scheduling, no fixed start times): for the next request the pacer computes `earliest = max(end(prev), start(prev) + 0.6 s, release)`, where `release` is the earliest instant at which PACE-3 would still hold if the request started then (the oldest start leaving the 1 s or 60 s window). The request starts at `max(earliest, target)`, where `target` is the monotonic deadline of section 5.2 for the FIRST request of a group; requests inside a group have no target and start at `earliest`. The wait is a monotonic-clock sleep. The pacer never starts early and never "catches up" by shortening a gap. A slow response simply delays everything after it.
- PACE-7 (group admission): before the first request of a group, the pacer computes its earliest possible start `m_e` and the server-time interval `[m_e + theta_lo, m_e + theta_hi]` (section 5.2). If `m_e + theta_lo > T + o + tol` (the V1 window can no longer be met), the group is NOT started (outcome MISSED-WINDOW), the boundary is TIMING-INVALID and no further group of that boundary is sent.
- No retry, no request after an ABORT.

PACE-5 post-run audit (deterministic, from the recorded monotonic timestamps only). The run is INVALID-PACING (harness defect, treated as an incident, no result used) if ANY check fails:
- (a) Integrity: `seq` is contiguous from 1 to `N`; every `seq` has exactly one start and one completion record; timestamps are integers; `end_ns >= start_ns`; start times are non-decreasing in `seq`; no record exists after an ABORT.
- (b) Completion ordering and non-overlap: completions occur in the same order as starts, and `end_ns(n) <= start_ns(n+1)` for every `n` (a request never starts before the previous one completed).
- (c) Spacing: `start_ns(n+1) - start_ns(n) >= 600,000,000` for every `n` (exact integer comparison).
- (d) Rolling caps: for every `n`, the number of requests with `start_ns` in `(start_ns(n) - 1e9, start_ns(n)]` is at most 2, and in `(start_ns(n) - 60e9, start_ns(n)]` at most 60.
- (e) Durations: every duration is at most `connect timeout + read timeout + 1 s` (18 s).
- (f) Group integrity: the requests of one group are consecutive in `seq`, in the defined order (S1, 4h, 1h, 15m, 5m, S2 for a 4-timeframe group); groups of a boundary appear in order g0, g1, g2, g3, ref; no foreign request lies inside a group.
- (g) Egress check: `N` equals the number of JSONL request records, equals the request counter of the single HTTP wrapper, and equals the count in the run manifest.
- For OBS-01 the same audit applies with the spacing in (c) replaced by `>= 2,000,000,000` ns and the caps by 1 per 2 s and 30 per minute.

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

## 5. OBS-02: targets, scheduler behavior and server-time mapping

Definitions: `T` = a close boundary in server time (open time of the next candle); the observed candle has open `T - I`, close `T - 1`. OBS-02 starts only after OBS-01 has PASSED (its queries use `startTime = T - I`, `endTime = T - 1`, `limit = 1`).

An observation group for a set of timeframes is: one `/time` call (S1), then one klines request per timeframe in the order 4h, 1h, 15m, 5m (largest first: the candle most likely to be unstable is sampled earliest, which is conservative), then one `/time` call (S2). A 5m-only boundary group has 3 requests, a 4-timeframe boundary group has 6.

### 5.1 Targets (server time), not fixed start times

Per boundary, in order: resync (3 `/time` calls), then groups g0, g1, g2, g3 and the reference group `ref` with nominal offsets `o = 0, 2, 10, 60, 180` s after `T`. The target server time of a group is `X = T + o`. The first request of a group starts at the scheduler's `max(earliest, D(X))` (PACE-6), where `D(X)` is the monotonic deadline of section 5.2. The actual start of a group is whatever completion-aware scheduling produces; it is judged only by the measured `S1` (V1 below).

Indicative best-case request starts (NON-NORMATIVE; they hold only if every response completes within 0.6 s, otherwise everything shifts later and V2 or PACE-7 decide validity), seconds after `T`:

| Group | 5m-only boundary | 4-timeframe boundary |
|---|---|---|
| resync | 3 calls from `T-30 s` (1 s apart) | same |
| g0 (+0) | 0.0, 0.6, 1.2 | 0.0, 0.6, 1.2, 1.8, 2.4, 3.0 |
| g1 (+2) | 2.0, 2.6, 3.2 | 3.6 ... 6.6 (earliest slot after g0) |
| g2 (+10) | 10.0 ... 11.2 | 10.0 ... 13.0 |
| g3 (+60) | 60.0 ... 61.2 | 60.0 ... 63.0 |
| ref (+180) | 180.0 ... 181.2 | 180.0 ... 183.0 |

Because six requests cannot complete before +2 s at the allowed pace, a 4-timeframe g1 group starts at about +3.6 s instead of +2.0 s. The matrix says "approximately +2 s", so the START window is `[o, o + 2.5 s]` and +3.6 s is inside `[2.0, 4.5]`. This is the only schedule deviation and it is explicit.

Validity of one observation group (all must hold, otherwise TIMING-INVALID):
- V1 start window: `S1 - T` in `[o, o + 2.5 s]` for `o` in {0, 2, 10}, and in `[o, o + 5.0 s]` for `o` in {60, 180}. `S1` is the SERVER timestamp of the first `/time` call, measured, independent of the estimator of 5.2: an estimator error can therefore only produce a TIMING-INVALID boundary, never a silently wrong sample.
- V2 duration: local monotonic time from the start of the S1 request to the end of the S2 request is at most 2.0 s (3.8 s for the 4-timeframe group).
- V3 consistency: `S2 - S1` lies inside `[start(S2) - end(S1) - 1 ms - d, end(S2) - start(S1) + 1 ms + d]` of the local monotonic clock, where `d = delta x (end(S2) - start(S1))`. A violation means a server/local rate anomaly.
- V4 every request returned HTTP 200 within the timeout with a well-formed body.

Request counts (estimates; a skipped boundary sends fewer): 5m-only boundary 3 + 15 = 18; 4-timeframe boundary 3 + 30 = 33. Session X (12 consecutive 5m boundaries ending at a 4h boundary) 11 x 18 + 33 = 231, plus initial sync 10, plus sweep 15: about 256. Session Y (a second 4h boundary with 5m controls at -5 and +5 minutes) 18 + 33 + 18 = 69, plus 10 and 6: about 85. One day about 342 (with the pre-registration query); two days about 685; with OBS-01 (66) about 750. The caps in section 3 hold regardless; for reference, in the best case any 60 s window holds at most 21 starts and 33 weight.

### 5.2 Mapping server time to local monotonic deadlines

Notation. All times in milliseconds (converted from monotonic ns). For every `/time` call `j` (resync, S1, S2, initial sync): `a_j` = monotonic start, `b_j` = monotonic end, `s_j` = the integer `serverTime` returned. The server generated its timestamp at an unknown monotonic instant `g_j` in `[a_j, b_j]`, and the true server time at that instant lies in `[s_j, s_j + 1)` because the timestamp is truncated to whole milliseconds.

Offset model. `server_time = mono + theta`, with `theta` an unknown constant (plus a bounded rate error, below). Each sample bounds it:
`theta in I_j = [ s_j - b_j , s_j + 1 - a_j ]`, width `RTT_j + 1 ms`.

Drift allowance (assumption, documented): the server and local monotonic clocks advance at rates that differ by at most `delta = 100 ppm` (1e-4). At a later monotonic time `t >= b_j` the interval of sample `j` is widened:
`I_j(t) = [ s_j - b_j - delta (t - b_j) , s_j + 1 - a_j + delta (t - a_j) ]`.

Estimator at time `t` (the decision time):
- Sample set: every `/time` call of the run with `b_j >= t - 600 s` (the 3 resync calls, every S1 and S2, the initial sync calls).
- `Theta(t) = intersection of I_j(t)` = `[theta_lo, theta_hi]` with `theta_lo = max_j lower_j(t)` and `theta_hi = min_j upper_j(t)`.
- Uncertainty `w(t) = theta_hi - theta_lo`. The midpoint is logged for diagnostics ONLY and is never used in any decision.

Deadlines (the exact rule). To start a request whose SERVER timestamp is certainly not earlier than the target server time `X`, the request must start at monotonic `m >= D(X)` with
`D(X) = X - theta_lo(m)`,
because for any monotonic time `m' >= m` the server time is at least `m' + theta_lo >= X`. `theta_lo` decreases slowly with time through the `delta` term, so `D` is evaluated as a fixed point: sleep until `D(X)` computed at the current time, wake, recompute with the current time, sleep again if the deadline moved later, and stop when `now >= D(now)`. The server-time upper side used by PACE-7 is `m + theta_hi`.
Lateness caused by the estimator is at most `w + wake latency`; with `w <= W_max = 250 ms` (below) this is far inside the 2.5 s V1 window.

Boundary anchors: `T` is a server-time epoch value (multiple of `I`). The resync calls start at the deadline `D(T - 30 s)` and must complete before `T - 10 s`. The decision time for the boundary is `T - 10 s`.

### 5.3 Failure and fallback behavior when synchronization is inadequate

- SYNC-ADEQUATE at the decision time iff `Theta` is non-empty AND `w <= W_max = 250 ms`.
- Start of run: at least 10 `/time` calls, 1 s apart, are made first. If not SYNC-ADEQUATE after them, the run does not start (SYNC-INADEQUATE-AT-START).
- Before a boundary, if not SYNC-ADEQUATE after the 3 resync calls, up to 4 additional `/time` calls (1 s apart, all before `T - 10 s`) are made.
- If `Theta` is empty, samples older than 60 s are discarded and `Theta` is recomputed once. Still empty means a clock jump or a rate difference above `delta`.
- If still not SYNC-ADEQUATE at `T - 10 s`: the boundary is SYNC-SKIPPED: no group request is sent, the boundary is TIMING-INVALID, and the scheduler goes on to the next boundary's resync.
- If 3 consecutive boundaries are SYNC-SKIPPED or MISSED-WINDOW, the session stops as INCONCLUSIVE-TIMING (the environment is unfit; this is not an incident).
- There is NO fallback to the local wall clock, to NTP, or to the estimator midpoint for any decision. The only fallback is to skip. The wall clock is never read for scheduling or measurement (it may appear in logs, labeled diagnostic). A monotonic-clock regression (`end < start`, or a decreasing timestamp) is INVALID-PACING.
- A sleep that wakes more than 500 ms after its deadline is recorded as a diagnostic; whether the group is usable is decided only by V1-V4.
- The parameters `delta`, `W_max`, the 600 s window, the 60 s fallback window, the 10-sample start, the 4 extra samples and the 3-boundary stop are written into the run manifest.

## 6. Deterministic outcomes when timing windows cannot be met

Every classification below is computed by the pure analysis function from the evidence files; no human judgment is involved.

| Event | Classification |
|---|---|
| V1 early or late, V2 exceeded, V3 violated, a timeout or connection failure on any request in the group | the group is TIMING-INVALID; its boundary is TIMING-INVALID (kept in the evidence, never counted) |
| PACE-7 admission fails (V1 window can no longer be met) | MISSED-WINDOW: the group and the rest of the boundary are not sent; boundary TIMING-INVALID |
| not SYNC-ADEQUATE at `T - 10 s` (section 5.3) | SYNC-SKIPPED: no group sent; boundary TIMING-INVALID; 3 in a row stop the session as INCONCLUSIVE-TIMING |
| not SYNC-ADEQUATE after the initial 10 samples | SYNC-INADEQUATE-AT-START: the run does not start |
| 3 consecutive requests without an HTTP response | ABORT (INCIDENT-NETWORK), run stops |
| HTTP status other than 200 (including 403, 418, 429, any 3xx, any 5xx), non-JSON, wrong shape, wrong host/path, a row with a wrong open time, `X-MBX-USED-WEIGHT-1M` above 600, server time going backwards by more than 1 s | ABORT (INCIDENT), cooldown written for 418/429, owner reports to the reviewer before any rerun |
| any PACE-5 check (a)-(g) of section 3 fails in the post-run audit, or a monotonic regression is seen | INVALID-PACING, whole run unusable, reported as a harness defect |
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
`bound_k = (s1 - T) + 1 + ceil((mono_end_k - mono_start_S1) x (1 + delta))` milliseconds, where `s1` is the integer server timestamp of S1 (the `+ 1` covers its truncation to whole milliseconds), `mono_*` are local monotonic times (elapsed time only; the local wall clock is never used) and `delta = 100 ppm` is the drift allowance of section 5.2. V3 checks the consistency of S1 and S2 with the local elapsed time.

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

## 9. Scope: two separate UTC days and the time-of-day anchor

- Two distinct UTC calendar days, `D1` and `D2` (`D2` later than `D1`). On EACH day both sessions are run: session X (12 consecutive 5m boundaries ending at a 4h boundary, with all four timeframes observed at that 4h boundary) and session Y (a second, different 4h boundary on the same day, all four timeframes, with 5m controls at -5 and +5 minutes). Each day on its own therefore satisfies the matrix minimum (>= 12 consecutive 5m boundaries and >= 2 four-hour boundaries), and the lag uses all valid samples from both days.
- Eligible 4h boundaries are 04:00, 08:00, 12:00, 16:00, 20:00 UTC (00:00 is excluded so that no session straddles midnight). Session Y is a different eligible boundary on the same day, adjacent to X's where possible.
- Time-of-day anchor from a historical activity PROXY (pre-registered). Before each day's sessions, one klines request (BTCUSDT, 4h, `startTime = 00:00Z` of the previous UTC day, `limit = 6`) returns the previous UTC day's six 4h candles. Among the five whose closing boundary is eligible, rank by quote asset volume (index 7, Decimal). On `D1` session X ends at the same time of day as the closing boundary of the LOWEST-proxy window; on `D2` at the same time of day as the HIGHEST-proxy window. The ranking, the chosen boundaries and a UTC timestamp are written to a pre-registration file before the session starts, and the harness refuses to start a session whose anchor boundary differs from it.
- What this does and does not mean. The rule only chooses times of day, from past data, in a way that cannot be tuned after the fact. It does NOT guarantee that the live session on that day is quiet or busy, calm or volatile; yesterday's volume at a time of day is a proxy, not a forecast. The protocol makes no claim about live activity or volatility, and no pass/fail criterion or lag formula depends on it. The labels used in the evidence are "LOW-proxy" and "HIGH-proxy", never "quiet" or "busy".
- Realized activity is reported descriptively: for every observed candle the reference row gives quote volume and trade count; the report tabulates them per session and the ratio to the proxy window's previous-day quote volume. The reviewer can use this to judge afterwards whether the HIGH-proxy session really was more active (Q4).
- If the pre-registered boundary has already passed, the session is run on the next UTC day instead (that day then gets its own classification), not at a different time of day.

## 10. Initial lag candidates

No lag is selected or assumed. If the data show the typical structure of section 8 (stable at the first or second observation), the formula yields roughly 4000 to 7000 ms; a clearly slower exchange behavior would give the larger tiers of the table. These are only illustrations of the formula; the approved value comes from the evidence.

## 11. Execution plan and gates; relationship to other rows

1. Reviewer approves this protocol (possibly amended).
2. Harness, pacer, analysis code and offline tests (fake HTTP, fake monotonic clock, golden vectors for stability, `bound_k`, the lag formula, the full PACE-5 audit, the interval-intersection estimator including empty-intersection and wide-uncertainty cases, group admission and the skip rules) are written and reviewed as a separate commit.
3. The owner runs OBS-01, and only if it passes, OBS-02 on both days, on their own machine with `--live`.
4. Evidence (JSONL requests, manifest with commit SHA/Python/host/UTC range/stdout/stderr/exit code/SHA-256 of every file, pre-registration file, analysis output) is returned to the reviewer; the lag is proposed from the data and approved or rejected by the reviewer.
- LAG-01/OBS-03: config keeps requiring an explicit lag until approval; `matrix.yaml` keeps `OBS-01`/`OBS-02` as `open` (a test pins this), so recording results does not edit the frozen matrix. LIVE-01..05 run only after OBS-02 and the lag are approved.

## 12. Open questions for the reviewer

1. Q1: lag basis `T_app` (recommended) versus `T_all`.
2. Q2: acceptance of the additions beyond the matrix: probes a2/e/f/g, the -30 s resync, the +180 s reference, the post-session sweep, and the later start of the 4-timeframe g1 group.
3. Q3: numeric parameters: start tolerances 2.5 s / 5.0 s, duration caps 2.0 s / 3.8 s, spacing 0.6 s, weight guard 600, margin `M = max(2000, L_obs)`, round-up to whole seconds.
4. Q4: is a pre-registered historical proxy (LOW-proxy on `D1`, HIGH-proxy on `D2`) an acceptable reading of "a busier market period"? Stronger alternative if the reviewer wants a guarantee: require the realized `D2` session activity (quote volume of the observed candles) to exceed `D1`'s by a pre-set ratio, otherwise repeat on another day; this may need several days and is not proposed by default.
5. Q5: after approval, may the lag become a configured default (LAG-01 would need a new spec version) or must it stay explicit?
6. Q6: the fallback host `api.binance.com` is not observed. Either require a reduced OBS-02 on it, or restrict acceptance runs and any approved lag to the primary host (fallback use then fails the run).
7. Q7: confirm or correct the U1-U3 documentation conclusions in section 1.
8. Q8: synchronization parameters: drift allowance `delta = 100 ppm`, `W_max = 250 ms`, 600 s sample window, 4 extra samples, stop after 3 consecutive skipped boundaries.
