"""Only public Binance Spot market-data access exists: no keys, no private endpoints, exact hosts."""
from datetime import datetime, timezone

import httpx
import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
from trading_app.data.binance_client import BinanceMarketDataClient, validate_base_url, validate_public_url

S0 = 1767571200000


def run_fetch():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": S0 + 10 * 300000}), FakeResponse(payload=make_rows(S0, 3))])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=0)
    client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=datetime.fromtimestamp(S0 / 1000, timezone.utc),
                                 end=datetime.fromtimestamp((S0 + 3 * 300000) / 1000, timezone.utc))
    return http, client


@pytest.mark.requirement("M1-04")
def test_no_api_keys():
    http, _ = run_fetch()
    for _, params in http.calls:
        assert not [k for k in params if any(w in k.lower() for w in ("key", "signature", "timestamp", "recvwindow", "token", "secret"))]
    default = BinanceMarketDataClient(base_url="https://data-api.binance.vision")
    try:
        assert isinstance(default.http_client, httpx.Client)
        assert not [h for h in default.http_client.headers if any(w in h.lower() for w in ("key", "auth", "signature", "token", "secret", "mbx"))]
    finally:
        default.close()
    import inspect
    assert not [n for n in inspect.signature(BinanceMarketDataClient.__init__).parameters if any(w in n.lower() for w in ("key", "secret", "token", "password"))]


@pytest.mark.requirement("M1-04")
def test_no_private_endpoints():
    http, _ = run_fetch()
    assert {u.rsplit("/api/v3/", 1)[1] for u, _ in http.calls} == {"time", "klines"}
    for path in ("/api/v3/order", "/api/v3/account", "/api/v3/myTrades", "/api/v3/openOrders", "/sapi/v1/capital/withdraw/apply",
                 "/fapi/v1/order", "/api/v3/userDataStream", "/wapi/v3/withdraw.html"):
        with pytest.raises(ValueError):
            validate_public_url("https://data-api.binance.vision" + path)


@pytest.mark.requirement("M1-04")
def test_public_spot_market_data_only():
    for host in ("fapi.binance.com", "dapi.binance.com", "eapi.binance.com", "stream.binance.com", "testnet.binance.vision",
                 "demo-api.binance.com", "api1.binance.com", "api-gcp.binance.com", "papi.binance.com"):
        with pytest.raises(ValueError):
            validate_base_url("https://" + host)
    assert validate_base_url("https://data-api.binance.vision") == "https://data-api.binance.vision"
    assert validate_base_url("https://api.binance.com") == "https://api.binance.com"
    http, _ = run_fetch()
    assert all(u.startswith("https://data-api.binance.vision/api/v3/") for u, _ in http.calls)
