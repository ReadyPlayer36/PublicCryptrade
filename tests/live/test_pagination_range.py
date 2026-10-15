"""Pagination contract test uses fake upstream pages only; no live requests are sent."""
from datetime import datetime, timezone

import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
from trading_app.data.binance_client import BinanceMarketDataClient

START_MS = 1767571200000


@pytest.mark.requirement("LIVE-03")
def test_1152_candles_two_pages():
    start = datetime.fromtimestamp(START_MS / 1000, timezone.utc)
    end = datetime.fromtimestamp((START_MS + 1152 * 300000) / 1000, timezone.utc)
    page1 = make_rows(START_MS, 1000)
    page2 = make_rows(START_MS + 1000 * 300000, 152)
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1768000000000}), FakeResponse(payload=page1), FakeResponse(payload=page2)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=0)
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=start, end=end)
    assert len(rows) == 1152
    kline_calls = [(u, p) for u, p in http.calls if u.endswith("/api/v3/klines")]
    assert len(kline_calls) == 2
    assert [p["startTime"] for _, p in kline_calls] == [START_MS, START_MS + 1000 * 300000]
    assert all(p["limit"] == 1000 for _, p in kline_calls)
    assert [r[0] for r in rows] == sorted({r[0] for r in rows})
