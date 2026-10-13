"""Public-client acceptance tests use canned public HTTP responses only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from tests.fixtures.policy import frozen_policy, retry_policy, cooldown_policy
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
START = datetime.fromtimestamp(1767571200, tz=timezone.utc)
END = datetime.fromtimestamp(1767571500, tz=timezone.utc)
VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/retry_cooldown_vectors.json").read_text())

@pytest.mark.requirement("M1-06")
def test_retry_policy():
    http = FakeHttpClient([FakeResponse(status_code=500) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="500|retry|request"):
        client.get_server_time()
    assert len(http.calls) == retry_policy()["attempts_total"]
    assert sleeps == [1, 2, 3]

@pytest.mark.requirement("M1-12")
def test_binance_responses_are_mocked():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 123})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    result = client.get_server_time()
    assert result == 123
    assert len(http.calls) == 1
    assert http.calls[0][0].endswith("/api/v3/time")

@pytest.mark.requirement("RETRY-06")
def test_429_without_retry_after_uses_backoff():
    http = FakeHttpClient([FakeResponse(status_code=429) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="429|rate limit|retry"):
        client.get_server_time()
    assert len(http.calls) == 4
    assert sleeps == VECTORS["cases"][10]["expected_sleeps_s"]

@pytest.mark.requirement("RETRY-04")
def test_backoff_cap_and_jitter():
    http = FakeHttpClient([FakeResponse(status_code=500) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.25)
    with pytest.raises(BinanceClientError, match="500|retry|request"):
        client.get_server_time()
    assert sleeps == VECTORS["cases"][0]["expected_sleeps_s"]
    assert len(http.calls) == 4

@pytest.mark.requirement("RETRY-05")
def test_fetch_sleep_budget_and_cooldown():
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": "11"}) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="429|budget|cooldown|retry"):
        client.get_server_time()
    assert sleeps == [11, 11]
    assert len(http.calls) == 3
    assert retry_policy()["sleep_budget_seconds"] == 30

@pytest.mark.requirement("RETRY-01")
def test_malformed_json_retry():
    http = FakeHttpClient([FakeResponse(status_code=200, json_error=ValueError("bad json")) for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="JSON|malformed|response"):
        client.get_server_time()
    assert len(http.calls) == 4
    assert sleeps == [1, 2, 3]

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("status", [400, 403, 418], ids=["400", "403", "418"])
def test_no_retry_status(status):
    http = FakeHttpClient([FakeResponse(status_code=status)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match=str(status)):
        client.get_server_time()
    assert len(http.calls) == 1

@pytest.mark.requirement("RETRY-03")
def test_only_retry_configured_statuses():
    for status, expected_requests in ((400, 1), (403, 1), (418, 1), (500, 4), (502, 4), (503, 4), (504, 4), (429, 4)):
        http = FakeHttpClient([FakeResponse(status_code=status) for _ in range(4)])
        client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0)
        with pytest.raises(BinanceClientError, match=str(status)):
            client.get_server_time()
        assert len(http.calls) == expected_requests

@pytest.mark.requirement("RETRY-01")
def test_read_timeout_retry():
    http = FakeHttpClient(errors=[TimeoutError("read timeout") for _ in range(4)])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="timeout|request"):
        client.get_server_time()
    assert len(http.calls) == 4
    assert sleeps == [1, 2, 3]

@pytest.mark.requirement("RETRY-01")
def test_repeated_429_persists_cooldown():
    http = FakeHttpClient([FakeResponse(status_code=429) for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match="429|cooldown|rate limit"):
        client.get_server_time()
    assert len(http.calls) == 4

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("retry_after", [10, 45, 61], ids=["429", "over-budget", "over-cap"])
def test_retry_after_cap_and_no_jitter(retry_after):
    policy = retry_policy()["retry_after"]
    assert policy["sleep_jitter"] is False
    assert policy["max_seconds"] == 60
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": str(retry_after)})])
    sleeps = []
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=sleeps.append, jitter=lambda: 0.75)
    with pytest.raises(BinanceClientError, match="429|retry|cooldown|budget"):
        client.get_server_time()
    assert len(http.calls) == (4 if retry_after == 10 else 1)
    assert all(wait == retry_after for wait in sleeps)

@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("status", [429, 500], ids=["429", "500"])
def test_retry_status(status):
    http = FakeHttpClient([FakeResponse(status_code=status) for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match=str(status)):
        client.get_server_time()
    assert len(http.calls) == 4

@pytest.mark.requirement("RETRY-02")
def test_timeout_retry_and_connect_fallback():
    policy = retry_policy()
    assert "read_timeout" in policy["retry_errors"]
    assert policy["connect_dns"] == "fallback_only_before_first_successful_server_time"
    http = FakeHttpClient(errors=[TimeoutError("timeout") for _ in range(4)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0)
    with pytest.raises(BinanceClientError, match="timeout|request"):
        client.get_server_time()
    assert len(http.calls) == 4

@pytest.mark.requirement("RETRY-02")
@pytest.mark.parametrize("timeout_type", ["read", "write", "pool"], ids=["read-timeout", "write-timeout", "pool-timeout"])
def test_read_write_and_pool_timeouts_retry_same_host(timeout_type):
    import httpx
    from tests.fixtures.fakes import SequenceFakeHttpClient
    exc = {"read": httpx.ReadTimeout, "write": httpx.WriteTimeout, "pool": httpx.PoolTimeout}[timeout_type]("timeout")
    http = SequenceFakeHttpClient([exc, exc, exc, exc])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: 1767571500000)
    with pytest.raises(BinanceClientError, match="timeout|request"):
        client.get_server_time()
    assert len(http.calls) == 4
    assert {url.split("/")[2] for url, _ in http.calls} == {"data-api.binance.vision"}

@pytest.mark.requirement("RETRY-02")
@pytest.mark.parametrize("error_type", ["connect-error", "connect-timeout"], ids=["connect-error", "connect-timeout"])
def test_connect_failures_fallback_only_before_first_successful_time_call(error_type):
    import httpx
    from tests.fixtures.fakes import SequenceFakeHttpClient
    exc = httpx.ConnectError("connect failed") if error_type == "connect-error" else httpx.ConnectTimeout("connect timed out")
    http = SequenceFakeHttpClient([exc, FakeResponse(payload={"serverTime": 1767571500000})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: 1767571500000)
    assert client.get_server_time() == 1767571500000
    assert [url.split("/")[2] for url, _ in http.calls] == ["data-api.binance.vision", "api.binance.com"]


@pytest.mark.requirement("RETRY-02")
def test_connect_failure_after_success_does_not_fallback():
    import httpx
    from tests.fixtures.fakes import SequenceFakeHttpClient
    http = SequenceFakeHttpClient([
        FakeResponse(payload={"serverTime": 1767571500000}),
        httpx.ConnectError("later connection failure"),
        httpx.ConnectError("later connection failure"),
        httpx.ConnectError("later connection failure"),
        httpx.ConnectError("later connection failure"),
    ])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: 1767571500000)
    assert client.get_server_time() == 1767571500000
    with pytest.raises(BinanceClientError, match="connect|request|server"):
        client.get_server_time()
    assert len(http.calls) == 5
    assert {url.split("/")[2] for url, _ in http.calls} == {"data-api.binance.vision"}
