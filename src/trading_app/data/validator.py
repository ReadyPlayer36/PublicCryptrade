"""Raw Binance kline validation. Detects problems; never repairs data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

TIMEFRAME_MS: dict[str, int] = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}


class DataValidationError(ValueError):
    """Raised when market data fails validation."""


@dataclass(frozen=True)
class ValidationIssue:
    """A concrete data-quality problem."""

    code: str
    message: str
    index: int | None = None
    open_time_ms: int | None = None


def timeframe_to_ms(timeframe: str) -> int:
    try:
        return TIMEFRAME_MS[timeframe]
    except KeyError as exc:
        raise DataValidationError(f"Unsupported timeframe: {timeframe!r}") from exc


def parse_decimal(value: Any, *, field_name: str, index: int) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DataValidationError(
            f"Row {index}: {field_name} is not a valid decimal: {value!r}"
        ) from exc
    if not result.is_finite():
        raise DataValidationError(f"Row {index}: {field_name} must be finite: {value!r}")
    return result


def _to_int(value: Any) -> int:
    """Strict integer conversion: no bools, no truncation, no non-finite values."""
    if isinstance(value, bool):
        raise ValueError("bool is not an integer field")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text.lstrip("+-").isascii() or not text.lstrip("+-").isdigit():
            raise ValueError(f"not an integer string: {value!r}")
        return int(text)
    if isinstance(value, (float, Decimal)):
        number = Decimal(value) if isinstance(value, float) else value
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError(f"not a finite integral number: {value!r}")
        return int(number)
    raise TypeError(f"unsupported integer type: {type(value).__name__}")


def validate_klines(
    rows: Sequence[Sequence[Any]],
    *,
    symbol: str,
    timeframe: str,
    expected_start_ms: int | None = None,
    expected_end_ms_exclusive: int | None = None,
) -> list[ValidationIssue]:
    """Validate raw Binance kline rows and return every issue found."""
    interval_ms = timeframe_to_ms(timeframe)
    issues: list[ValidationIssue] = []

    def add(code: str, message: str, index: int | None, open_ms: int | None = None) -> None:
        issues.append(ValidationIssue(code=code, message=message, index=index, open_time_ms=open_ms))

    for name, bound in (("expected_start_ms", expected_start_ms), ("expected_end_ms_exclusive", expected_end_ms_exclusive)):
        if bound is not None and bound % interval_ms != 0:
            add("INVALID_EXPECTED_RANGE", f"{name} {bound} is not aligned to {timeframe}.", None)

    seen: set[int] = set()
    previous_open: int | None = None
    first_open: int | None = None
    last_open: int | None = None

    for index, row in enumerate(rows):
        if len(row) < 12:
            add("MALFORMED_ROW", f"Row {index} contains {len(row)} fields; expected at least 12.", index)
            continue
        try:
            open_ms = _to_int(row[0])
            close_ms = _to_int(row[6])
        except (TypeError, ValueError):
            add("INVALID_TIMESTAMP", f"Row {index} contains invalid timestamps.", index)
            continue

        if first_open is None:
            first_open = open_ms
        last_open = open_ms

        if open_ms in seen:
            add("DUPLICATE_CANDLE", f"Duplicate candle for {symbol} {timeframe} at {open_ms}.", index, open_ms)
        seen.add(open_ms)

        if open_ms % interval_ms != 0:
            add("MISALIGNED_TIMESTAMP", f"Row {index}: open timestamp {open_ms} is not aligned to {timeframe}.", index, open_ms)
        if close_ms <= open_ms:
            add("INVALID_CLOSE_TIME", f"Row {index}: close time {close_ms} is not after open time {open_ms}.", index, open_ms)
        if close_ms != open_ms + interval_ms - 1:
            add("INVALID_CANDLE_DURATION", f"Row {index}: close time does not match {timeframe} interval.", index, open_ms)

        prices: dict[str, Decimal] = {}
        for field_index, name in ((1, "open"), (2, "high"), (3, "low"), (4, "close")):
            try:
                price = parse_decimal(row[field_index], field_name=name, index=index)
            except DataValidationError as exc:
                add("INVALID_PRICE", str(exc), index, open_ms)
                continue
            if price <= 0:
                add("INVALID_PRICE", f"Row {index}: {name} must be > 0; got {price}.", index, open_ms)
            prices[name] = price

        if len(prices) == 4:
            if prices["high"] < max(prices["open"], prices["close"]):
                add("INVALID_OHLC", f"Row {index}: high is below open/close.", index, open_ms)
            if prices["low"] > min(prices["open"], prices["close"]):
                add("INVALID_OHLC", f"Row {index}: low is above open/close.", index, open_ms)
            if prices["low"] > prices["high"]:
                add("INVALID_OHLC", f"Row {index}: low is greater than high.", index, open_ms)

        for field_index, name in ((5, "volume"), (7, "quote_volume")):
            try:
                volume = parse_decimal(row[field_index], field_name=name, index=index)
            except DataValidationError as exc:
                add("INVALID_VOLUME", str(exc), index, open_ms)
                continue
            if volume < 0:
                add("INVALID_VOLUME", f"Row {index}: {name} must be >= 0; got {volume}.", index, open_ms)

        try:
            if _to_int(row[8]) < 0:
                raise ValueError
        except (TypeError, ValueError):
            add("INVALID_TRADE_COUNT", f"Row {index}: invalid trade count.", index, open_ms)

        if previous_open is not None:
            expected_next = previous_open + interval_ms
            if open_ms < previous_open:
                add("NON_MONOTONIC_TIMESTAMP", f"Row {index}: timestamp {open_ms} is earlier than previous timestamp {previous_open}.", index, open_ms)
            elif open_ms > expected_next:
                missing = (open_ms - expected_next) // interval_ms
                if missing > 0:  # sub-interval offsets are reported as MISALIGNED_TIMESTAMP only
                    add("MISSING_CANDLES", f"Missing {missing} candle(s) between {previous_open} and {open_ms}.", index, open_ms)
        previous_open = open_ms

    if not rows and (expected_start_ms is not None or expected_end_ms_exclusive is not None):
        add("EMPTY_RESULT", "No candles returned for an expected non-empty range.", None)

    if first_open is not None and last_open is not None:
        if expected_start_ms is not None and first_open != expected_start_ms:
            add("UNEXPECTED_START", f"Expected first candle at {expected_start_ms}, received {first_open}.", None, first_open)
        if expected_end_ms_exclusive is not None:
            expected_last = expected_end_ms_exclusive - interval_ms
            if last_open != expected_last:
                add("UNEXPECTED_END", f"Expected last candle at {expected_last}, received {last_open}.", None, last_open)

    return issues


def assert_valid_klines(
    rows: Sequence[Sequence[Any]],
    *,
    symbol: str,
    timeframe: str,
    expected_start_ms: int | None = None,
    expected_end_ms_exclusive: int | None = None,
) -> None:
    issues = validate_klines(
        rows,
        symbol=symbol,
        timeframe=timeframe,
        expected_start_ms=expected_start_ms,
        expected_end_ms_exclusive=expected_end_ms_exclusive,
    )
    if issues:
        formatted = "\n".join(f"[{i.code}] {i.message}" for i in issues)
        raise DataValidationError(f"Market-data validation failed for {symbol} {timeframe}:\n{formatted}")


def utc_datetime_from_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
