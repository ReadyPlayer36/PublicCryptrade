"""Finality boundary contract tests driven by independently supplied vectors."""
import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from trading_app.data.finality import is_final, effective_end_ms, EmptyEffectiveRangeError, NaiveDatetimeError
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.policy import frozen_policy

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/finality_vectors.json").read_text())
START = datetime.fromtimestamp(1767571200000 / 1000, tz=timezone.utc)

@pytest.mark.requirement("FINAL-01")
@pytest.mark.requirement("FINAL-04")
@pytest.mark.requirement("FINAL-08")
@pytest.mark.parametrize("lag_ms", [0, 60000], ids=["lag-0ms", "lag-positive"])
def test_boundary_rule(lag_ms):
    cases = [case for case in VECTORS["cases"] if case["L_ms"] == lag_ms]
    assert len(cases) == 3
    for case in cases:
        assert is_final(case["candle_close_ms"], case["S_ms"], case["L_ms"]) is case["expected_final"]

@pytest.mark.requirement("FINAL-05")
def test_effective_end_formula():
    for case in VECTORS["cases"]:
        assert effective_end_ms(case["requested_end_ms"], case["S_ms"], case["L_ms"], VECTORS["interval_ms"]) == case["expected_effective_end_ms"]
    future = VECTORS["extra"]["future_end"]
    assert effective_end_ms(future["requested_end_ms"], future["S_ms"], future["L_ms"], VECTORS["interval_ms"]) == future["expected_effective_end_ms"]

@pytest.mark.requirement("FINAL-07")
def test_empty_effective_range_and_input_validation():
    end = VECTORS["extra"]["empty_effective_range"]
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient([FakeResponse(payload={"serverTime": end["S_ms"]})]))
    with pytest.raises(EmptyEffectiveRangeError, match="effective.*range|effective_end"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=datetime.fromtimestamp(end["requested_start_ms"]/1000, timezone.utc), end=datetime.fromtimestamp(end["requested_end_ms"]/1000, timezone.utc))
    with pytest.raises(NaiveDatetimeError, match="naive|timezone"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=datetime(2024,1,1), end=datetime(2024,1,2))

@pytest.mark.requirement("LAG-01")
def test_finality_lag_has_no_default():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match="lag|configuration|finality"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=datetime.fromtimestamp(1767571500, timezone.utc))
    assert len(http.calls) == 1

@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    # Timeouts are retried per the frozen policy (4 attempts); the fetch then fails closed.
    http = FakeHttpClient(errors=[TimeoutError("server time unavailable") for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http,
                                     sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: 999_999_999_999_999)
    with pytest.raises(BinanceClientError, match="timeout"):
        client.get_server_time()
    assert len(http.calls) == 4
