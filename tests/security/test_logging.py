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
