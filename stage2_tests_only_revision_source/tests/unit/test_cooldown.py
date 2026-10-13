"""Cooldown persistence and policy contract tests; no real network is used."""
import json
from pathlib import Path
import pytest
from tests.fixtures.policy import cooldown_policy
from trading_app.data.cooldown import read_cooldown, write_cooldown, CorruptCooldownError
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from tests.fixtures.fakes import FakeHttpClient, FakeResponse

@pytest.mark.requirement("COOLDOWN-03")
def test_cooldown_atomic_persistence(tmp_path):
    path = tmp_path / "binance_cooldown.json"
    payload = {"until_ms": 1767571800000, "reason": "429_exhausted"}
    write_cooldown(path, payload)
    assert json.loads(path.read_text()) == payload
    assert list(tmp_path.glob("*.tmp")) == []

@pytest.mark.requirement("COOLDOWN-02")
def test_cooldown_trigger_minimums_and_retry_after():
    durations = cooldown_policy()["durations"]
    assert durations["418"] == "max(supplied_retry_after,600)"
    assert durations["429_exhausted"] == "max(supplied_retry_after,300)"
    assert durations["429_retry_after_over_60"] == "max(supplied_retry_after,600)"
    http = FakeHttpClient([FakeResponse(status_code=418, headers={"Retry-After": "900"})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match="418|cooldown|rate"):
        client.get_server_time()
    assert len(http.calls) == 1

@pytest.mark.requirement("COOLDOWN-05")
def test_corrupt_cooldown_fails_closed(tmp_path):
    path = tmp_path / "cooldown.json"
    path.write_text('{"until_ms": -1, "reason": "bad"}')
    with pytest.raises(CorruptCooldownError, match="negative|invalid|cooldown"):
        read_cooldown(path)

@pytest.mark.requirement("COOLDOWN-05")
@pytest.mark.parametrize("contents", [None, "not-json", "{}", '{"until_ms": "x", "reason": "bad"}', '{"until_ms": -1, "reason": "bad"}'], ids=["missing", "corrupt-json", "missing-fields", "non-integer", "negative"])
def test_invalid_cooldown_state_fails_closed(tmp_path, contents):
    path = tmp_path / "cooldown.json"
    if contents is not None:
        path.write_text(contents)
    with pytest.raises(CorruptCooldownError, match="cooldown|invalid|missing|integer|negative|JSON"):
        read_cooldown(path)

@pytest.mark.requirement("COOLDOWN-01")
def test_active_cooldown_blocks_server_time_network_io(tmp_path):
    path = tmp_path / "binance_cooldown.json"
    path.write_text('{"until_ms": 1767571800000, "reason": "418"}')
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http, cooldown_path=path, now_ms=lambda: 1767571500000)
    with pytest.raises(BinanceClientError, match="cooldown|until"):
        client.get_server_time()
    assert http.calls == []
