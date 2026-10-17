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


_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Tests must never reach a real network: any non-loopback connect or DNS lookup fails loudly."""
    real_connect, real_connect_ex, real_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def _host(address):
        return address[0] if isinstance(address, tuple) and address else address

    def guarded_connect(self, address, *args, **kwargs):
        if self.family != socket.AF_UNIX and _host(address) not in _LOOPBACK:
            raise RuntimeError(f"real network access is forbidden in tests: connect to {_host(address)!r}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if self.family != socket.AF_UNIX and _host(address) not in _LOOPBACK:
            raise RuntimeError(f"real network access is forbidden in tests: connect_ex to {_host(address)!r}")
        return real_connect_ex(self, address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in _LOOPBACK:
            raise RuntimeError(f"real network access is forbidden in tests: DNS lookup of {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
