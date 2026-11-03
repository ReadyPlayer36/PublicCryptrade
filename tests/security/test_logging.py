"""Logs and errors never contain URLs, headers, keys, tokens or secret-like values."""
import logging
import re

import httpx
import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse, SequenceFakeHttpClient
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient

POISON = "https://user:hunter2@evil.example/api/v3/time?apiKey=SECRETKEY&signature=SIGVALUE"
FORBIDDEN = re.compile(r"https?://|hunter2|SECRETKEY|SIGVALUE|Bearer|Authorization|X-MBX|apikey|signature|secret|token|userinfo", re.I)


def make(http, **kw):
    return BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, sleep=lambda _: None,
                                   jitter=lambda: 0.0, now_ms=lambda: 1767571500000, **kw)


def everything_logged(caplog):
    return "\n".join(r.getMessage() + " " + str(r.args) for r in caplog.records)


@pytest.mark.requirement("LOG-02")
def test_http_error_logging_excludes_raise_for_status_url_userinfo_and_secrets(caplog, tmp_path):
    class PoisonedResponse(FakeResponse):
        headers = {"Retry-After": "5", "Authorization": "Bearer TOPSECRETTOKEN", "X-MBX-APIKEY": "SECRETKEY"}
        def raise_for_status(self):
            raise httpx.HTTPStatusError(f"Client error for url {POISON}", request=None, response=None)

    caplog.set_level(logging.DEBUG)
    responses = [PoisonedResponse(status_code=503) for _ in range(4)]
    with pytest.raises(BinanceClientError) as failed:
        make(FakeHttpClient(responses)).get_server_time()
    teapot = PoisonedResponse(status_code=418)
    with pytest.raises(BinanceClientError) as banned:
        make(FakeHttpClient([teapot]), cooldown_path=tmp_path / "c.json").get_server_time()
    for text in (everything_logged(caplog), str(failed.value), str(banned.value)):
        assert not FORBIDDEN.search(text), text
    assert caplog.records, "expected retry/cooldown log records"


@pytest.mark.requirement("LOG-01")
def test_logs_exclude_urls_headers_keys_tokens_and_secrets(caplog):
    caplog.set_level(logging.DEBUG)
    for exc in (httpx.ConnectError(POISON), httpx.ReadTimeout(POISON), httpx.ReadError(POISON), TimeoutError(POISON)):
        http = SequenceFakeHttpClient([exc] * 4)
        with pytest.raises(BinanceClientError) as err:
            make(http).get_server_time()
        assert not FORBIDDEN.search(str(err.value)), str(err.value)
        assert err.value.__cause__ is None and err.value.__context__ is None
    assert not FORBIDDEN.search(everything_logged(caplog)), everything_logged(caplog)
    for record in caplog.records:
        assert record.exc_info is None and not FORBIDDEN.search(record.getMessage())


@pytest.mark.requirement("LOG-01")
def test_unretried_transport_error_leaves_no_cause_or_context():
    http = SequenceFakeHttpClient([httpx.ReadError(POISON)])
    with pytest.raises(BinanceClientError) as err:
        make(http).get_server_time()
    assert err.value.__cause__ is None and err.value.__context__ is None


@pytest.mark.requirement("LOG-02")
@pytest.mark.parametrize("status", [400, 403, 429, 500, 503])
def test_injected_http_status_error_from_the_http_client_never_leaks(caplog, status):
    request = httpx.Request("GET", "https://data-api.binance.vision/api/v3/time")
    error = httpx.HTTPStatusError(f"Server error '{status}' for url '{POISON}'", request=request, response=httpx.Response(status, request=request))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(BinanceClientError) as failed:
        make(SequenceFakeHttpClient([error])).get_server_time()
    assert not FORBIDDEN.search(str(failed.value)), str(failed.value)
    assert failed.value.__cause__ is None and failed.value.__context__ is None
    assert not FORBIDDEN.search(everything_logged(caplog))
    assert all(r.exc_info is None for r in caplog.records)


@pytest.mark.requirement("LOG-02")
def test_cooldown_persistence_failure_text_is_not_exposed(caplog, monkeypatch, tmp_path):
    from trading_app.data import binance_client as bc

    def explode(*args, **kwargs):
        raise OSError(POISON)

    monkeypatch.setattr(bc, "extend_cooldown", explode)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(BinanceClientError) as failed:
        make(FakeHttpClient([FakeResponse(status_code=418)]), cooldown_path=tmp_path / "c.json").get_server_time()
    assert "could not be persisted (OSError)" in str(failed.value)
    assert not FORBIDDEN.search(str(failed.value)) and failed.value.__cause__ is None and failed.value.__context__ is None
    assert not FORBIDDEN.search(everything_logged(caplog))


@pytest.mark.requirement("LOG-02")
def test_corrupt_cooldown_file_error_carries_no_file_content(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"until_ms": "SECRETKEY", "reason": "hunter2"')
    with pytest.raises(BinanceClientError) as failed:
        make(FakeHttpClient([]), cooldown_path=path).get_server_time()
    assert not FORBIDDEN.search(str(failed.value)) and failed.value.__cause__ is None and failed.value.__context__ is None
