"""Stage C: klines download, finality, pagination and input validation (fakes only)."""
from datetime import datetime, timedelta, timezone

import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_row, make_rows
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient
from trading_app.data.finality import EmptyEffectiveRangeError, NaiveDatetimeError, NonFinalCandleError
from trading_app.data.validator import DataValidationError

I = 300_000
S0 = 1767571200000
UTC = timezone.utc


def dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def client_for(responses, lag=0, **kw):
    http = FakeHttpClient(list(responses))
    kw.setdefault("sleep", lambda _: None)
    kw.setdefault("jitter", lambda: 0.0)
    return BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, finality_lag_ms=lag, **kw), http


def fetch(client, n=3, start=S0):
    return client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=dt(start), end=dt(start + n * I))


def time_resp(ms):
    return FakeResponse(payload={"serverTime": ms})


@pytest.mark.requirement("M1-05")
def test_request_params_are_exact_and_carry_no_credentials():
    client, http = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=make_rows(S0, 3))])
    fetch(client)
    url, params = http.calls[1]
    assert url == "https://data-api.binance.vision/api/v3/klines"
    assert params == {"symbol": "BTCUSDT", "interval": "5m", "startTime": S0, "endTime": S0 + 3 * I - 1, "limit": 1000}


@pytest.mark.requirement("M1-05")
def test_rows_are_returned_in_order_and_unmodified():
    rows = make_rows(S0, 3)
    client, _ = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=[list(r) for r in rows])])
    assert fetch(client) == rows


@pytest.mark.requirement("FINAL-07")
@pytest.mark.parametrize("kwargs", [
    dict(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2, tzinfo=UTC)),
    dict(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 2)),
])
def test_naive_datetimes_rejected_before_any_network_call(kwargs):
    client, http = client_for([time_resp(S0)])
    with pytest.raises(NaiveDatetimeError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", **kwargs)
    assert http.calls == []


@pytest.mark.requirement("FINAL-07")
@pytest.mark.parametrize("start,end,match", [
    (S0 + 1, S0 + 3 * I, "start is not aligned"), (S0, S0 + 3 * I + 1, "end is not aligned"),
    (S0 + I, S0 + I, "after start"), (S0 + 2 * I, S0 + I, "after start"),
])
def test_unaligned_or_reversed_ranges_rejected_before_any_network_call(start, end, match):
    client, http = client_for([time_resp(S0)])
    with pytest.raises(ValueError, match=match):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=dt(start), end=dt(end))
    assert http.calls == []


@pytest.mark.requirement("FINAL-07")
@pytest.mark.parametrize("symbol,timeframe", [("", "5m"), ("btcusdt", "5m"), ("BTC/USDT", "5m"), ("BTCUSDT&x=1", "5m"), ("BTCUSDT", "2m"), ("BTCUSDT", "")])
def test_invalid_symbol_or_timeframe_rejected_before_any_network_call(symbol, timeframe):
    client, http = client_for([time_resp(S0)])
    with pytest.raises(ValueError):
        client.get_historical_klines(symbol=symbol, timeframe=timeframe, start=dt(S0), end=dt(S0 + I))
    assert http.calls == []


@pytest.mark.requirement("LAG-01")
@pytest.mark.parametrize("bad", [-1, True, 1.5, "0"])
def test_invalid_configured_lag_is_rejected_at_construction(bad):
    with pytest.raises(ValueError, match="finality_lag_ms"):
        BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=FakeHttpClient([]), finality_lag_ms=bad)


@pytest.mark.requirement("FINAL-06")
def test_nonfinal_rows_abort_instead_of_being_dropped():
    S = S0 + 3 * I - 1                     # last candle closes at S0+3I-1 == S -> not < B
    client, http = client_for([time_resp(S + 2 * I), FakeResponse(payload=make_rows(S0, 3))], lag=2 * I + 1)
    with pytest.raises(NonFinalCandleError, match="non-final"):
        fetch(client)


@pytest.mark.requirement("FINAL-06")
def test_nonfinal_check_runs_before_structural_validation_and_across_pages():
    pages = [make_rows(S0, 1000), make_rows(S0 + 1000 * I, 2)]
    server = S0 + 1001 * I          # second-page candle 1001 closes at S0+1002I-1 >= B
    client, _ = client_for([time_resp(server)] + [FakeResponse(payload=p) for p in pages])
    with pytest.raises(NonFinalCandleError):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 1002 * I))


@pytest.mark.requirement("FINAL-02")
def test_final_candles_exactly_at_the_boundary_are_accepted():
    client, _ = client_for([time_resp(S0 + 3 * I), FakeResponse(payload=make_rows(S0, 3))])
    assert len(fetch(client)) == 3        # last close = S0+3I-1 < B = S0+3I


@pytest.mark.requirement("LAG-01")
def test_positive_lag_shrinks_the_effective_end():
    client, http = client_for([time_resp(S0 + 3 * I + 5), FakeResponse(payload=make_rows(S0, 2))], lag=I)
    assert len(fetch(client)) == 2
    assert http.calls[1][1]["endTime"] == S0 + 2 * I - 1


@pytest.mark.requirement("FINAL-07")
def test_empty_effective_range_is_an_explicit_error_with_no_kline_request():
    client, http = client_for([time_resp(S0 + I - 1)])
    with pytest.raises(EmptyEffectiveRangeError, match="effective"):
        fetch(client)
    assert len(http.calls) == 1


@pytest.mark.requirement("LAG-01")
def test_missing_lag_fails_after_snapshot_without_any_kline_request():
    http = FakeHttpClient([time_resp(S0 + 10 * I)])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match="finality lag"):
        fetch(client)
    assert len(http.calls) == 1


@pytest.mark.requirement("M1-05")
def test_time_snapshot_is_taken_once_per_fetch_even_with_many_pages():
    pages = [make_rows(S0, 1000), make_rows(S0 + 1000 * I, 1000), make_rows(S0 + 2000 * I, 5)]
    client, http = client_for([time_resp(S0 + 5000 * I)] + [FakeResponse(payload=p) for p in pages])
    rows = client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 2005 * I))
    assert len(rows) == 2005
    assert [u.rsplit("/", 1)[1] for u, _ in http.calls] == ["time", "klines", "klines", "klines"]


@pytest.mark.requirement("M1-05")
@pytest.mark.parametrize("name,rows", [
    ("gap", [make_row(S0), make_row(S0 + 2 * I)]),
    ("duplicate", [make_row(S0), make_row(S0)]),
    ("wrong-start", [make_row(S0 + I), make_row(S0 + 2 * I)]),
    ("bad-ohlc", [make_row(S0), [S0 + I, "100", "90", "99", "100", "1", S0 + 2 * I - 1, "1", 1, "0", "0", "0"]]),
    ("short-row", [make_row(S0), [S0 + I]]),
    ("misaligned", [make_row(S0 + 7), make_row(S0 + 7 + I)]),
])
def test_suspicious_pages_abort_the_fetch(name, rows):
    client, _ = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=rows)])
    with pytest.raises(DataValidationError):
        fetch(client, n=2)


@pytest.mark.requirement("M1-05")
def test_page_that_ends_early_followed_by_empty_page_is_rejected_as_incomplete():
    client, _ = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=make_rows(S0, 2)), FakeResponse(payload=[])])
    with pytest.raises(DataValidationError, match="UNEXPECTED_END"):
        fetch(client, n=4)


@pytest.mark.requirement("M1-05")
def test_candle_beyond_requested_end_is_rejected():
    client, _ = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=make_rows(S0, 4))])
    with pytest.raises(DataValidationError, match="outside requested range"):
        fetch(client, n=3)


@pytest.mark.requirement("M1-05")
@pytest.mark.parametrize("payload", [{"a": 1}, "x", None, [1, 2], [[S0]] * 1001])
def test_wrong_shape_kline_pages_abort_without_retry(payload):
    client, http = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=payload)])
    with pytest.raises((BinanceClientError, DataValidationError)):
        fetch(client)
    assert len(http.calls) == 2


@pytest.mark.requirement("M1-05")
def test_empty_first_page_returns_an_empty_list():
    client, _ = client_for([time_resp(S0 + 10 * I), FakeResponse(payload=[])])
    assert fetch(client) == []


@pytest.mark.requirement("COOLDOWN-01")
def test_cooldown_during_pagination_stops_further_page_requests(tmp_path):
    path = tmp_path / "c.json"
    pages = [FakeResponse(payload=make_rows(S0, 1000)), FakeResponse(payload=make_rows(S0 + 1000 * I, 5))]
    client, http = client_for([time_resp(S0 + 5000 * I)] + pages, cooldown_path=path, now_ms=lambda: S0)
    original_get = http.get

    def trip_after_first_page(url, *, params=None):
        out = original_get(url, params=params)
        if url.endswith("/klines"):
            from trading_app.data.cooldown import write_cooldown
            write_cooldown(path, {"until_ms": S0 + 600_000, "reason": "418"})
        return out

    http.get = trip_after_first_page
    with pytest.raises(BinanceClientError, match="cooldown active"):
        client.get_historical_klines(symbol="BTCUSDT", timeframe="5m", start=dt(S0), end=dt(S0 + 1005 * I))
    assert [u.rsplit("/", 1)[1] for u, _ in http.calls] == ["time", "klines"]
