"""SQLite persistence for validated candles.

* Decimals are stored as exact strings via ``format(d, "f")``; times as UTC epoch ms.
* Every SQLite connection sets WAL mode and a busy timeout; the data directory is
  created before connecting.
* One atomic ``BEGIN IMMEDIATE`` transaction per insert, taken only after all input
  validation. Identical rows are idempotent; any difference raises
  ``CandleConflictError`` and rolls the whole batch back. Nothing is overwritten.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

from trading_app.data.models import Base, CandleModel
from trading_app.data.schemas import Candle

BUSY_TIMEOUT_MS = 10_000   # explicit; differs from the sqlite3 module default (5000) so it is verifiable
MAX_CANDLES_PER_FETCH = 100_000
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS = timedelta(milliseconds=1)
_LOOKUP_CHUNK = 500
_DECIMAL_COLUMNS = (("open", "open_price"), ("high", "high_price"), ("low", "low_price"),
                    ("close", "close_price"), ("volume", "volume"), ("quote_volume", "quote_volume"))


class CandleConflictError(RuntimeError):
    """An existing candle differs from the incoming one; nothing was written."""


class TooManyCandlesError(ValueError):
    """A fetch exceeded max_candles_per_fetch; rejected before any persistence."""


def create_engine_from_url(database_url: str) -> Engine:
    """Create the engine. For SQLite files: create the directory first, then set WAL +
    busy timeout on EVERY new connection and take manual transaction control."""
    url = make_url(database_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    if is_sqlite and url.database not in (None, "", ":memory:") and not str(url.database).startswith("file:"):
        Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)
    if is_sqlite:
        in_memory = url.database in (None, "", ":memory:")

        @event.listens_for(engine, "connect")
        def _configure(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.isolation_level = None          # we issue BEGIN IMMEDIATE ourselves
            cursor = dbapi_connection.cursor()
            try:
                if not in_memory:
                    cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            finally:
                cursor.close()
    return engine


def to_ms(value: datetime) -> int:
    """Exact UTC epoch milliseconds from an aware datetime (integer arithmetic)."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware datetimes")
    return (value.astimezone(timezone.utc) - _EPOCH) // _MS


def _from_ms(value: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=value)


def _dec(value: Any, name: str) -> Decimal:
    if isinstance(value, (float, bool)):
        raise ValueError(f"{name} must be Decimal, int or decimal string, never float")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value) if isinstance(value, (str, int)) else value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not a valid decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite")
    return number


def _normalize(candle: Any, index: int) -> dict[str, Any]:
    try:
        symbol, timeframe = candle.symbol, candle.timeframe
        if not isinstance(symbol, str) or not symbol or not isinstance(timeframe, str) or not timeframe:
            raise ValueError("symbol and timeframe must be non-empty strings")
        trade_count = candle.trade_count
        if isinstance(trade_count, bool) or not isinstance(trade_count, int) or trade_count < 0:
            raise ValueError("trade_count must be an int >= 0")
        row: dict[str, Any] = {
            "symbol": symbol, "timeframe": timeframe,
            "open_time_ms": to_ms(candle.open_time), "close_time_ms": to_ms(candle.close_time),
            "trade_count": trade_count,
        }
        decimals: dict[str, Decimal] = {}
        for attr, column in _DECIMAL_COLUMNS:
            number = _dec(getattr(candle, attr), attr)
            decimals[column] = number
            row[column] = format(number, "f")
        created = getattr(candle, "created_at_ms", None)
        row["created_at_ms"] = created if isinstance(created, int) and not isinstance(created, bool) else int(time.time() * 1000)
    except AttributeError as exc:
        raise ValueError(f"candle {index} is missing a required field: {exc.name}") from None
    except ValueError as exc:
        raise ValueError(f"candle {index} is invalid: {exc}") from None
    row["_decimals"] = decimals
    return row


def _differences(stored: Mapping[str, Any], incoming: dict[str, Any]) -> list[str]:
    """Names of conflict fields that differ (numeric Decimal equality; created_at excluded)."""
    different: list[str] = []
    if stored["close_time_ms"] != incoming["close_time_ms"]:
        different.append("close_time")
    for attr, column in _DECIMAL_COLUMNS:
        if Decimal(stored[column]) != incoming["_decimals"][column]:
            different.append(attr)
    if stored["trade_count"] != incoming["trade_count"]:
        different.append("trade_count")
    return different


class CandleRepository:
    """Persistence layer for validated candles."""

    def __init__(self, engine: Engine, *, max_candles_per_fetch: int = MAX_CANDLES_PER_FETCH) -> None:
        if isinstance(max_candles_per_fetch, bool) or not isinstance(max_candles_per_fetch, int) or max_candles_per_fetch < 1:
            raise ValueError("max_candles_per_fetch must be an int >= 1")
        self.engine = engine
        self.max_candles_per_fetch = max_candles_per_fetch

    def create_tables(self) -> None:
        Base.metadata.create_all(self.engine)

    def insert_candles(self, candles: Iterable[Any]) -> int:
        """Insert new candles atomically; returns the number of NEW rows.

        Validation and normalization finish before the transaction starts. An identical
        existing row is skipped; a differing one raises CandleConflictError and rolls the
        entire batch back. Existing rows are never overwritten.
        """
        batch = list(candles)
        if len(batch) > self.max_candles_per_fetch:
            raise TooManyCandlesError(
                f"{len(batch)} candles exceed max_candles_per_fetch={self.max_candles_per_fetch}; nothing persisted"
            )
        if not batch:
            return 0
        rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        for index, candle in enumerate(batch):
            row = _normalize(candle, index)
            key = (row["symbol"], row["timeframe"], row["open_time_ms"])
            previous = rows.get(key)
            if previous is not None:
                diff = self._batch_diff(previous, row)
                if diff:
                    raise CandleConflictError(
                        f"conflict inside the batch for {key[0]} {key[1]} at {key[2]}: fields differ: {', '.join(diff)}"
                    )
                continue
            rows[key] = row

        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                existing = self._load_existing(connection, rows)
                new_rows: list[dict[str, Any]] = []
                for key, row in rows.items():
                    stored = existing.get(key)
                    if stored is None:
                        new_rows.append({k: v for k, v in row.items() if k != "_decimals"})
                        continue
                    diff = _differences(stored, row)
                    if diff:
                        raise CandleConflictError(
                            f"conflict for {key[0]} {key[1]} at {key[2]}: existing candle is different in: {', '.join(diff)}; "
                            "nothing was written"
                        )
                if new_rows:
                    connection.execute(CandleModel.__table__.insert(), new_rows)
                connection.commit()
                return len(new_rows)
            except IntegrityError:
                connection.rollback()
                raise CandleConflictError("unique constraint conflict; nothing was written") from None
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _batch_diff(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
        different = []
        if a["close_time_ms"] != b["close_time_ms"]:
            different.append("close_time")
        for attr, column in _DECIMAL_COLUMNS:
            if a["_decimals"][column] != b["_decimals"][column]:
                different.append(attr)
        if a["trade_count"] != b["trade_count"]:
            different.append("trade_count")
        return different

    @staticmethod
    def _load_existing(connection: Any, rows: dict[tuple[str, str, int], dict[str, Any]]) -> dict[tuple[str, str, int], Mapping[str, Any]]:
        table = CandleModel.__table__
        by_series: dict[tuple[str, str], list[int]] = {}
        for symbol, timeframe, open_ms in rows:
            by_series.setdefault((symbol, timeframe), []).append(open_ms)
        found: dict[tuple[str, str, int], Mapping[str, Any]] = {}
        for (symbol, timeframe), times in by_series.items():
            for start in range(0, len(times), _LOOKUP_CHUNK):
                chunk = times[start:start + _LOOKUP_CHUNK]
                statement = select(table).where(
                    table.c.symbol == symbol, table.c.timeframe == timeframe, table.c.open_time_ms.in_(chunk)
                )
                for stored in connection.execute(statement).mappings():
                    found[(symbol, timeframe, stored["open_time_ms"])] = stored
        return found

    def count(self, *, symbol: str | None = None, timeframe: str | None = None) -> int:
        statement = select(func.count()).select_from(CandleModel)
        if symbol is not None:
            statement = statement.where(CandleModel.symbol == symbol)
        if timeframe is not None:
            statement = statement.where(CandleModel.timeframe == timeframe)
        with self.engine.connect() as connection:
            return int(connection.execute(statement).scalar_one())

    def get_candles(self, *, symbol: str, timeframe: str) -> list[Candle]:
        statement = (select(CandleModel).where(CandleModel.symbol == symbol, CandleModel.timeframe == timeframe)
                     .order_by(CandleModel.open_time_ms))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            Candle(
                symbol=r["symbol"], timeframe=r["timeframe"],
                open_time=_from_ms(r["open_time_ms"]), close_time=_from_ms(r["close_time_ms"]),
                open=Decimal(r["open_price"]), high=Decimal(r["high_price"]), low=Decimal(r["low_price"]),
                close=Decimal(r["close_price"]), volume=Decimal(r["volume"]), quote_volume=Decimal(r["quote_volume"]),
                trade_count=r["trade_count"],
            )
            for r in rows
        ]

    def scan_legacy_data(self, *args: Any, **kwargs: Any):
        """Return legacy-data findings without modifying records (Stage D2)."""
        raise NotImplementedError("Stage-2 implementation not started: scan_legacy_data")
