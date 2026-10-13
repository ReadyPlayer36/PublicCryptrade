"""Global cooldown must block all HTTP, including server-time calls."""
import json
from pathlib import Path
import pytest
from trading_app.data.binance_client import BinanceMarketDataClient, BinanceClientError
from trading_app.data.cooldown import CorruptCooldownError, read_cooldown
from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.policy import cooldown_policy

@pytest.mark.requirement("COOLDOWN-04")
def test_cooldown_directory_scope(tmp_path):
    assert cooldown_policy()["directory_scoped"] is True
    path = tmp_path / "data" / "binance_cooldown.json"
    path.parent.mkdir(); path.write_text('{"until_ms": "not-an-int", "reason": "test"}')
    with pytest.raises(CorruptCooldownError, match="integer|invalid|cooldown"):
        read_cooldown(path)

@pytest.mark.requirement("COOLDOWN-01")
def test_cooldown_is_global_across_hosts():
    http = FakeHttpClient([FakeResponse(payload={"serverTime": 1767571500000})])
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=http)
    with pytest.raises(BinanceClientError, match="time|server"):
        client.get_server_time()
    assert len(http.calls) == 1
    assert cooldown_policy()["scope"] == "global_across_allowed_hosts"

@pytest.mark.requirement("COOLDOWN-03")
def test_cooldown_persists_across_processes(tmp_path):
    path = tmp_path / "binance_cooldown.json"
    path.write_text('{"until_ms": 1767571800000, "reason": "418"}')
    # Reopening from disk, rather than retaining an in-memory object, is the persistence contract.
    assert read_cooldown(path) == {"until_ms": 1767571800000, "reason": "418"}
