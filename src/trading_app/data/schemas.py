"""Validated candle schema (normalized, Decimal-exact)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DECIMAL_FIELDS = ("open", "high", "low", "close", "volume", "quote_volume")


class Candle(BaseModel):
    """Validated OHLCV candle. Prices and volumes are Decimal; floats are rejected."""

    model_config = ConfigDict(frozen=True, strict=False)

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

    @field_validator(*_DECIMAL_FIELDS, mode="before")
    @classmethod
    def _no_floats(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise ValueError("decimal fields must be Decimal, int or decimal strings, never float/bool")
        return value

    @field_validator(*_DECIMAL_FIELDS)
    @classmethod
    def _finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("decimal fields must be finite")
        return value

    @field_validator("open_time", "close_time")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value
