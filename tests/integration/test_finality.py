"""Client-level finality range clamping and upstream non-final abort tests."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from trading_app.data.finality import EmptyEffectiveRangeError, NonFinalCandleError
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/finality_vectors.json").read_text())
START = datetime.fromtimestamp(1767571200000/1000, timezone.utc)
END = datetime.fromtimestamp(1767571500000/1000, timezone.utc)
FUTURE = datetime.fromtimestamp(1767601200000/1000, timezone.utc)

@pytest.mark.requirement("FINAL-01")
def test_client_clamps_end_time_to_finality_boundary():
    s = VECTORS["extra"]["future_end"]["S_ms"]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": s}), FakeResponse(payload=make_rows(1767571200000, 10))])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", finality_lag_ms=0, http_client=http)
    result = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=FUTURE)
    kline_calls = [params for url, params in http.calls if url.endswith("/api/v3/klines")]
    assert len(result) == 10
    assert len(kline_calls) == 1
    assert kline_calls[0]["endTime"] == VECTORS["extra"]["future_end"]["expected_effective_end_ms"] - 1

@pytest.mark.requirement("FINAL-03")
def test_future_end_reports_requested_and_effective_ranges():
    s = VECTORS["extra"]["future_end"]["S_ms"]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": s}), FakeResponse(payload=make_rows(1767571200000, 10))])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", finality_lag_ms=0, http_client=http)
    result = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=FUTURE)
    assert len(result) == 10
    assert http.calls[1][1]["endTime"] == VECTORS["extra"]["future_end"]["expected_effective_end_ms"] - 1

@pytest.mark.requirement("FINAL-07")
def test_b_not_final_vectors_shrink_to_explicit_empty_range():
    for case in VECTORS["cases"]:
        if case["case"] != "B_not_final":
            continue
        client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", finality_lag_ms=case["L_ms"], http_client=FakeHttpClient([FakeResponse(payload={"serverTime": case["S_ms"]})]))
        with pytest.raises(EmptyEffectiveRangeError, match="effective.*range|effective_end"):
            client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)

@pytest.mark.requirement("FINAL-06")
def test_returned_nonfinal_candle_aborts_fetch():
    s = VECTORS["cases"][0]["S_ms"]
    kline = [VECTORS["cases"][0]["candle_open_ms"], "100.10", "101.00", "99.50", "100.50", "12.345", VECTORS["cases"][0]["B_ms"], "1240", 100, "0", "0", "0"]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": s}), FakeResponse(payload=[kline])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", finality_lag_ms=0, http_client=http)
    with pytest.raises(NonFinalCandleError, match="non-final|finality|close"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert len(http.calls) == 2

@pytest.mark.requirement("FINAL-01")
def test_server_time_failure_aborts_without_kline_request():
    http = FakeHttpClient(errors=[TimeoutError("server time down") for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="timeout"):
        client.get_server_time()
    assert len(http.calls) == 4


@pytest.mark.requirement("FINAL-01")
@pytest.mark.parametrize("lag_ms", [0], ids=["lag-0ms"])
def test_boundary_rule(lag_ms):
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000}), FakeResponse(payload=make_rows(1767571200000, 1))])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=lag_ms)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert [r[0] for r in rows] == [1767571200000]
    assert http.calls[1][1]["endTime"] == 1767571500000 - 1

@pytest.mark.requirement("FINAL-01")
def test_no_local_clock_fallback():
    http = FakeHttpClient(errors=[TimeoutError("server time unavailable") for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: 999_999_999_999_999)
    with pytest.raises(BinanceClientError, match="timeout"):
        client.get_server_time()
    assert len(http.calls) == 4

@pytest.mark.requirement("FINAL-01")
@pytest.mark.parametrize("failure", ["invalid-timestamp", "malformed-time", "server-time-failure"], ids=["invalid-timestamp", "malformed-time", "server-time-failure"])
def test_server_time_failure_aborts(failure):
    if failure == "invalid-timestamp":
        http = FakeHttpClient([FakeResponse(payload={"serverTime": -1})])
    elif failure == "malformed-time":
        http = FakeHttpClient([FakeResponse(payload={"serverTime": "not-an-integer"})])
    else:
        http = FakeHttpClient(errors=[TimeoutError("server time down") for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="time|timestamp|server"):
        client.get_server_time()
    assert len(http.calls) == (4 if failure == "server-time-failure" else 1)

@pytest.mark.requirement("FINAL-02")
def test_nonfinal_candle_during_pagination_aborts():
    s = 1767571500000
    row = [1767571200000, "100", "101", "99", "100", "1", s, "100", 1, "0", "0", "0"]
    http = FakeHttpClient([FakeResponse(payload={"serverTime": s}), FakeResponse(payload=[row])])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=0)
    from trading_app.data.finality import NonFinalCandleError
    with pytest.raises(NonFinalCandleError, match="non-final|finality|close"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert len(http.calls) == 2


@pytest.mark.requirement("FINAL-01")
def test_boundary_vectors_with_positive_lag_clamp_the_request():
    for case in VECTORS["cases"]:
        if case["case"] != "B-1_is_final":
            continue
        http = FakeHttpClient([FakeResponse(payload={"serverTime": case["S_ms"]}), FakeResponse(payload=make_rows(1767571200000, 1))])
        client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=case["L_ms"])
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
        assert http.calls[1][1]["endTime"] == case["expected_effective_end_ms"] - 1
