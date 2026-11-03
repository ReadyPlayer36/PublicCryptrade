"""SQLAlchemy table definition. Decimals are stored as exact strings (format(d, "f"))."""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class CandleModel(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
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
        UniqueConstraint("symbol", "timeframe", "open_time_ms", name="uq_candle_symbol_timeframe_open_time"),
    )


class DataFetchModel(Base):
    """One row per fetch attempt (success or failure): the audit and metadata record."""

    __tablename__ = "data_fetches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    effective_end_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    server_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finality_lag_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    host: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_text: Mapped[str | None] = mapped_column(String(240), nullable=True)
    fetched_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
