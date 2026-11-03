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
    with pytest.raises(RuntimeError, match="DNS getaddrinfo"):
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


@pytest.mark.requirement("HYGIENE-03")
def test_udp_datagram_sends_to_remote_addresses_are_blocked():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(RuntimeError, match="sendto"):
            udp.sendto(b"x", ("8.8.8.8", 53))
        with pytest.raises(RuntimeError, match="sendto"):
            udp.sendto(b"x", 0, ("8.8.8.8", 53))                      # flags form
        with pytest.raises(RuntimeError, match="sendto"):
            udp.sendto(b"x", ("example.com", 53))
        with pytest.raises(RuntimeError, match="sendmsg"):
            udp.sendmsg([b"x"], [], 0, ("8.8.8.8", 53))
        with pytest.raises(RuntimeError, match="forbidden"):
            udp.connect(("8.8.8.8", 53))                              # connected-UDP route
    finally:
        udp.close()


@pytest.mark.requirement("HYGIENE-03")
def test_every_dns_resolution_path_is_blocked_for_remote_names():
    with pytest.raises(RuntimeError, match="DNS gethostbyname of"):
        socket.gethostbyname("data-api.binance.vision")
    with pytest.raises(RuntimeError, match="DNS gethostbyname_ex of"):
        socket.gethostbyname_ex("data-api.binance.vision")
    with pytest.raises(RuntimeError, match="DNS gethostbyaddr of"):
        socket.gethostbyaddr("8.8.8.8")
    with pytest.raises(RuntimeError, match="DNS getnameinfo of"):
        socket.getnameinfo(("8.8.8.8", 53), 0)


@pytest.mark.requirement("HYGIENE-03")
def test_empty_and_look_alike_hostnames_are_not_treated_as_loopback():
    for host in ("", "0.0.0.0", "localhost.evil.example", "127.0.0.1.evil.example", "LOCALHOST.evil.example"):
        with pytest.raises(RuntimeError, match="forbidden"):
            socket.getaddrinfo(host, 80)
        with pytest.raises(RuntimeError, match="forbidden"):
            socket.gethostbyname(host)
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="forbidden"):
            raw.connect(("", 80))
    finally:
        raw.close()


@pytest.mark.requirement("HYGIENE-03")
def test_loopback_udp_and_name_resolution_still_work():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(b"ping", receiver.getsockname())
        data, _ = receiver.recvfrom(16)
        assert data == b"ping"
        sender.sendto(b"flag", 0, receiver.getsockname())             # (data, flags, address) form to loopback must pass
        assert receiver.recvfrom(16)[0] == b"flag"
        sender.sendmsg([b"pong"], [], 0, receiver.getsockname())
        assert receiver.recvfrom(16)[0] == b"pong"
        assert socket.gethostbyname("localhost") in ("127.0.0.1", "::1")
        assert socket.getaddrinfo("127.0.0.1", 80)
        assert socket.getaddrinfo("LOCALHOST", 80)
        assert socket.getaddrinfo(None, 80)                           # passive/wildcard lookups carry no remote host
    finally:
        sender.close()
        receiver.close()


@pytest.mark.requirement("HYGIENE-03")
def test_sendmsg_keyword_address_and_addressless_sends_cannot_bypass_the_guard():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(RuntimeError, match="sendmsg"):
            udp.sendmsg([b"x"], address=("8.8.8.8", 53))              # keyword form is checked by the guard itself
        with pytest.raises(RuntimeError, match="forbidden"):
            udp.connect(("8.8.8.8", 53))                              # so a socket can never be connected to a remote peer
        with pytest.raises(OSError):
            udp.sendmsg([b"x"])                                       # address-less send on a never-connected socket: no packet
        with pytest.raises(OSError):
            udp.send(b"x")
    finally:
        udp.close()


@pytest.mark.requirement("HYGIENE-03")
def test_addressless_sends_on_a_loopback_connected_udp_socket_still_work():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.connect(receiver.getsockname())
        sender.sendmsg([b"a"])
        assert receiver.recvfrom(8)[0] == b"a"
        sender.send(b"b")
        assert receiver.recvfrom(8)[0] == b"b"
        with pytest.raises(TypeError):                                # CPython's sendmsg takes no keyword arguments at all
            sender.sendmsg([b"x"], address=receiver.getsockname())
    finally:
        sender.close()
        receiver.close()
