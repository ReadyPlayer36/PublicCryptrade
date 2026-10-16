"""Application configuration (public market data only). There are deliberately NO secret fields."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from trading_app.data.binance_client import validate_base_url
from trading_app.data.validator import TIMEFRAME_MS

_SYMBOL = re.compile(r"[A-Z0-9]{2,20}")


def _split(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item).strip() for item in value]
    raise ValueError("expected a comma-separated string or a list")


class Settings(BaseSettings):
    """Settings loaded from environment variables / .env. Unknown variables are ignored."""

    app_name: str = "binance-research"
    app_env: str = "development"

    database_url: str = "sqlite:///./data/trading.db"
    cooldown_path: str = "data/binance_cooldown.json"

    binance_base_url: str = "https://data-api.binance.vision"
    binance_timeout_seconds: float = 10.0
    finality_lag_ms: int | None = None          # no default until the lag experiment is approved
    max_candles_per_fetch: int = 100_000

    allowed_symbols: Annotated[tuple[str, ...], NoDecode] = ("BTCUSDT", "ETHUSDT")
    allowed_timeframes: Annotated[tuple[str, ...], NoDecode] = ("5m", "15m", "1h", "4h")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @field_validator("binance_base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        return validate_base_url(value)

    @field_validator("binance_timeout_seconds")
    @classmethod
    def _timeout(cls, value: float) -> float:
        if not value > 0 or value != value or value == float("inf"):
            raise ValueError("binance_timeout_seconds must be a finite number > 0")
        return value

    @field_validator("finality_lag_ms")
    @classmethod
    def _lag(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("finality_lag_ms must be >= 0")
        return value

    @field_validator("max_candles_per_fetch")
    @classmethod
    def _max_candles(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_candles_per_fetch must be >= 1")
        return value

    @field_validator("database_url", "cooldown_path")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("allowed_symbols", mode="before")
    @classmethod
    def _symbols(cls, value: object) -> tuple[str, ...]:
        items = tuple(dict.fromkeys(item.upper() for item in _split(value)))
        if not items:
            raise ValueError("allowed_symbols must not be empty")
        bad = [item for item in items if not _SYMBOL.fullmatch(item)]
        if bad:
            raise ValueError(f"invalid symbol(s): {bad}")
        return items

    @field_validator("allowed_timeframes", mode="before")
    @classmethod
    def _timeframes(cls, value: object) -> tuple[str, ...]:
        items = tuple(dict.fromkeys(_split(value)))
        if not items:
            raise ValueError("allowed_timeframes must not be empty")
        bad = [item for item in items if item not in TIMEFRAME_MS]
        if bad:
            raise ValueError(f"unsupported timeframe(s): {bad}; supported: {sorted(TIMEFRAME_MS)}")
        return items


@lru_cache
def get_settings() -> Settings:
    return Settings()
