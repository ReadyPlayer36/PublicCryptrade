"""Settings: allowlists, validation, and the absence of any secret configuration."""
import dataclasses
import os

import pytest
from pydantic import ValidationError

from tests.fixtures.policy import frozen_policy
from trading_app.config import Settings, get_settings

SECRET_WORDS = ("key", "secret", "token", "password", "passphrase", "signature", "credential", "auth")


def make(monkeypatch, **env):
    for name in list(os.environ):
        if name.upper() in {"ALLOWED_SYMBOLS", "ALLOWED_TIMEFRAMES", "DATABASE_URL", "BINANCE_BASE_URL", "FINALITY_LAG_MS",
                            "BINANCE_TIMEOUT_SECONDS", "MAX_CANDLES_PER_FETCH", "COOLDOWN_PATH", "API_KEY", "BINANCE_API_KEY"}:
            monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.mark.requirement("M1-03")
def test_configured_symbols_and_timeframes(monkeypatch):
    defaults = make(monkeypatch)
    assert defaults.allowed_symbols == ("BTCUSDT", "ETHUSDT")
    assert defaults.allowed_timeframes == ("5m", "15m", "1h", "4h")
    configured = make(monkeypatch, ALLOWED_SYMBOLS="btcusdt, SOLUSDT ,BTCUSDT", ALLOWED_TIMEFRAMES="5m,1h")
    assert configured.allowed_symbols == ("BTCUSDT", "SOLUSDT")        # upper-cased, de-duplicated, order kept
    assert configured.allowed_timeframes == ("5m", "1h")


@pytest.mark.requirement("M1-02")
def test_pydantic_config_has_no_secret_fields(monkeypatch):
    fields = Settings.model_fields
    assert not [n for n in fields if any(w in n.lower() for w in SECRET_WORDS)]
    settings = make(monkeypatch, API_KEY="LEAKME", BINANCE_API_KEY="LEAKME2")
    assert "LEAKME" not in repr(settings) and "LEAKME" not in str(settings.model_dump())
    assert not hasattr(settings, "api_key") and not hasattr(settings, "binance_api_key")
    assert Settings.model_config["extra"] == "ignore"


@pytest.mark.requirement("M1-03")
def test_symbol_allowlist(monkeypatch):
    for value in ["", " , ", "BTC/USDT", "BTCUSDT;DROP", "B", "BTCUSDT&x=1", "btc usdt"]:
        with pytest.raises(ValidationError):
            make(monkeypatch, ALLOWED_SYMBOLS=value)


@pytest.mark.requirement("M1-03")
def test_symbol_and_timeframe_allowlist(monkeypatch):
    for value in ["", "2m", "5m,2m", "1d", "5M", "5m;1h"]:
        with pytest.raises(ValidationError):
            make(monkeypatch, ALLOWED_TIMEFRAMES=value)
    with pytest.raises(ValidationError):
        make(monkeypatch, ALLOWED_SYMBOLS="BTCUSDT,", ALLOWED_TIMEFRAMES="3m")
    assert make(monkeypatch, ALLOWED_SYMBOLS="ETHUSDT", ALLOWED_TIMEFRAMES="4h").allowed_timeframes == ("4h",)


@pytest.mark.requirement("M1-03")
def test_timeframes_are_limited_to_the_frozen_validator_set():
    from trading_app.data.validator import TIMEFRAME_MS
    assert set(TIMEFRAME_MS) == {"5m", "15m", "1h", "4h"}


@pytest.mark.requirement("M1-02")
@pytest.mark.parametrize("name,value", [
    ("BINANCE_BASE_URL", "http://data-api.binance.vision"), ("BINANCE_BASE_URL", "https://evil.example"),
    ("BINANCE_BASE_URL", "https://testnet.binance.vision"), ("BINANCE_BASE_URL", "https://data-api.binance.vision/api"),
    ("BINANCE_TIMEOUT_SECONDS", "0"), ("BINANCE_TIMEOUT_SECONDS", "-1"), ("BINANCE_TIMEOUT_SECONDS", "inf"),
    ("BINANCE_TIMEOUT_SECONDS", "nan"), ("FINALITY_LAG_MS", "-1"), ("FINALITY_LAG_MS", "1.5"),
    ("MAX_CANDLES_PER_FETCH", "0"), ("DATABASE_URL", " "), ("COOLDOWN_PATH", ""),
])
def test_invalid_values_are_rejected(monkeypatch, name, value):
    with pytest.raises(ValidationError):
        make(monkeypatch, **{name: value})


@pytest.mark.requirement("M1-02")
def test_defaults_match_frozen_policy_and_lag_has_no_default(monkeypatch):
    settings = make(monkeypatch)
    policy = frozen_policy()
    assert settings.binance_base_url == "https://" + policy["network"]["hosts"]["primary"]
    assert settings.max_candles_per_fetch == policy["storage"]["max_candles_per_fetch"] == 100_000
    assert settings.finality_lag_ms is None                              # explicit operator decision required
    assert settings.cooldown_path == "data/binance_cooldown.json"
    assert make(monkeypatch, FINALITY_LAG_MS="0").finality_lag_ms == 0   # zero is valid by design


@pytest.mark.requirement("M1-02")
def test_get_settings_is_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.chdir(os.path.dirname(__file__))
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
