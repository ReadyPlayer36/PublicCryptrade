"""Deterministic audit hash of candle records (frozen spec: matrix.yaml `hash`)."""
from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

FIELD_ORDER = (
    "symbol", "timeframe", "open_time_ms", "close_time_ms", "open", "high",
    "low", "close", "volume", "quote_volume", "trade_count",
)
_TEXT_FIELDS = ("symbol", "timeframe")
_INT_FIELDS = ("open_time_ms", "close_time_ms", "trade_count")
_DECIMAL_FIELDS = ("open", "high", "low", "close", "volume", "quote_volume")
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\n"


def _serialize_int(value: Any, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int, got {type(value).__name__}")
    return str(value)


def _serialize_decimal(value: Any, name: str) -> str:
    if isinstance(value, float) or isinstance(value, bool):
        raise ValueError(f"{name} must be a Decimal, int or decimal string, not {type(value).__name__}")
    try:
        number = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not a valid decimal: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite: {value!r}")
    return format(number, "f")


def _serialize_record(record: Mapping[str, Any], index: int) -> str:
    missing = [f for f in FIELD_ORDER if f not in record]
    if missing:
        raise ValueError(f"record {index} is missing fields: {missing}")
    parts: list[str] = []
    for name in FIELD_ORDER:
        value = record[name]
        if name in _TEXT_FIELDS:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
            if _FIELD_SEP in value or _RECORD_SEP in value:
                raise ValueError(f"{name} contains a reserved separator character")
            parts.append(value)
        elif name in _INT_FIELDS:
            parts.append(_serialize_int(value, name))
        else:
            parts.append(_serialize_decimal(value, name))
    return _FIELD_SEP.join(parts)


def hash_candles(records: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 hex digest of records in strictly ascending open_time_ms order.

    Records are never reordered or de-duplicated: unsorted or duplicate input
    is rejected (no silent repair). An empty set hashes the empty byte string.
    """
    lines: list[str] = []
    previous: int | None = None
    for index, record in enumerate(records):
        line = _serialize_record(record, index)
        open_time = record["open_time_ms"]
        if previous is not None and open_time <= previous:
            raise ValueError(f"record {index} is not in strictly ascending open_time_ms order")
        previous = open_time
        lines.append(line)
    return hashlib.sha256(_RECORD_SEP.join(lines).encode("utf-8")).hexdigest()
