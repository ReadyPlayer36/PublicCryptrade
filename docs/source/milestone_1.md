# Binance Spot Trading Research Application — Milestone 1

Public market-data ingestion only. No trading, order submission, API keys, private endpoints, or execution code.
## 1. Project structure

binance-research/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
│
├── src/
│   └── trading_app/
│       ├── __init__.py
│       ├── config.py
│       │
│       └── data/
│           ├── __init__.py
│           ├── models.py
│           ├── schemas.py
│           ├── validator.py
│           ├── repository.py
│           ├── binance_client.py
│           └── service.py
│
└── tests/
    ├── unit/
    │   ├── test_validator.py
    │   ├── test_repository.py
    │   └── test_binance_client.py
    └── fixtures/
        └── __init__.py

Database: data/trading.db
## 2. pyproject.toml

[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "binance-research"
version = "0.1.0"
description = "Binance Spot market-data research application"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pandas>=2.2,<3",
    "numpy>=2.0,<3",
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.6,<3",
    "SQLAlchemy>=2.0,<3",
    "FastAPI>=0.115,<1",
    "httpx>=0.27,<1"
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "pytest-cov>=6,<7"
]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-ra"
## 3. .env.example

APP_NAME=binance-research
APP_ENV=development

DATABASE_URL=sqlite:///./data/trading.db

BINANCE_BASE_URL=https://api.binance.com
BINANCE_TIMEOUT_SECONDS=10
BINANCE_MAX_RETRIES=3
BINANCE_REQUEST_DELAY_SECONDS=0.2

ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT
ALLOWED_TIMEFRAMES=5m,15m,1h,4h

Note: there is intentionally no API-key configuration because Milestone 1 uses public endpoints only.
## 4. .gitignore

__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/

.venv/
venv/
env/

.env

data/*.db
data/*.sqlite
data/*.sqlite3

*.log

.DS_Store
.idea/
.vscode/
## 5. src/trading_app/__init__.py

"""Binance Spot research application."""
## 6. src/trading_app/config.py

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "binance-research"
    app_env: str = "development"

    database_url: str = "sqlite:///./data/trading.db"

    binance_base_url: str = "https://api.binance.com"
    binance_timeout_seconds: float = 10.0
    binance_max_retries: int = 3
    binance_request_delay_seconds: float = 0.2

    allowed_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    allowed_timeframes: tuple[str, ...] = ("5m", "15m", "1h", "4h")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("binance_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("binance_timeout_seconds must be > 0")
        return value

    @field_validator("binance_max_retries")
    @classmethod
    def validate_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("binance_max_retries must be >= 0")
        return value

    @field_validator("binance_request_delay_seconds")
    @classmethod
    def validate_request_delay(cls, value: float) -> float:
        if value < 0:
            raise ValueError("binance_request_delay_seconds must be >= 0")
        return value

    @field_validator("allowed_symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(
                item.strip().upper()
                for item in value.split(",")
                if item.strip()
            )
        return tuple(str(item).upper() for item in value)

    @field_validator("allowed_timeframes", mode="before")
    @classmethod
    def parse_timeframes(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(
                item.strip()
                for item in value.split(",")
                if item.strip()
            )
        return tuple(str(item) for item in value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
## 7. src/trading_app/data/__init__.py

"""Market-data ingestion and storage."""
## 8. src/trading_app/data/schemas.py

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Candle(BaseModel):
    """Validated OHLCV candle."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=2)

    open_time: datetime
    close_time: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal

    trade_count: int = Field(ge=0)

    @field_validator(
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    )
    @classmethod
    def validate_decimal_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("OHLCV values must be finite")
        return value
## 9. src/trading_app/data/models.py

from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class CandleModel(Base):
    """Persisted OHLCV candle."""

    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    open_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    close_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    open_price: Mapped[str] = mapped_column(String(80), nullable=False)
    high_price: Mapped[str] = mapped_column(String(80), nullable=False)
    low_price: Mapped[str] = mapped_column(String(80), nullable=False)
    close_price: Mapped[str] = mapped_column(String(80), nullable=False)
    volume: Mapped[str] = mapped_column(String(80), nullable=False)
    quote_volume: Mapped[str] = mapped_column(String(80), nullable=False)

    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "open_time_ms",
            name="uq_candle_symbol_timeframe_open_time",
        ),
    )
## 10. src/trading_app/data/validator.py

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
        raise DataValidationError(
            f"Unsupported timeframe: {timeframe!r}"
        ) from exc


def parse_decimal(value: Any, *, field_name: str, index: int) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DataValidationError(
            f"Row {index}: {field_name} is not a valid decimal: {value!r}"
        ) from exc

    if not result.is_finite():
        raise DataValidationError(
            f"Row {index}: {field_name} must be finite: {value!r}"
        )

    return result


def validate_raw_klines(
    rows: Sequence[Sequence[Any]],
    *,
    symbol: str,
    timeframe: str,
    expected_start_ms: int | None = None,
    expected_end_ms_exclusive: int | None = None,
) -> list[ValidationIssue]:
    """Validate raw Binance kline rows. No data is repaired."""

    interval_ms = timeframe_to_ms(timeframe)
    issues: list[ValidationIssue] = []
    seen: set[int] = set()
    previous_open_time: int | None = None

    for index, row in enumerate(rows):
        if len(row) < 12:
            issues.append(ValidationIssue(
                code="MALFORMED_ROW",
                message=f"Row {index} contains {len(row)} fields; expected at least 12.",
                index=index,
            ))
            continue

        try:
            open_time_ms = int(row[0])
            close_time_ms = int(row[6])
        except (TypeError, ValueError):
            issues.append(ValidationIssue(
                code="INVALID_TIMESTAMP",
                message=f"Row {index} contains invalid timestamps.",
                index=index,
            ))
            continue

        if open_time_ms in seen:
            issues.append(ValidationIssue(
                code="DUPLICATE_CANDLE",
                message=f"Duplicate candle for {symbol} {timeframe} at {open_time_ms}.",
                index=index,
                open_time_ms=open_time_ms,
            ))

        seen.add(open_time_ms)

        if open_time_ms % interval_ms != 0:
            issues.append(ValidationIssue(
                code="MISALIGNED_TIMESTAMP",
                message=f"Row {index}: open timestamp {open_time_ms} is not aligned to {timeframe}.",
                index=index,
                open_time_ms=open_time_ms,
            ))

        if close_time_ms <= open_time_ms:
            issues.append(ValidationIssue(
                code="INVALID_CLOSE_TIME",
                message=f"Row {index}: close time {close_time_ms} is not after open time {open_time_ms}.",
                index=index,
                open_time_ms=open_time_ms,
            ))

        if close_time_ms != open_time_ms + interval_ms - 1:
            issues.append(ValidationIssue(
                code="INVALID_CANDLE_DURATION",
                message=f"Row {index}: close time does not match {timeframe} interval.",
                index=index,
                open_time_ms=open_time_ms,
            ))

        for field_index, field_name in ((1, "open"), (2, "high"), (3, "low"), (4, "close")):
            try:
                price = parse_decimal(row[field_index], field_name=field_name, index=index)
            except DataValidationError as exc:
                issues.append(ValidationIssue(
                    code="INVALID_PRICE",
                    message=str(exc),
                    index=index,
                    open_time_ms=open_time_ms,
                ))
                continue

            if price <= 0:
                issues.append(ValidationIssue(
                    code="INVALID_PRICE",
                    message=f"Row {index}: {field_name} must be > 0; got {price}.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))

        try:
            high = parse_decimal(row[2], field_name="high", index=index)
            low = parse_decimal(row[3], field_name="low", index=index)
            open_price = parse_decimal(row[1], field_name="open", index=index)
            close_price = parse_decimal(row[4], field_name="close", index=index)

            if high < max(open_price, close_price):
                issues.append(ValidationIssue(
                    code="INVALID_OHLC",
                    message=f"Row {index}: high is below open/close.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))

            if low > min(open_price, close_price):
                issues.append(ValidationIssue(
                    code="INVALID_OHLC",
                    message=f"Row {index}: low is above open/close.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))

            if low > high:
                issues.append(ValidationIssue(
                    code="INVALID_OHLC",
                    message=f"Row {index}: low is greater than high.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))
        except DataValidationError:
            pass

        for field_index, field_name in ((5, "volume"), (7, "quote_volume")):
            try:
                volume = parse_decimal(row[field_index], field_name=field_name, index=index)
            except DataValidationError as exc:
                issues.append(ValidationIssue(
                    code="INVALID_VOLUME",
                    message=str(exc),
                    index=index,
                    open_time_ms=open_time_ms,
                ))
                continue

            if volume < 0:
                issues.append(ValidationIssue(
                    code="INVALID_VOLUME",
                    message=f"Row {index}: {field_name} must be >= 0; got {volume}.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))

        try:
            trade_count = int(row[8])
            if trade_count < 0:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(ValidationIssue(
                code="INVALID_TRADE_COUNT",
                message=f"Row {index}: invalid trade count.",
                index=index,
                open_time_ms=open_time_ms,
            ))

        if previous_open_time is not None:
            expected_next = previous_open_time + interval_ms

            if open_time_ms < previous_open_time:
                issues.append(ValidationIssue(
                    code="NON_MONOTONIC_TIMESTAMP",
                    message=f"Row {index}: timestamp {open_time_ms} is earlier than previous timestamp {previous_open_time}.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))
            elif open_time_ms > expected_next:
                missing_count = (open_time_ms - expected_next) // interval_ms
                issues.append(ValidationIssue(
                    code="MISSING_CANDLES",
                    message=f"Missing {missing_count} candle(s) between {previous_open_time} and {open_time_ms}.",
                    index=index,
                    open_time_ms=open_time_ms,
                ))

        previous_open_time = open_time_ms

    if rows:
        first_open_time = int(rows[0][0])
        last_open_time = int(rows[-1][0])

        if expected_start_ms is not None and first_open_time != expected_start_ms:
            issues.append(ValidationIssue(
                code="UNEXPECTED_START",
                message=f"Expected first candle at {expected_start_ms}, received {first_open_time}.",
                open_time_ms=first_open_time,
            ))

        if expected_end_ms_exclusive is not None:
            expected_last = expected_end_ms_exclusive - interval_ms
            if last_open_time != expected_last:
                issues.append(ValidationIssue(
                    code="UNEXPECTED_END",
                    message=f"Expected last candle at {expected_last}, received {last_open_time}.",
                    open_time_ms=last_open_time,
                ))

    return issues


def assert_valid_klines(
    rows: Sequence[Sequence[Any]],
    *,
    symbol: str,
    timeframe: str,
    expected_start_ms: int | None = None,
    expected_end_ms_exclusive: int | None = None,
) -> None:
    issues = validate_raw_klines(
        rows,
        symbol=symbol,
        timeframe=timeframe,
        expected_start_ms=expected_start_ms,
        expected_end_ms_exclusive=expected_end_ms_exclusive,
    )

    if issues:
        formatted = "\n".join(
            f"[{issue.code}] {issue.message}"
            for issue in issues
        )
        raise DataValidationError(
            f"Market-data validation failed for {symbol} {timeframe}:\n{formatted}"
        )


def utc_datetime_from_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
## 11. src/trading_app/data/repository.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from trading_app.data.models import Base, CandleModel
from trading_app.data.schemas import Candle


def create_engine_from_url(database_url: str) -> Engine:
    """Create the SQLAlchemy engine."""
    return create_engine(database_url, future=True)


class CandleRepository:
    """Persistence layer for validated candles."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_tables(self) -> None:
        Base.metadata.create_all(self.engine)

    def insert_candles(self, candles: list[Candle]) -> int:
        """Insert candles while preventing duplicates."""
        if not candles:
            return 0

        with self.session_factory() as session:
            keys = [
                (
                    candle.symbol,
                    candle.timeframe,
                    int(candle.open_time.timestamp() * 1000),
                )
                for candle in candles
            ]

            existing_query = select(
                CandleModel.symbol,
                CandleModel.timeframe,
                CandleModel.open_time_ms,
            ).where(
                or_(
                    *(
                        and_(
                            CandleModel.symbol == symbol,
                            CandleModel.timeframe == timeframe,
                            CandleModel.open_time_ms == open_time_ms,
                        )
                        for symbol, timeframe, open_time_ms in keys
                    )
                )
            )

            existing_keys = set(session.execute(existing_query).all())
            inserted = 0

            for candle in candles:
                open_time_ms = int(candle.open_time.timestamp() * 1000)
                key = (candle.symbol, candle.timeframe, open_time_ms)

                if key in existing_keys:
                    continue

                session.add(CandleModel(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    open_time_ms=open_time_ms,
                    close_time_ms=int(candle.close_time.timestamp() * 1000),
                    open_price=str(candle.open),
                    high_price=str(candle.high),
                    low_price=str(candle.low),
                    close_price=str(candle.close),
                    volume=str(candle.volume),
                    quote_volume=str(candle.quote_volume),
                    trade_count=candle.trade_count,
                    created_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                ))

                existing_keys.add(key)
                inserted += 1

            session.commit()
            return inserted

    def count(self, *, symbol: str | None = None, timeframe: str | None = None) -> int:
        with self.session_factory() as session:
            statement = select(CandleModel)

            if symbol is not None:
                statement = statement.where(CandleModel.symbol == symbol)
            if timeframe is not None:
                statement = statement.where(CandleModel.timeframe == timeframe)

            return len(session.execute(statement).scalars().all())

    def get_candles(self, *, symbol: str, timeframe: str) -> list[Candle]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CandleModel)
                .where(CandleModel.symbol == symbol)
                .where(CandleModel.timeframe == timeframe)
                .order_by(CandleModel.open_time_ms)
            ).scalars().all()

            return [
                Candle(
                    symbol=row.symbol,
                    timeframe=row.timeframe,
                    open_time=datetime.fromtimestamp(row.open_time_ms / 1000, tz=timezone.utc),
                    close_time=datetime.fromtimestamp(row.close_time_ms / 1000, tz=timezone.utc),
                    open=row.open_price,
                    high=row.high_price,
                    low=row.low_price,
                    close=row.close_price,
                    volume=row.volume,
                    quote_volume=row.quote_volume,
                    trade_count=row.trade_count,
                )
                for row in rows
            ]
## 12. src/trading_app/data/binance_client.py

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from trading_app.data.schemas import Candle
from trading_app.data.validator import DataValidationError, assert_valid_klines, timeframe_to_ms


class BinanceClientError(RuntimeError):
    """Raised when Binance public market-data access fails."""


class HttpClient(Protocol):
    def get(self, url: str, *, params: dict[str, Any]) -> httpx.Response:
        ...


class BinanceMarketDataClient:
    """Binance public Spot market-data client. No credentials are used."""

    KLINES_PATH = "/api/v3/klines"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        request_delay_seconds: float = 0.2,
        http_client: HttpClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.request_delay_seconds = request_delay_seconds
        self._owns_http_client = http_client is None

        self.http_client = http_client or httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": "binance-research/0.1",
            },
        )

    def close(self) -> None:
        if self._owns_http_client:
            self.http_client.close()

    def __enter__(self) -> "BinanceMarketDataClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
    ) -> list[list[Any]]:
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        }

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.http_client.get(
                    f"{self.base_url}{self.KLINES_PATH}",
                    params=params,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "1")

                    try:
                        delay = max(float(retry_after), 1.0)
                    except ValueError:
                        delay = 1.0

                    if attempt >= self.max_retries:
                        raise BinanceClientError(
                            f"Binance rate limit remained active after {self.max_retries} retries."
                        )

                    time.sleep(delay)
                    continue

                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, list):
                    raise BinanceClientError(
                        "Binance returned a non-list kline response."
                    )

                return payload

            except (httpx.HTTPError, ValueError, BinanceClientError) as exc:
                last_error = exc

                if attempt >= self.max_retries:
                    break

                time.sleep(self.request_delay_seconds * (attempt + 1))

        raise BinanceClientError(
            "Unable to retrieve Binance klines."
        ) from last_error

    def get_historical_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Download [start, end) candle data."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware.")

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        if end <= start:
            raise ValueError("end must be after start.")

        interval_ms = timeframe_to_ms(timeframe)
        start_ms = int(start.timestamp() * 1000)
        end_ms_exclusive = int(end.timestamp() * 1000)

        if start_ms % interval_ms != 0:
            raise ValueError(f"start {start.isoformat()} is not aligned to {timeframe}.")
        if end_ms_exclusive % interval_ms != 0:
            raise ValueError(f"end {end.isoformat()} is not aligned to {timeframe}.")

        all_rows: list[list[Any]] = []
        cursor_ms = start_ms

        while cursor_ms < end_ms_exclusive:
            page = self._request_klines(
                symbol=symbol,
                timeframe=timeframe,
                start_time_ms=cursor_ms,
                end_time_ms=end_ms_exclusive - 1,
                limit=1000,
            )

            if not page:
                raise DataValidationError(
                    f"Binance returned no candles starting at {cursor_ms} for {symbol} {timeframe}."
                )

            page_issues = self._validate_page_order(
                page,
                symbol=symbol,
                timeframe=timeframe,
            )

            if page_issues:
                raise DataValidationError(
                    "Suspicious Binance page:\n" + "\n".join(page_issues)
                )

            all_rows.extend(page)

            last_open_ms = int(page[-1][0])
            next_cursor = last_open_ms + interval_ms

            if next_cursor <= cursor_ms:
                raise DataValidationError(
                    "Binance pagination did not advance; refusing to continue."
                )

            cursor_ms = next_cursor

            if len(page) < 1000:
                break

            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)

        assert_valid_klines(
            all_rows,
            symbol=symbol,
            timeframe=timeframe,
            expected_start_ms=start_ms,
            expected_end_ms_exclusive=end_ms_exclusive,
        )

        return [
            self._raw_to_candle(row, symbol=symbol, timeframe=timeframe)
            for row in all_rows
        ]

    @staticmethod
    def _validate_page_order(
        rows: list[list[Any]],
        *,
        symbol: str,
        timeframe: str,
    ) -> list[str]:
        interval_ms = timeframe_to_ms(timeframe)
        issues: list[str] = []
        previous: int | None = None

        for index, row in enumerate(rows):
            if len(row) < 12:
                issues.append(f"row {index}: fewer than 12 Binance kline fields")
                continue

            try:
                current = int(row[0])
            except (TypeError, ValueError):
                issues.append(f"row {index}: invalid open timestamp")
                continue

            if previous is not None:
                if current <= previous:
                    issues.append(
                        f"row {index}: timestamps are not strictly increasing"
                    )
                elif current != previous + interval_ms:
                    issues.append(
                        f"row {index}: gap detected between {previous} and {current}"
                    )

            previous = current

        return issues

    @staticmethod
    def _raw_to_candle(
        row: list[Any],
        *,
        symbol: str,
        timeframe: str,
    ) -> Candle:
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
            close_time=datetime.fromtimestamp(int(row[6]) / 1000, tz=timezone.utc),
            open=row[1],
            high=row[2],
            low=row[3],
            close=row[4],
            volume=row[5],
            quote_volume=row[7],
            trade_count=int(row[8]),
        )
## 13. src/trading_app/data/service.py

from __future__ import annotations

from datetime import datetime

from trading_app.config import Settings
from trading_app.data.binance_client import BinanceMarketDataClient
from trading_app.data.repository import CandleRepository


class MarketDataService:
    """Application service for historical market-data ingestion."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: BinanceMarketDataClient,
        repository: CandleRepository,
    ) -> None:
        self.settings = settings
        self.client = client
        self.repository = repository

    def download_and_store(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> int:
        symbol = symbol.upper()

        if symbol not in self.settings.allowed_symbols:
            raise ValueError(f"Symbol {symbol!r} is not configured.")

        if timeframe not in self.settings.allowed_timeframes:
            raise ValueError(f"Timeframe {timeframe!r} is not configured.")

        candles = self.client.get_historical_klines(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

        return self.repository.insert_candles(candles)
## 14. tests/fixtures/__init__.py

"""Test fixtures."""
## 15. tests/unit/test_validator.py

from datetime import datetime, timezone

import pytest

from trading_app.data.validator import DataValidationError, assert_valid_klines


def kline(
    open_time_ms: int,
    *,
    open_price: str = "100",
    high: str = "101",
    low: str = "99",
    close: str = "100.5",
    volume: str = "10",
    quote_volume: str = "1005",
) -> list:
    interval_ms = 5 * 60 * 1000
    return [
        open_time_ms, open_price, high, low, close, volume,
        open_time_ms + interval_ms - 1, quote_volume, 100, "1", "2", "0",
    ]


START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
INTERVAL = 5 * 60 * 1000


def test_valid_klines_pass():
    rows = [kline(START), kline(START + INTERVAL), kline(START + 2 * INTERVAL)]
    assert_valid_klines(
        rows,
        symbol="BTCUSDT",
        timeframe="5m",
        expected_start_ms=START,
        expected_end_ms_exclusive=START + 3 * INTERVAL,
    )


def test_duplicate_candle_is_rejected():
    with pytest.raises(DataValidationError, match="DUPLICATE_CANDLE"):
        assert_valid_klines([kline(START), kline(START)], symbol="BTCUSDT", timeframe="5m")


def test_missing_candle_is_rejected():
    with pytest.raises(DataValidationError, match="MISSING_CANDLES"):
        assert_valid_klines(
            [kline(START), kline(START + 2 * INTERVAL)],
            symbol="BTCUSDT",
            timeframe="5m",
        )


@pytest.mark.parametrize("field_index", [1, 2, 3, 4])
def test_invalid_price_is_rejected(field_index: int):
    row = kline(START)
    row[field_index] = "0"

    with pytest.raises(DataValidationError, match="INVALID_PRICE"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")


def test_negative_volume_is_rejected():
    row = kline(START)
    row[5] = "-1"

    with pytest.raises(DataValidationError, match="INVALID_VOLUME"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")


def test_invalid_ohlc_relationship_is_rejected():
    row = kline(START, high="90", low="80", open_price="100", close="95")

    with pytest.raises(DataValidationError, match="INVALID_OHLC"):
        assert_valid_klines([row], symbol="BTCUSDT", timeframe="5m")


def test_unaligned_timestamp_is_rejected():
    with pytest.raises(DataValidationError, match="MISALIGNED_TIMESTAMP"):
        assert_valid_klines([kline(START + 1)], symbol="BTCUSDT", timeframe="5m")
## 16. tests/unit/test_repository.py

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine

from trading_app.data.models import Base
from trading_app.data.repository import CandleRepository
from trading_app.data.schemas import Candle


def make_candle(open_time: datetime) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="5m",
        open_time=open_time,
        close_time=datetime.fromtimestamp(
            open_time.timestamp() + 299,
            tz=timezone.utc,
        ),
        open=Decimal("100.12345678"),
        high=Decimal("101.12345678"),
        low=Decimal("99.12345678"),
        close=Decimal("100.92345678"),
        volume=Decimal("12.34567890"),
        quote_volume=Decimal("1234.56789012"),
        trade_count=100,
    )


def test_duplicate_inserts_are_ignored():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repository = CandleRepository(engine)

    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candle = make_candle(timestamp)

    assert repository.insert_candles([candle]) == 1
    assert repository.insert_candles([candle]) == 0
    assert repository.count(symbol="BTCUSDT", timeframe="5m") == 1


def test_decimal_values_round_trip_as_exact_strings():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repository = CandleRepository(engine)

    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repository.insert_candles([make_candle(timestamp)])

    stored = repository.get_candles(symbol="BTCUSDT", timeframe="5m")

    assert len(stored) == 1
    assert stored[0].open == Decimal("100.12345678")
    assert stored[0].volume == Decimal("12.34567890")
## 17. tests/unit/test_binance_client.py

from datetime import datetime, timezone

import httpx
import pytest

from trading_app.data.binance_client import BinanceMarketDataClient
from trading_app.data.validator import DataValidationError


class MockHttpClient:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.calls: list[dict] = []

    def get(self, url: str, *, params: dict):
        self.calls.append({"url": url, "params": params})
        return self.response


def make_kline(open_time_ms: int) -> list:
    interval_ms = 5 * 60 * 1000
    return [
        open_time_ms, "100.0", "101.0", "99.0", "100.5", "10.0",
        open_time_ms + interval_ms - 1, "1005.0", 100, "1.0", "2.0", "0",
    ]


START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
INTERVAL = 5 * 60 * 1000


def test_client_downloads_public_klines():
    payload = [make_kline(START), make_kline(START + INTERVAL)]
    response = httpx.Response(200, json=payload)
    mock = MockHttpClient(response)

    client = BinanceMarketDataClient(
        base_url="https://api.binance.com",
        http_client=mock,
        request_delay_seconds=0,
    )

    candles = client.get_historical_klines(
        symbol="BTCUSDT",
        timeframe="5m",
        start=datetime.fromtimestamp(START / 1000, tz=timezone.utc),
        end=datetime.fromtimestamp((START + 2 * INTERVAL) / 1000, tz=timezone.utc),
    )

    assert len(candles) == 2
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].timeframe == "5m"
    assert mock.calls[0]["url"] == "https://api.binance.com/api/v3/klines"
    assert "apiKey" not in mock.calls[0]["params"]


def test_client_rejects_gap():
    payload = [make_kline(START), make_kline(START + 2 * INTERVAL)]
    response = httpx.Response(200, json=payload)
    mock = MockHttpClient(response)

    client = BinanceMarketDataClient(
        base_url="https://api.binance.com",
        http_client=mock,
        request_delay_seconds=0,
    )

    with pytest.raises(DataValidationError):
        client.get_historical_klines(
            symbol="BTCUSDT",
            timeframe="5m",
            start=datetime.fromtimestamp(START / 1000, tz=timezone.utc),
            end=datetime.fromtimestamp((START + 3 * INTERVAL) / 1000, tz=timezone.utc),
        )


def test_client_rejects_unaligned_request():
    response = httpx.Response(200, json=[])
    mock = MockHttpClient(response)

    client = BinanceMarketDataClient(
        base_url="https://api.binance.com",
        http_client=mock,
    )

    with pytest.raises(ValueError, match="not aligned"):
        client.get_historical_klines(
            symbol="BTCUSDT",
            timeframe="5m",
            start=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        )


def test_client_rejects_http_error():
    response = httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    mock = MockHttpClient(response)

    client = BinanceMarketDataClient(
        base_url="https://api.binance.com",
        http_client=mock,
        max_retries=0,
    )

    with pytest.raises(Exception):
        client.get_historical_klines(
            symbol="BTCUSDT",
            timeframe="5m",
            start=datetime.fromtimestamp(START / 1000, tz=timezone.utc),
            end=datetime.fromtimestamp((START + INTERVAL) / 1000, tz=timezone.utc),
        )
## 18. scripts/download_candles.py

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from trading_app.config import get_settings
from trading_app.data.binance_client import BinanceMarketDataClient
from trading_app.data.repository import CandleRepository, create_engine_from_url
from trading_app.data.service import MarketDataService


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Datetime must include a timezone.")

    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Binance Spot historical candles."
    )

    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--start", required=True, type=parse_datetime)
    parser.add_argument("--end", required=True, type=parse_datetime)

    args = parser.parse_args()
    settings = get_settings()

    engine = create_engine_from_url(settings.database_url)
    repository = CandleRepository(engine)
    repository.create_tables()

    client = BinanceMarketDataClient(
        base_url=settings.binance_base_url,
        timeout_seconds=settings.binance_timeout_seconds,
        max_retries=settings.binance_max_retries,
        request_delay_seconds=settings.binance_request_delay_seconds,
    )

    try:
        service = MarketDataService(
            settings=settings,
            client=client,
            repository=repository,
        )

        inserted = service.download_and_store(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
        )

        total = repository.count(
            symbol=args.symbol.upper(),
            timeframe=args.timeframe,
        )

        print(f"New candles inserted: {inserted}")
        print(f"Total stored candles: {total}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
## 19. Installation

From the project root:
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
Windows PowerShell activation/copy commands:
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
## 20. Run the tests

pytest
pytest -v
pytest --cov=trading_app --cov-report=term-missing
## 21. Test the real public-data path

Example: download one hour of BTCUSDT 5-minute candles. This should produce 12 candles.
python scripts/download_candles.py \
  --symbol BTCUSDT \
  --timeframe 5m \
  --start 2026-01-05T00:00:00+00:00 \
  --end 2026-01-05T01:00:00+00:00
Run the same command again. Expected behavior:
New candles inserted: 0
Total stored candles: 12
## 22. Verify SQLite data

sqlite3 data/trading.db
.tables
SELECT symbol, timeframe, open_time_ms, open_price, high_price,
low_price, close_price, volume, trade_count
FROM candles
ORDER BY open_time_ms;
SELECT symbol, timeframe, COUNT(*) AS candle_count
FROM candles
GROUP BY symbol, timeframe;
SELECT symbol, timeframe, open_time_ms, COUNT(*) AS n
FROM candles
GROUP BY symbol, timeframe, open_time_ms
HAVING COUNT(*) > 1;
## 23. Verify timestamp continuity

For 5m data, consecutive candle open timestamps must differ by 300,000 ms. For 15m, 1h and 4h the intervals are 900,000 ms, 3,600,000 ms and 14,400,000 ms.
SELECT
    open_time_ms,
    open_time_ms - LAG(open_time_ms) OVER (
        ORDER BY open_time_ms
    ) AS delta_ms
FROM candles
WHERE symbol = 'BTCUSDT'
  AND timeframe = '5m'
ORDER BY open_time_ms;
## 24. Verify OHLC correctness

SELECT COUNT(*)
FROM candles
WHERE CAST(high_price AS REAL) < CAST(open_price AS REAL)
   OR CAST(high_price AS REAL) < CAST(close_price AS REAL)
   OR CAST(low_price AS REAL) > CAST(open_price AS REAL)
   OR CAST(low_price AS REAL) > CAST(close_price AS REAL)
   OR CAST(low_price AS REAL) > CAST(high_price AS REAL);
Expected result: 0.
## 25. Verify invalid-volume handling

The validator rejects negative volume and quote volume, non-numeric values, NaN and Infinity. Run:
pytest tests/unit/test_validator.py -v
## 26. Verify suspicious data is not silently repaired

pytest tests/unit/test_validator.py::test_missing_candle_is_rejected -v
pytest tests/unit/test_validator.py::test_duplicate_candle_is_rejected -v
A duplicate already present in SQLite is ignored for idempotent ingestion, while a duplicate or gap inside downloaded market data causes validation failure. No missing candle is fabricated.
## 27. Design note: decimal preservation

SQLite does not provide a native arbitrary-precision decimal type. Prices and volumes are therefore stored as exact decimal strings and converted explicitly at the analytical boundary. Timestamps are stored as UTC epoch milliseconds.
## 28. Milestone 1 acceptance checklist

- Python 3.12 project structure
- Pydantic configuration
- Configurable symbols/timeframes
- Public Binance Spot market-data client
- No API keys
- No private endpoints
- Historical kline download
- Pagination
- Rate-limit retry handling
- SQLite/SQLAlchemy persistence
- Composite uniqueness constraint
- Application-level duplicate prevention
- Timestamp alignment validation
- Candle-duration validation
- Monotonic timestamp validation
- Missing-candle detection
- Duplicate-candle detection
- Invalid-price detection
- Invalid-volume detection
- OHLC consistency validation
- No silent data repair
- Mocked Binance tests
- Exact decimal preservation in storage
- Repeatable ingestion
- Direct SQLite verification procedure
- No trading code
Scope boundary: stop after Milestone 1. The next stage should add stronger data-ingestion integration tests and an explicit dataset/data-quality report before strategies consume these candles.
