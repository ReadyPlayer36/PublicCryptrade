"""Public Binance Spot market-data client (no credentials, no private endpoints).

Stage B2: request engine (retry, backoff, Retry-After, sleep budget, host fallback,
cooldown) and ``get_server_time``. ``get_historical_klines`` is not implemented yet.

Design decisions (see docs/stage2-test-decisions.md):
* ``now_ms`` is used ONLY for cooldown timestamps; finality never uses the local clock.
* ``cooldown_path=None`` keeps cooldown in memory for the client's lifetime; production
  wiring must pass the configured file path so cooldown is global across processes.
* The sleep budget and host lock are per fetch; the fetch owner calls ``begin_fetch()``.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from trading_app.data.finality import (
    EmptyEffectiveRangeError,
    NaiveDatetimeError,
    NonFinalCandleError,
    effective_end_ms,
    is_final,
)
from trading_app.data.validator import DataValidationError, timeframe_to_ms, validate_klines
from trading_app.data.cooldown import (
    CorruptCooldownError,
    cooldown_duration_s,
    extend_cooldown,
    read_cooldown,
)

PRIMARY_HOST = "data-api.binance.vision"
FALLBACK_HOST = "api.binance.com"
ALLOWED_HOSTS = (PRIMARY_HOST, FALLBACK_HOST)
TIME_PATH = "/api/v3/time"
KLINES_PATH = "/api/v3/klines"
ALLOWED_PATHS = (TIME_PATH, KLINES_PATH)

ATTEMPTS_TOTAL = 4
RETRY_STATUSES = frozenset({500, 502, 503, 504, 429})
BACKOFF_BASE_S = 1
BACKOFF_FACTOR = 2
BACKOFF_CAP_S = 3
JITTER_MAX_S = 1
RETRY_AFTER_MAX_S = 60
SLEEP_BUDGET_S = 30
KLINES_PAGE_LIMIT = 1000
logger = logging.getLogger("trading_app.binance_client")
# Logging policy: only fixed labels, counts and status codes. Never URLs, headers, params,
# exception text, response bodies, or anything secret-like.
_DIGITS = re.compile(r"[0-9]+")
_SYMBOL = re.compile(r"[A-Z0-9]{2,20}")


class BinanceClientError(RuntimeError):
    """Raised when Binance public market-data access fails."""


def _split_allowed_https(url: str):
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise ValueError("url must use https")
    if parts.username is not None or parts.password is not None:
        raise ValueError("url must not contain credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("url has an invalid port") from exc
    if port is not None:
        raise ValueError("url must not specify a port")
    if parts.query or parts.fragment:
        raise ValueError("url must not contain a query or fragment")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host {host!r} is not an allowed public Binance Spot market-data host")
    return host, parts.path


def validate_base_url(url: str) -> str:
    """Return the normalized https origin for an allowed host (no path allowed)."""
    host, path = _split_allowed_https(url)
    if path not in ("", "/"):
        raise ValueError("base_url must be a bare origin (no path)")
    return f"https://{host}"


def validate_public_url(url: str) -> bool:
    """True only for https://<allowed host>/api/v3/time or /api/v3/klines, exactly."""
    _, path = _split_allowed_https(url)
    if path not in ALLOWED_PATHS:
        raise ValueError(f"path {path!r} is not an allowed exact path")
    return True


def _retry_after_s(response: Any) -> int | None:
    """Integer seconds from a Retry-After header; absent or unparsable means None."""
    for name, value in dict(response.headers).items():
        if str(name).lower() == "retry-after":
            text = str(value).strip()
            return int(text) if _DIGITS.fullmatch(text) else None
    return None


class BinanceMarketDataClient:
    """Binance public Spot market-data client. No credentials are used."""

    def __init__(
        self,
        *,
        base_url: str,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
        sleep: Callable[[float], None] | None = None,
        jitter: Callable[[], float] | None = None,
        now_ms: Callable[[], int] | None = None,
        cooldown_path: str | Path | None = None,
        finality_lag_ms: int | None = None,
    ) -> None:
        self._origin = validate_base_url(base_url)
        if finality_lag_ms is not None and (
            isinstance(finality_lag_ms, bool) or not isinstance(finality_lag_ms, int) or finality_lag_ms < 0
        ):
            raise ValueError("finality_lag_ms must be an int >= 0 or None")
        self.finality_lag_ms = finality_lag_ms
        self._sleep = sleep or time.sleep
        self._jitter = jitter or (lambda: random.uniform(0.0, JITTER_MAX_S))
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._cooldown_path = Path(cooldown_path) if cooldown_path is not None else None
        self._cooldown_until_ms = 0
        self._owns_http_client = http_client is None
        self.http_client = http_client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "binance-research/0.1"},
        )
        self.begin_fetch()

    # ---- lifecycle -------------------------------------------------------
    def close(self) -> None:
        if self._owns_http_client:
            self.http_client.close()

    def __enter__(self) -> "BinanceMarketDataClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def begin_fetch(self) -> None:
        """Reset per-fetch state: sleep budget, host lock and fallback allowance."""
        self._fetch_sleep_s: float = 0.0
        self._host = PRIMARY_HOST if self._origin.endswith(PRIMARY_HOST) else FALLBACK_HOST
        self._host_locked = False
        self._fallback_used = False

    # ---- cooldown --------------------------------------------------------
    def _check_cooldown(self) -> None:
        until, reason = self._cooldown_until_ms, "in-memory"
        if self._cooldown_path is not None:
            corrupt = False
            try:
                state = read_cooldown(self._cooldown_path)
            except CorruptCooldownError:
                corrupt = self._cooldown_path.exists()
            else:
                if state["until_ms"] > until:
                    until, reason = state["until_ms"], state["reason"]
            if corrupt:   # raised outside the except block: no cause/context carries file content
                raise BinanceClientError("cooldown state unreadable or invalid; failing closed")
        if until > self._now_ms():
            raise BinanceClientError(f"cooldown active until {until} ms ({reason}); no request sent")

    def _trip_cooldown(self, trigger: str, retry_after_s: int | None) -> str:
        """Persist a cooldown; returns a note for the error message."""
        until = self._now_ms() + cooldown_duration_s(trigger, retry_after_s) * 1000
        until = max(until, self._cooldown_until_ms)
        self._cooldown_until_ms = until
        logger.warning("binance cooldown set trigger=%s until_ms=%d", trigger, until)
        if self._cooldown_path is None:
            return f"cooldown set until {until} ms ({trigger})"
        try:
            in_force = extend_cooldown(self._cooldown_path, {"until_ms": until, "reason": trigger})
        except OSError as exc:
            logger.error("binance cooldown could not be persisted error_type=%s", type(exc).__name__)
            return f"cooldown set in memory until {until} ms ({trigger}) but could not be persisted ({type(exc).__name__})"
        if in_force["until_ms"] > until:
            return f"cooldown already active until {in_force['until_ms']} ms"
        return f"cooldown persisted until {until} ms ({trigger})"

    # ---- request engine --------------------------------------------------
    def _backoff_s(self, attempt: int) -> float:
        jitter = self._jitter()
        if isinstance(jitter, bool) or not 0 <= jitter <= JITTER_MAX_S:
            raise ValueError(f"jitter must be within [0, {JITTER_MAX_S}]")
        return min(BACKOFF_CAP_S, BACKOFF_BASE_S * BACKOFF_FACTOR**attempt) + jitter

    def _wait(self, seconds: float, reason: str) -> None:
        if self._fetch_sleep_s + seconds > SLEEP_BUDGET_S:
            raise BinanceClientError(
                f"per-fetch sleep budget of {SLEEP_BUDGET_S}s would be exceeded; aborting after: {reason}"
            )
        self._fetch_sleep_s += seconds
        self._sleep(seconds)

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(ATTEMPTS_TOTAL):
            self._check_cooldown()  # before EVERY attempt, including retries after a sleep
            last = attempt == ATTEMPTS_TOTAL - 1
            url = f"https://{self._host}{path}"
            validate_public_url(url)
            wait: float | None = None
            fatal_type: str | None = None
            try:
                response = self.http_client.get(url, params=params or {})
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if not self._host_locked and not self._fallback_used and self._host == PRIMARY_HOST:
                    self._host, self._fallback_used = FALLBACK_HOST, True
                    reason, wait = f"connect failure on {PRIMARY_HOST}; switched to fallback host", 0.0
                else:
                    reason = f"connect failure ({type(exc).__name__})"
            except (httpx.TimeoutException, TimeoutError) as exc:
                reason = f"timeout ({type(exc).__name__})"
            except (httpx.HTTPError, OSError) as exc:
                fatal_type = type(exc).__name__   # keep only the type; the text can embed URLs/userinfo/query strings
            else:
                status = response.status_code
                if 200 <= status < 300:
                    try:
                        return response.json()
                    except ValueError:
                        reason = "malformed JSON response"
                elif 300 <= status < 400:
                    raise BinanceClientError(f"unexpected redirect HTTP {status}; redirects are never followed")
                elif status == 418:
                    ra = _retry_after_s(response)
                    note = self._trip_cooldown("418", ra)
                    raise BinanceClientError(f"HTTP 418 (IP banned); {note}")
                elif status == 429:
                    ra = _retry_after_s(response)
                    if ra is not None and ra > RETRY_AFTER_MAX_S:
                        note = self._trip_cooldown("429_retry_after_over_60", ra)
                        raise BinanceClientError(f"HTTP 429 rate limit: Retry-After {ra}s exceeds {RETRY_AFTER_MAX_S}s; {note}")
                    if last:
                        note = self._trip_cooldown("429_exhausted", ra)
                        raise BinanceClientError(f"HTTP 429 rate limit persisted after {ATTEMPTS_TOTAL} attempts; {note}")
                    seconds = ra if ra is not None else self._backoff_s(attempt)
                    if self._fetch_sleep_s + seconds > SLEEP_BUDGET_S:
                        note = self._trip_cooldown("429_retry_after_exceeds_sleep_budget", ra)
                        raise BinanceClientError(f"HTTP 429 rate limit: sleep budget of {SLEEP_BUDGET_S}s exceeded; {note}")
                    logger.warning("binance retry endpoint=%s attempt=%d reason=http_429 wait_s=%s", path.rsplit("/", 1)[-1], attempt + 1, seconds)
                    self._fetch_sleep_s += seconds
                    self._sleep(seconds)
                    continue
                elif status in RETRY_STATUSES:
                    reason = f"HTTP {status}"
                else:
                    raise BinanceClientError(f"HTTP {status} is not retryable")
            if fatal_type is not None:   # raised outside the except block: no __context__ / __cause__ leak
                raise BinanceClientError(f"request to {path} failed without retry: {fatal_type}")
            if last:
                raise BinanceClientError(f"Binance request to {path} failed after {ATTEMPTS_TOTAL} attempts: {reason}")
            logger.warning("binance retry endpoint=%s attempt=%d reason=%s", path.rsplit("/", 1)[-1], attempt + 1, reason)
            self._wait(self._backoff_s(attempt) if wait is None else wait, reason)
        raise AssertionError("unreachable")  # pragma: no cover

    # ---- public API ------------------------------------------------------
    def get_server_time(self) -> int:
        """Return Binance server time in ms. Fails closed; never uses the local clock."""
        payload = self._request_json(TIME_PATH)
        value = payload.get("serverTime") if isinstance(payload, dict) else None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BinanceClientError("server-time response has no valid integer serverTime")
        self._host_locked = True
        return value

    def get_historical_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[list[Any]]:
        """Download final candles for [start, end) as raw Binance rows, fully validated.

        One server-time snapshot S per fetch; B = S - lag; only candles with
        close_time_ms < B are accepted. A non-final row aborts the fetch. An empty
        response for a non-empty effective range raises DataValidationError (EMPTY_RESULT).
        """
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise ValueError(f"invalid symbol: {symbol!r}")
        interval_ms = timeframe_to_ms(timeframe)
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise ValueError("start and end must be datetimes")
        if start.tzinfo is None or end.tzinfo is None:
            raise NaiveDatetimeError("start and end must be timezone-aware (naive datetimes are rejected)")
        start_ms = int(start.astimezone(timezone.utc).timestamp() * 1000)
        end_ms = int(end.astimezone(timezone.utc).timestamp() * 1000)
        if end_ms <= start_ms:
            raise ValueError("end must be after start")
        for name, value in (("start", start_ms), ("end", end_ms)):
            if value % interval_ms != 0:
                raise ValueError(f"{name} is not aligned to {timeframe}")

        self.begin_fetch()
        server_time_ms = self.get_server_time()          # the single S snapshot for this fetch
        if self.finality_lag_ms is None:
            raise BinanceClientError("finality lag is not configured; refusing to fetch without an explicit finality_lag_ms")
        lag_ms = self.finality_lag_ms
        boundary_ms = server_time_ms - lag_ms
        end_effective = effective_end_ms(end_ms, server_time_ms, lag_ms, interval_ms)
        if end_effective <= start_ms:
            raise EmptyEffectiveRangeError(
                f"effective range is empty: effective_end {end_effective} <= start {start_ms}"
            )

        rows: list[list[Any]] = []
        cursor = start_ms
        while cursor < end_effective:
            page = self._request_json(KLINES_PATH, {
                "symbol": symbol, "interval": timeframe, "startTime": cursor,
                "endTime": end_effective - 1, "limit": KLINES_PAGE_LIMIT,
            })
            if not isinstance(page, list) or len(page) > KLINES_PAGE_LIMIT or not all(isinstance(r, list) for r in page):
                raise BinanceClientError("klines response has an invalid shape")
            if not page:
                break
            self._reject_nonfinal(page, boundary_ms)
            issues = validate_klines(page, symbol=symbol, timeframe=timeframe, expected_start_ms=cursor)
            if issues:
                raise DataValidationError("Suspicious Binance page:\n" + "\n".join(f"[{i.code}] {i.message}" for i in issues))
            last_open = int(page[-1][0])
            if last_open >= end_effective:
                raise DataValidationError(f"Binance returned candle {last_open} outside requested range ending {end_effective}")
            rows.extend(page)
            cursor = last_open + interval_ms

        # Always validate, including an empty result: an empty response for a non-empty
        # effective range is rejected (EMPTY_RESULT), never silently returned.
        issues = validate_klines(rows, symbol=symbol, timeframe=timeframe,
                                 expected_start_ms=start_ms, expected_end_ms_exclusive=end_effective)
        if issues:
            raise DataValidationError(
                f"Market-data validation failed for {symbol} {timeframe}:\n"
                + "\n".join(f"[{i.code}] {i.message}" for i in issues)
            )
        return rows

    @staticmethod
    def _reject_nonfinal(page: list[list[Any]], boundary_ms: int) -> None:
        for index, row in enumerate(page):
            try:
                close_ms = int(row[6])
            except (IndexError, TypeError, ValueError):
                continue  # structural problems are reported by the validator
            if not is_final(close_ms, boundary_ms, 0):
                raise NonFinalCandleError(
                    f"non-final candle returned (row {index}, close_time_ms {close_ms} >= finality boundary {boundary_ms})"
                )
