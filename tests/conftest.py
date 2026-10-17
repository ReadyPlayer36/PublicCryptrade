import socket

import pytest

# Export every frozen-matrix requirement marker into JUnit testcase properties.
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    for marker in item.iter_markers(name="requirement"):
        if marker.args:
            report.user_properties.append(("requirement", str(marker.args[0])))


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}      # the empty hostname is NOT allowed


def _norm(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return host.lower() if isinstance(host, str) else host


def _is_remote(host) -> bool:
    return _norm(host) not in _LOOPBACK


def _address_host(address):
    return address[0] if isinstance(address, tuple) and address else address


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Tests must never reach a real network: any non-loopback connect, datagram send or DNS lookup fails loudly."""
    S = socket.socket
    real = {name: getattr(S, name) for name in ("connect", "connect_ex", "sendto", "sendmsg")}
    real_dns = {name: getattr(socket, name) for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")}

    def forbid(what, host):
        raise RuntimeError(f"real network access is forbidden in tests: {what} {host!r}")

    def make_socket_guard(key, label, address_of):
        def guarded(self, *args, **kwargs):
            address = address_of(args, kwargs)
            if self.family != socket.AF_UNIX and _is_remote(_address_host(address)):
                forbid(label, _address_host(address))
            return real[key](self, *args, **kwargs)
        return guarded

    last_arg = lambda args, kwargs: kwargs.get("address", args[-1] if args else None)      # sendto(data, [flags,] address)
    first_arg = lambda args, kwargs: args[0] if args else kwargs.get("address")            # connect(address)
    sendmsg_addr = lambda args, kwargs: kwargs.get("address", args[3] if len(args) > 3 else None)  # sendmsg(buffers, ancdata, flags, address)

    def guarded_sendmsg(self, *args, **kwargs):
        address = sendmsg_addr(args, kwargs)
        if address is not None and self.family != socket.AF_UNIX and _is_remote(_address_host(address)):
            forbid("sendmsg to", _address_host(address))
        return real["sendmsg"](self, *args, **kwargs)

    def dns_guard(name, host_of):
        def guarded(*args, **kwargs):
            host = host_of(args, kwargs)
            if host is not None and _is_remote(host):
                forbid(f"DNS {name} of", host)
            return real_dns[name](*args, **kwargs)
        return guarded

    host_first = lambda args, kwargs: args[0] if args else kwargs.get("host", kwargs.get("hostname", kwargs.get("ip_address")))
    nameinfo_host = lambda args, kwargs: _address_host(args[0] if args else kwargs.get("sockaddr"))

    monkeypatch.setattr(S, "connect", make_socket_guard("connect", "connect to", first_arg))
    monkeypatch.setattr(S, "connect_ex", make_socket_guard("connect_ex", "connect_ex to", first_arg))
    monkeypatch.setattr(S, "sendto", make_socket_guard("sendto", "sendto", last_arg))
    monkeypatch.setattr(S, "sendmsg", guarded_sendmsg)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        monkeypatch.setattr(socket, name, dns_guard(name, host_first))
    monkeypatch.setattr(socket, "getnameinfo", dns_guard("getnameinfo", nameinfo_host))
