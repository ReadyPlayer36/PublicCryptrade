"""Live acceptance scenarios, represented offline with deterministic fake public responses."""
from datetime import datetime, timezone

import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
from trading_app.data.binance_client import BinanceMarketDataClient

START_MS = 1767571200000
START = datetime.fromtimestamp(START_MS / 1000, tz=timezone.utc)
END = datetime.fromtimestamp((START_MS + 12 * 300000) / 1000, tz=timezone.utc)   # one hour = 12 x 5m
SERVER_MS = START_MS + 13 * 300000


def make_client(http):
    return BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=0)


@pytest.mark.requirement("LIVE-01")
def test_btcusdt_5m_12_candles():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": SERVER_MS}), FakeResponse(payload=make_rows(START_MS, 12))])
    rows = make_client(http).get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert len(rows) == 12
    assert rows[0][0] == START_MS and rows[-1][0] == START_MS + 11 * 300000
    assert len(http.calls) == 2


@pytest.mark.requirement("LIVE-02")  # client-level stand-in: a rerun yields identical rows, so storage can insert zero new ones
def test_immediate_rerun_zero_new_rows():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": SERVER_MS}), FakeResponse(payload=make_rows(START_MS, 12)),
                           FakeResponse(payload={"serverTime": SERVER_MS}), FakeResponse(payload=make_rows(START_MS, 12))])
    client = make_client(http)
    first = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    second = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=START, end=END)
    assert first == second and len(first) == 12
    assert len(http.calls) == 4
