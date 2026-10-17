"""The autouse network guard in tests/conftest.py: tests can never reach a real network."""
import socket

import pytest


@pytest.mark.requirement("HYGIENE-03")
def test_remote_connect_is_blocked_before_any_packet_is_sent():
    for target in (("54.199.166.168", 443), ("example.com", 443), ("data-api.binance.vision", 443)):
        with pytest.raises(RuntimeError, match="real network access is forbidden"):
            socket.create_connection(target, timeout=1)
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="forbidden"):
            raw.connect(("8.8.8.8", 53))
        with pytest.raises(RuntimeError, match="forbidden"):
            raw.connect_ex(("8.8.8.8", 53))
    finally:
        raw.close()


@pytest.mark.requirement("HYGIENE-03")
def test_dns_lookup_of_remote_names_is_blocked():
    with pytest.raises(RuntimeError, match="DNS lookup"):
        socket.getaddrinfo("data-api.binance.vision", 443)


@pytest.mark.requirement("HYGIENE-03")
def test_loopback_and_unix_sockets_still_work():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname(), timeout=2)
    try:
        conn, peer = server.accept()
        assert client.getpeername() == server.getsockname()      # a real loopback connection was made
        assert peer[0] == "127.0.0.1"
        conn.close()
    finally:
        client.close()
        server.close()


@pytest.mark.requirement("HYGIENE-03")
def test_default_http_client_cannot_reach_binance_from_tests():
    from datetime import datetime, timezone
    from trading_app.data.binance_client import BinanceMarketDataClient
    client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", finality_lag_ms=0, sleep=lambda _: None)
    try:
        with pytest.raises(RuntimeError, match="real network access is forbidden"):
            client.get_historical_klines(symbol="BTCUSDT", timeframe="5m",
                                         start=datetime(2024, 1, 1, tzinfo=timezone.utc), end=datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc))
    finally:
        client.close()
