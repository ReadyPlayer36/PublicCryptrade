"""Stage B2: request engine, host policy, cooldown integration. Fakes only; no network."""
import json

import httpx
import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse, SequenceFakeHttpClient
from tests.fixtures.policy import frozen_policy
from trading_app.data import binance_client as bc
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient, validate_base_url, validate_public_url

BASE = "https://data-api.binance.vision"
NOW = 1_767_571_500_000
OK = {"serverTime": NOW}


def make(http, **kw):
    kw.setdefault("sleep", lambda _: None)
    kw.setdefault("jitter", lambda: 0.0)
    kw.setdefault("now_ms", lambda: NOW)
    return BinanceMarketDataClient(base_url=BASE, http_client=http, **kw)


# ---- host policy -------------------------------------------------------------
@pytest.mark.requirement("NET-01")
def test_host_constants_match_frozen_policy():
    net = frozen_policy()["network"]
    assert (bc.PRIMARY_HOST, bc.FALLBACK_HOST) == (net["hosts"]["primary"], net["hosts"]["fallback"])
    assert set(bc.ALLOWED_HOSTS).isdisjoint(net["hosts"]["excluded"])
    assert [bc.TIME_PATH, bc.KLINES_PATH] == net["paths"]
    assert net["https_only"] is True and net["follow_redirects"] is False


@pytest.mark.requirement("NET-01")
def test_retry_constants_match_frozen_policy():
    r = frozen_policy()["retry"]
    assert bc.ATTEMPTS_TOTAL == r["attempts_total"]
    assert bc.RETRY_STATUSES == set(r["retry_statuses"])
    b = r["backoff"]
    assert (bc.BACKOFF_BASE_S, bc.BACKOFF_FACTOR, bc.BACKOFF_CAP_S, bc.JITTER_MAX_S) == (
        b["base_seconds"], b["factor"], b["cap_seconds"], b["jitter_max_seconds"])
    assert bc.RETRY_AFTER_MAX_S == r["retry_after"]["max_seconds"]
    assert bc.SLEEP_BUDGET_S == r["sleep_budget_seconds"]


@pytest.mark.requirement("NET-01")
@pytest.mark.parametrize("url", [
    "http://data-api.binance.vision", "https://api1.binance.com", "https://api2.binance.com", "https://api3.binance.com",
    "https://api4.binance.com", "https://api-gcp.binance.com", "https://testnet.binance.vision", "https://demo-api.binance.com",
    "https://evil.example", "https://data-api.binance.vision.evil.example", "https://user:pw@data-api.binance.vision",
    "https://data-api.binance.vision:8443", "https://data-api.binance.vision/api/v3/time", "https://data-api.binance.vision/?x=1",
    "ftp://data-api.binance.vision", "", "https://",
])
def test_disallowed_base_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)
    with pytest.raises(ValueError):
        BinanceMarketDataClient(base_url=url, http_client=FakeHttpClient())


@pytest.mark.requirement("NET-01")
@pytest.mark.parametrize("url", [BASE, BASE + "/", "https://DATA-API.binance.vision", "https://api.binance.com"])
def test_allowed_base_urls_normalize_to_bare_origin(url):
    assert validate_base_url(url) == "https://" + url.split("//")[1].rstrip("/").lower()


@pytest.mark.requirement("NET-02")
def test_default_http_client_never_follows_redirects_and_sends_no_credentials():
    client = BinanceMarketDataClient(base_url=BASE)
    try:
        assert client.http_client.follow_redirects is False
        assert not any("key" in k.lower() or "signature" in k.lower() for k in client.http_client.headers)
    finally:
        client.close()


@pytest.mark.requirement("NET-02")
def test_time_request_has_no_params_or_credentials():
    http = FakeHttpClient([FakeResponse(payload=OK)])
    make(http).get_server_time()
    assert http.calls == [(BASE + "/api/v3/time", {})]


@pytest.mark.requirement("RETRY-01")
def test_redirect_is_an_error_and_not_retried():
    http = FakeHttpClient([FakeResponse(status_code=302, headers={"Location": "https://evil.example"})])
    with pytest.raises(BinanceClientError, match="302"):
        make(http).get_server_time()
    assert len(http.calls) == 1


@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("payload", [{"msg": "x"}, {"serverTime": "1767571500000"}, {"serverTime": True}, {"serverTime": 0},
                                     {"serverTime": -5}, {"serverTime": 1.5}, [], None, "x"])
def test_wrong_shape_2xx_is_not_retried(payload):
    http = FakeHttpClient([FakeResponse(payload=payload)])
    with pytest.raises(BinanceClientError, match="serverTime"):
        make(http).get_server_time()
    assert len(http.calls) == 1


@pytest.mark.requirement("RETRY-01")
@pytest.mark.parametrize("status", [401, 404, 405, 422, 451, 501])
def test_other_statuses_are_not_retried_and_do_not_set_cooldown(status, tmp_path):
    path = tmp_path / "c.json"
    http = FakeHttpClient([FakeResponse(status_code=status)])
    with pytest.raises(BinanceClientError, match=str(status)):
        make(http, cooldown_path=path).get_server_time()
    assert len(http.calls) == 1 and not path.exists()


@pytest.mark.requirement("RETRY-01")
def test_unknown_transport_error_is_not_retried():
    http = SequenceFakeHttpClient([httpx.ReadError("reset")])
    with pytest.raises(BinanceClientError, match="ReadError"):
        make(http).get_server_time()
    assert len(http.calls) == 1


# ---- fallback ------------------------------------------------------------------
@pytest.mark.requirement("RETRY-02")
def test_connect_failures_never_leave_the_allowed_hosts():
    exc = httpx.ConnectError("dns")
    http = SequenceFakeHttpClient([exc, exc, exc, exc])
    with pytest.raises(BinanceClientError, match="connect"):
        make(http).get_server_time()
    assert [u.split("/")[2] for u, _ in http.calls] == ["data-api.binance.vision", "api.binance.com", "api.binance.com", "api.binance.com"]


@pytest.mark.requirement("RETRY-02")
def test_fallback_happens_once_per_fetch_and_begin_fetch_resets_it():
    exc = httpx.ConnectError("dns")
    http = SequenceFakeHttpClient([exc, FakeResponse(payload=OK), exc, FakeResponse(payload=OK)])
    client = make(http)
    assert client.get_server_time() == NOW
    client.begin_fetch()
    assert client.get_server_time() == NOW
    assert [u.split("/")[2] for u, _ in http.calls] == ["data-api.binance.vision", "api.binance.com"] * 2


@pytest.mark.requirement("RETRY-02")
@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_errors_never_trigger_fallback(status):
    http = FakeHttpClient([FakeResponse(status_code=status) for _ in range(4)])
    with pytest.raises(BinanceClientError):
        make(http).get_server_time()
    assert {u.split("/")[2] for u, _ in http.calls} == {"data-api.binance.vision"}


# ---- backoff, jitter, budget ------------------------------------------------------
@pytest.mark.requirement("RETRY-04")
@pytest.mark.parametrize("bad", [-0.1, 1.01, True])
def test_out_of_range_jitter_is_a_programming_error(bad):
    http = FakeHttpClient([FakeResponse(status_code=500) for _ in range(4)])
    with pytest.raises(ValueError, match="jitter"):
        make(http, jitter=lambda: bad).get_server_time()


@pytest.mark.requirement("RETRY-04")
@pytest.mark.parametrize("jitter", [0.0, 1.0])
def test_jitter_bounds_are_inclusive(jitter):
    sleeps = []
    http = FakeHttpClient([FakeResponse(status_code=500) for _ in range(4)])
    with pytest.raises(BinanceClientError):
        make(http, sleep=sleeps.append, jitter=lambda: jitter).get_server_time()
    assert sleeps == [1 + jitter, 2 + jitter, 3 + jitter]


@pytest.mark.requirement("RETRY-05")
def test_sleep_budget_is_cumulative_across_requests_until_begin_fetch():
    sleeps = []
    def failing():
        return FakeHttpClient([FakeResponse(status_code=500) for _ in range(4)])
    http = failing()
    client = make(http, sleep=sleeps.append)
    for _ in range(5):                      # 5 x (1+2+3) = 30s, exactly the budget
        with pytest.raises(BinanceClientError, match="failed after 4"):
            client.get_server_time()
        client.http_client = http = failing()
    with pytest.raises(BinanceClientError, match="budget"):
        client.get_server_time()
    assert len(http.calls) == 1 and sum(sleeps) == 30
    client.begin_fetch()
    client.http_client = FakeHttpClient([FakeResponse(payload=OK)])
    assert client.get_server_time() == NOW


@pytest.mark.requirement("RETRY-05")
@pytest.mark.parametrize("header", ["Retry-After", "retry-after", "RETRY-AFTER"])
def test_retry_after_header_is_case_insensitive(header):
    sleeps = []
    http = FakeHttpClient([FakeResponse(status_code=429, headers={header: "7"}), FakeResponse(payload=OK)])
    assert make(http, sleep=sleeps.append, jitter=lambda: 0.9).get_server_time() == NOW
    assert sleeps == [7]


@pytest.mark.requirement("RETRY-05")
@pytest.mark.parametrize("value", ["abc", "-5", "1.5", "", "Wed, 21 Oct 2026 07:28:00 GMT"])
def test_unparsable_retry_after_is_treated_as_absent(value):
    sleeps = []
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": value}), FakeResponse(payload=OK)])
    assert make(http, sleep=sleeps.append).get_server_time() == NOW
    assert sleeps == [1]


@pytest.mark.requirement("RETRY-05")
def test_retry_after_zero_retries_immediately():
    sleeps = []
    http = FakeHttpClient([FakeResponse(status_code=429, headers={"Retry-After": "0"}), FakeResponse(payload=OK)])
    assert make(http, sleep=sleeps.append).get_server_time() == NOW
    assert sleeps == [0]


# ---- cooldown integration ------------------------------------------------------------
@pytest.mark.requirement("COOLDOWN-02")
@pytest.mark.parametrize("responses,expected_s,reason", [
    ([FakeResponse(status_code=418)], 600, "418"),
    ([FakeResponse(status_code=418, headers={"Retry-After": "900"})], 900, "418"),
    ([FakeResponse(status_code=418, headers={"Retry-After": "5"})], 600, "418"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "10"})] * 4, 300, "429_exhausted"),
    ([FakeResponse(status_code=429)] * 4, 300, "429_exhausted"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "11"})] * 3, 600, "429_retry_after_exceeds_sleep_budget"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "45"})], 600, "429_retry_after_exceeds_sleep_budget"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "60"})], 600, "429_retry_after_exceeds_sleep_budget"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "61"})], 600, "429_retry_after_over_60"),
    ([FakeResponse(status_code=429, headers={"Retry-After": "700"})], 700, "429_retry_after_over_60"),
], ids=["418", "418-RA900", "418-RA5", "429-RA10-exhausted", "429-no-RA-exhausted", "RA11-budget", "RA45-budget", "RA60-boundary", "RA61-cap", "RA700-cap"])
def test_cooldown_is_persisted_with_frozen_durations(tmp_path, responses, expected_s, reason):
    path = tmp_path / "data" / "binance_cooldown.json"
    with pytest.raises(BinanceClientError, match="cooldown"):
        make(FakeHttpClient(list(responses)), cooldown_path=path).get_server_time()
    assert json.loads(path.read_text()) == {"until_ms": NOW + expected_s * 1000, "reason": reason}


@pytest.mark.requirement("COOLDOWN-02")
@pytest.mark.parametrize("status", [400, 403, 500, 502, 503, 504])
def test_non_rate_limit_errors_never_persist_cooldown(tmp_path, status):
    path = tmp_path / "c.json"
    with pytest.raises(BinanceClientError):
        make(FakeHttpClient([FakeResponse(status_code=status) for _ in range(4)]), cooldown_path=path).get_server_time()
    assert not path.exists()


@pytest.mark.requirement("COOLDOWN-01")
def test_cooldown_blocks_later_calls_in_memory_without_a_file():
    http = FakeHttpClient([FakeResponse(status_code=418)])
    client = make(http)
    with pytest.raises(BinanceClientError, match="418"):
        client.get_server_time()
    with pytest.raises(BinanceClientError, match="cooldown active"):
        client.get_server_time()
    assert len(http.calls) == 1


@pytest.mark.requirement("COOLDOWN-01")
def test_cooldown_is_global_across_clients_sharing_the_file(tmp_path):
    path = tmp_path / "c.json"
    with pytest.raises(BinanceClientError):
        make(FakeHttpClient([FakeResponse(status_code=418)]), cooldown_path=path).get_server_time()
    other_http = FakeHttpClient([FakeResponse(payload=OK)])
    with pytest.raises(BinanceClientError, match="cooldown active"):
        make(other_http, cooldown_path=path).get_server_time()
    assert other_http.calls == []


@pytest.mark.requirement("COOLDOWN-01")
def test_expired_cooldown_allows_requests_and_boundary_is_exclusive(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"until_ms": NOW, "reason": "418"}))
    assert make(FakeHttpClient([FakeResponse(payload=OK)]), cooldown_path=path).get_server_time() == NOW
    path.write_text(json.dumps({"until_ms": NOW + 1, "reason": "418"}))
    http = FakeHttpClient([FakeResponse(payload=OK)])
    with pytest.raises(BinanceClientError, match="cooldown active"):
        make(http, cooldown_path=path).get_server_time()
    assert http.calls == []


@pytest.mark.requirement("COOLDOWN-05")
@pytest.mark.parametrize("contents", ["not-json", "{}", '{"until_ms": -1, "reason": "x"}', '{"until_ms": "9", "reason": "x"}', ""])
def test_corrupt_cooldown_file_fails_closed_before_any_network_call(tmp_path, contents):
    path = tmp_path / "c.json"
    path.write_text(contents)
    http = FakeHttpClient([FakeResponse(payload=OK)])
    with pytest.raises(BinanceClientError, match="failing closed"):
        make(http, cooldown_path=path).get_server_time()
    assert http.calls == []


@pytest.mark.requirement("COOLDOWN-03")
def test_a_new_cooldown_never_shortens_a_longer_existing_one(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"until_ms": NOW - 1, "reason": "old"}))   # expired, so the call proceeds
    client = make(FakeHttpClient([FakeResponse(status_code=418)]), cooldown_path=path)
    client._cooldown_until_ms = 0
    with pytest.raises(BinanceClientError):
        client.get_server_time()
    assert json.loads(path.read_text())["until_ms"] == NOW + 600_000


@pytest.mark.requirement("COOLDOWN-03")
def test_cooldown_persistence_failure_does_not_mask_the_original_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    client = make(FakeHttpClient([FakeResponse(status_code=418)]), cooldown_path=blocker / "c.json")
    with pytest.raises(BinanceClientError, match="418.*could not be persisted"):
        client.get_server_time()
    with pytest.raises(BinanceClientError, match="cooldown active"):
        client.get_server_time()


@pytest.mark.requirement("FINAL-01")
def test_huge_retry_after_integer_does_not_overflow():
    from trading_app.data.cooldown import cooldown_duration_s
    assert cooldown_duration_s("418", 10**400) == 10**400


@pytest.mark.requirement("PATH-01")
@pytest.mark.parametrize("url", [
    "https://data-api.binance.vision/api/v3/time", "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/time", "https://API.binance.com/api/v3/klines",
])
def test_exact_allowed_full_urls_return_true(url):
    assert validate_public_url(url) is True


@pytest.mark.requirement("PATH-01")
@pytest.mark.parametrize("url", [
    "https://data-api.binance.vision", "https://data-api.binance.vision/", "https://data-api.binance.vision/api/v3/time/",
    "https://data-api.binance.vision/api/v3/TIME", "https://data-api.binance.vision//api/v3/time", "https://data-api.binance.vision/api/v3/order",
    "https://data-api.binance.vision/api/v3/time;x", "https://data-api.binance.vision/api/v3/time#f", "https://data-api.binance.vision/api/v3/time?x=1",
    "https://data-api.binance.vision/api/v3/%74ime", "https://data-api.binance.vision/api/v3/klines/%2e%2e/order",
    "https://testnet.binance.vision/api/v3/time", "http://data-api.binance.vision/api/v3/time", "https://data-api.binance.vision:443/api/v3/time",
    "https://a@data-api.binance.vision/api/v3/time", "https://api1.binance.com/api/v3/time", "https://data-api.binance.vision.evil.example/api/v3/time",
])
def test_non_exact_full_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


@pytest.mark.requirement("PATH-01")
def test_every_request_url_is_validated_before_sending():
    http = FakeHttpClient([FakeResponse(payload=OK)])
    make(http).get_server_time()
    assert all(validate_public_url(u) for u, _ in http.calls)
