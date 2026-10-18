"""Application service: download, validate, then save candles and the audit record atomically.

Order of operations (frozen requirement TX-09): ALL network I/O, finality checks and full
validation (including hashing) finish first; only then one short ``BEGIN IMMEDIATE``
transaction saves the candles and the success audit row together. A failure at any point
leaves no candle and no success row; a separate failure audit row is attempted afterwards
and can never mask or replace the original exception.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from trading_app.config import Settings
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient
from trading_app.data.finality import EmptyEffectiveRangeError, NaiveDatetimeError, NonFinalCandleError
from trading_app.data.hashing import hash_candles
from trading_app.data.repository import CandleConflictError, CandleRepository, TooManyCandlesError, _from_ms, to_ms
from trading_app.data.schemas import Candle
from trading_app.data.validator import DataValidationError

logger = logging.getLogger("trading_app.service")

_CONFLICT_FIELDS = {"close_time", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"}


def safe_error_text(exc: BaseException) -> str:
    """Fixed-vocabulary description of a failure. Never echoes the exception message, so it
    cannot carry URLs, response bodies, candle values, headers or secrets."""
    message = str(exc)
    if isinstance(exc, CandleConflictError):
        fields = sorted(set(re.findall(r"[a-z_]+", (re.findall(r"(?:different in|fields differ): ([a-z_, ]+)", message) or [""])[0])) & _CONFLICT_FIELDS)
        return "candle conflict with stored data" + (f" in fields: {', '.join(fields)}" if fields else "")
    if isinstance(exc, DataValidationError):
        codes = sorted(set(re.findall(r"\[([A-Z][A-Z_]{2,40})\]", message)))[:12]
        return "market-data validation failed" + (f": {', '.join(codes)}" if codes else "")
    if isinstance(exc, NonFinalCandleError):
        return "upstream returned a non-final candle"
    if isinstance(exc, EmptyEffectiveRangeError):
        return "effective range is empty (requested candles are not final yet)"
    if isinstance(exc, NaiveDatetimeError):
        return "naive datetime rejected"
    if isinstance(exc, TooManyCandlesError):
        return "fetch exceeds max_candles_per_fetch"
    if isinstance(exc, BinanceClientError):
        statuses = sorted(set(re.findall(r"HTTP (\d{3})", message)))
        parts = ["binance request failed"]
        if statuses:
            parts.append("HTTP " + "/".join(statuses))
        for needle, label in (("cooldown active", "cooldown active"), ("sleep budget", "sleep budget exceeded"),
                              ("failing closed", "failing closed"), ("finality lag is not configured", "finality lag not configured"),
                              ("timeout", "timeout"), ("connect", "connect failure")):
            if needle in message:
                parts.append(label)
        return ": ".join(parts[:1]) + (" (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else "")
    if isinstance(exc, ValueError):
        return "invalid input rejected"
    return "unexpected internal error"


class MarketDataService:
    """Application service for historical market-data ingestion."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: BinanceMarketDataClient,
        repository: CandleRepository,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.repository = repository
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))     # audit timestamps only; never used for finality

    def download_and_store(self, *, symbol: str, timeframe: str, start: datetime, end: datetime) -> int:
        """Return the number of NEW candles stored (0 on an idempotent rerun)."""
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a string")
        symbol = symbol.upper()
        if symbol not in self.settings.allowed_symbols:
            raise ValueError(f"Symbol {symbol!r} is not configured.")
        if timeframe not in self.settings.allowed_timeframes:
            raise ValueError(f"Timeframe {timeframe!r} is not configured.")
        requested_start_ms, requested_end_ms = to_ms(start), to_ms(end)

        row_count = 0          # rows fetched AND fully verified (client checks + service conversion); 0 until then
        try:
            rows = self.client.get_historical_klines(symbol=symbol, timeframe=timeframe, start=start, end=end)
            candles, records = self._normalize(rows, symbol, timeframe)          # full validation BEFORE any write
            row_count = len(candles)      # "verified" = the client's checks AND this service's own conversion both passed
            digest = hash_candles(records)
            fetch = self._fetch_record(symbol, timeframe, requested_start_ms, requested_end_ms, status="success",
                                       row_count=row_count, dataset_sha256=digest)
            return self.repository.insert_candles_with_fetch(candles, fetch)     # one short BEGIN IMMEDIATE transaction
        except Exception as exc:
            self._record_failure(exc, symbol, timeframe, requested_start_ms, requested_end_ms, row_count)
            raise

    # ---- helpers ---------------------------------------------------------------
    def _fetch_record(self, symbol: str, timeframe: str, requested_start_ms: int, requested_end_ms: int, *, status: str,
                      row_count: int = 0, dataset_sha256: str | None = None, error_class: str | None = None,
                      error_text: str | None = None) -> dict[str, Any]:
        info = getattr(self.client, "last_fetch", None)
        return {
            "symbol": symbol, "timeframe": timeframe,
            "requested_start_ms": requested_start_ms, "requested_end_ms": requested_end_ms,
            "effective_start_ms": info.effective_start_ms if info else None,
            "effective_end_ms": info.effective_end_ms if info else None,
            "server_time_ms": info.server_time_ms if info else None,
            "finality_lag_ms": info.finality_lag_ms if info else getattr(self.client, "finality_lag_ms", None),
            "host": info.host if info else None,
            "row_count": row_count, "dataset_sha256": dataset_sha256,
            "status": status, "error_class": error_class, "error_text": error_text,
            "fetched_at_ms": self._now_ms(),
        }

    def _record_failure(self, exc: BaseException, symbol: str, timeframe: str, start_ms: int, end_ms: int, row_count: int = 0) -> None:
        """Best-effort failure audit, attempted AFTER the candle transaction has rolled back. Never raises."""
        try:
            record = self._fetch_record(symbol, timeframe, start_ms, end_ms, status="failed", row_count=row_count,
                                        error_class=type(exc).__name__, error_text=safe_error_text(exc))
            self.repository.record_failed_fetch(record)
        except Exception as audit_exc:      # the original exception must always win
            logger.error("failure audit could not be written error_type=%s", type(audit_exc).__name__)

    @staticmethod
    def _normalize(rows: list[list[Any]], symbol: str, timeframe: str) -> tuple[list[Candle], list[dict[str, Any]]]:
        candles: list[Candle] = []
        records: list[dict[str, Any]] = []
        malformed: int | None = None
        for index, row in enumerate(rows):
            try:
                open_ms, close_ms = int(row[0]), int(row[6])
                candles.append(Candle(
                    symbol=symbol, timeframe=timeframe, open_time=_from_ms(open_ms), close_time=_from_ms(close_ms),
                    open=Decimal(str(row[1])), high=Decimal(str(row[2])), low=Decimal(str(row[3])), close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])), quote_volume=Decimal(str(row[7])), trade_count=int(row[8]),
                ))
                records.append({
                    "symbol": symbol, "timeframe": timeframe, "open_time_ms": open_ms, "close_time_ms": close_ms,
                    "open": str(row[1]), "high": str(row[2]), "low": str(row[3]), "close": str(row[4]),
                    "volume": str(row[5]), "quote_volume": str(row[7]), "trade_count": int(row[8]),
                })
            except Exception:           # IndexError, TypeError, ValueError, decimal.InvalidOperation, pydantic errors...
                malformed = index
            if malformed is not None:
                break
        if malformed is not None:      # raised outside the except block: no cause/context can carry row values
            raise DataValidationError(f"[MALFORMED_ROW] row {malformed} could not be converted")
        return candles, records
