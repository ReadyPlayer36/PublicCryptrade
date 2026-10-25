"""PACE-8 strict deadline (connection-closing watchdog) and the allow-listed transport; offline (mock and loopback only)."""
import http.client
import json
import socket
import socketserver
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler

import pytest

from tools.obs.pacer import Pacer
from tools.obs.clock import SystemClock
from tools.obs.params import AUDIT_MAX_DURATION_NS, CANCEL_GRACE_NS, CONNECT_TIMEOUT_S, DEADLINE_NS, HOST, MS, READ_TIMEOUT_S, S
from tools.obs.specs import UnsafeRequest, klines_request, time_request
from tools.obs.transport import CONNECT_ERROR, DEADLINE, MAX_BODY_BYTES, TIMEOUT, HttpTransport
from tools.obs.watchdog import CancellationFailed, run_with_deadline


# ---------------- watchdog ----------------
def test_a_request_that_finishes_before_the_deadline_is_not_cancelled():
    cancelled = []
    result = run_with_deadline(lambda: 42, lambda: cancelled.append(1), deadline_s=1.0)
    assert (result.timed_out, result.value, result.error, cancelled) == (False, 42, None, [])


def test_an_error_before_the_deadline_is_returned_not_raised():
    def boom():
        raise ValueError("x")
    result = run_with_deadline(boom, lambda: None, deadline_s=1.0)
    assert not result.timed_out and isinstance(result.error, ValueError)


def test_a_blocked_request_is_cancelled_at_the_deadline_and_its_error_is_swallowed():
    release = threading.Event()
    cancelled = []

    def blocked():
        release.wait(10)
        raise OSError("connection closed")                                   # what a closed connection does

    def cancel():
        cancelled.append(time.monotonic())
        release.set()

    t0 = time.monotonic()
    result = run_with_deadline(blocked, cancel, deadline_s=0.15, grace_s=1.0)
    elapsed = time.monotonic() - t0
    assert result.timed_out and result.error is None and len(cancelled) == 1
    assert 0.15 <= cancelled[0] - t0 < 0.5 and 0.15 <= elapsed < 1.0


def test_a_request_that_ignores_the_cancellation_is_an_incident():
    release = threading.Event()
    try:
        with pytest.raises(CancellationFailed):
            run_with_deadline(lambda: release.wait(5), lambda: None, deadline_s=0.05, grace_s=0.1)
    finally:
        release.set()


def test_protocol_constants():
    assert DEADLINE_NS == 17 * S and AUDIT_MAX_DURATION_NS == 18 * S and CANCEL_GRACE_NS == 1 * S
    assert (CONNECT_TIMEOUT_S, READ_TIMEOUT_S) == (5.0, 12.0) and DEADLINE_NS == (CONNECT_TIMEOUT_S + READ_TIMEOUT_S) * S
    assert HttpTransport().deadline_ns == DEADLINE_NS and HttpTransport().grace_ns == CANCEL_GRACE_NS


# ---------------- transport (fake connection) ----------------
class FakeSock:
    def __init__(self):
        self.timeout = None
        self.shut = False

    def settimeout(self, value):
        self.timeout = value

    def shutdown(self, how):
        self.shut = True


class FakeResponse:
    def __init__(self, status=200, body=b"{}", headers=()):
        self.status, self._body, self._headers = status, body, list(headers)

    def read(self, n=-1):
        return self._body[:n] if n >= 0 else self._body

    def getheaders(self):
        return self._headers


class FakeConnection:
    instances: list = []

    def __init__(self, scheme, host, port, timeout, *, response=None, error=None, connect_error=None):
        self.scheme, self.host, self.port, self.connect_timeout = scheme, host, port, timeout
        self.response, self.error, self.connect_error = response or FakeResponse(), error, connect_error
        self.sock = None
        self.requests = []
        self.closed = False
        FakeConnection.instances.append(self)

    def connect(self):
        if self.connect_error:
            raise self.connect_error
        self.sock = FakeSock()

    def request(self, method, url, headers):
        self.requests.append((method, url, headers))
        if self.error:
            raise self.error

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def fake_factory(**kw):
    FakeConnection.instances = []
    return lambda scheme, host, port, timeout: FakeConnection(scheme, host, port, timeout, **kw)


def test_requests_use_the_official_host_https_exact_path_and_parameters():
    headers = [("Date", "x"), ("Set-Cookie", "a=b"), ("X-MBX-USED-WEIGHT-1M", "3"), ("Retry-After", "2"), ("X-Other", "1")]
    transport = HttpTransport(connection_factory=fake_factory(response=FakeResponse(200, b'{"serverTime":1}', headers)))
    result = transport.send(time_request(role="S1"))
    spec = klines_request(symbol="BTCUSDT", interval="5m", start_ms=1_700_000_000_000, end_ms=1_700_000_299_999, limit=1, role="K5m")
    transport.send(spec)
    first, second = FakeConnection.instances
    assert (first.scheme, first.host, first.port, first.connect_timeout) == ("https", HOST, None, CONNECT_TIMEOUT_S)
    assert first.requests == [("GET", "/api/v3/time", {"Accept": "application/json", "User-Agent": "binance-research-obs/0.1"})]
    assert second.requests[0][:2] == ("GET", "/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime=1700000000000&endTime=1700000299999&limit=1")
    assert not {"authorization", "x-mbx-apikey", "cookie"} & {k.lower() for k in second.requests[0][2]}
    assert first.sock.timeout == READ_TIMEOUT_S                                         # the read timeout replaces the connect timeout
    assert (result.status, result.error, result.body) == (200, None, b'{"serverTime":1}')
    assert set(result.headers) == {"date", "x-mbx-used-weight-1m", "retry-after"}      # whitelist: no cookie, no other header
    assert transport.sent == 2 and first.closed and second.closed


def test_redirects_are_not_followed_and_are_reported_as_a_status():
    transport = HttpTransport(connection_factory=fake_factory(response=FakeResponse(302, b"", [("Location", "https://api.example.test/")])))
    result = transport.send(time_request(role="S1"))
    assert result.status == 302 and len(FakeConnection.instances) == 1 and "location" not in result.headers


def test_unsafe_specs_are_refused_before_a_connection_is_made():
    transport = HttpTransport(connection_factory=fake_factory())
    with pytest.raises(UnsafeRequest):
        transport.send(klines_request(symbol="BTCUSDT", interval="1d", start_ms=0, end_ms=1, limit=1))
    assert FakeConnection.instances == [] and transport.sent == 0


@pytest.mark.parametrize("base", ["http://data-api.binance.vision", "https://api.binance.com", "https://data-api.binance.vision:8443",
                                  "https://data-api.binance.vision/api", "https://user@data-api.binance.vision", "https://data-api.binance.vision?x=1",
                                  "http://example.com", "http://127.0.0.1.evil.test", "https://127.0.0.1"])
def test_base_url_must_be_the_official_host_or_loopback_http(base):
    with pytest.raises(ValueError):
        HttpTransport(base_url=base)


@pytest.mark.parametrize("base", ["https://data-api.binance.vision", "https://data-api.binance.vision/", "http://127.0.0.1:8080", "http://localhost:9"])
def test_accepted_base_urls(base):
    assert HttpTransport(base_url=base).sent == 0


@pytest.mark.parametrize("kw,expected", [({"connect_error": TimeoutError("t")}, TIMEOUT), ({"error": socket.timeout("t")}, TIMEOUT),
                                          ({"connect_error": ConnectionRefusedError("c")}, CONNECT_ERROR),
                                          ({"error": http.client.RemoteDisconnected("p")}, CONNECT_ERROR),
                                          ({"connect_error": ssl.SSLError("tls")}, CONNECT_ERROR)])
def test_errors_without_a_response_are_classified(kw, expected):
    result = HttpTransport(connection_factory=fake_factory(**kw)).send(time_request(role="S1"))
    assert (result.status, result.error) == (None, expected) and FakeConnection.instances[0].closed


def test_an_oversized_body_is_not_accepted():
    big = FakeResponse(200, b"x" * (MAX_BODY_BYTES + 5))
    result = HttpTransport(connection_factory=fake_factory(response=big)).send(time_request(role="S1"))
    assert (result.status, result.error) == (None, CONNECT_ERROR)


# ---------------- loopback: the watchdog really shuts the socket down ----------------
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):                                                                  # noqa: N802
        if self.path.startswith("/api/v3/klines"):
            self.server.hits.append(self.path)
            self.connection.settimeout(0.05)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not self.server.release.is_set():
                try:
                    if self.connection.recv(1, socket.MSG_PEEK) == b"":                  # the client closed its end
                        self.server.client_closed.set()
                        return
                except socket.timeout:
                    continue
                except OSError:
                    self.server.client_closed.set()
                    return
            return
        body = json.dumps({"serverTime": 1_700_000_000_000}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):                                                      # silence
        pass


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def loopback():
    server = _Server(("127.0.0.1", 0), _Handler)
    server.hits = []
    server.release = threading.Event()
    server.client_closed = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.release.set()
    server.shutdown()
    server.server_close()
    thread.join(2)


def make_transport(server, **kw):
    return HttpTransport(base_url=f"http://127.0.0.1:{server.server_address[1]}", **kw)


KLINES = klines_request(symbol="BTCUSDT", interval="5m", start_ms=0, end_ms=299_999, limit=1, role="K5m")


def test_the_deadline_cancels_a_hanging_request_by_closing_its_connection(loopback):
    transport = make_transport(loopback, deadline_ns=300 * MS, grace_ns=1 * S)
    t0 = time.monotonic()
    result = transport.send(KLINES)
    elapsed = time.monotonic() - t0
    assert (result.status, result.error) == (None, DEADLINE)
    assert 0.3 <= elapsed < 1.3 and loopback.hits == [KLINES.path + "?symbol=BTCUSDT&interval=5m&startTime=0&endTime=299999&limit=1"]
    assert loopback.client_closed.wait(2)                                                # the server saw the connection closed
    followup = transport.send(time_request(role="S1"))                                   # a new connection works normally
    assert (followup.status, followup.error) == (200, None) and json.loads(followup.body) == {"serverTime": 1_700_000_000_000}


def test_library_read_timeout_is_not_what_enforces_the_deadline(loopback):
    transport = make_transport(loopback, deadline_ns=400 * MS, grace_ns=1 * S)           # deadline far below the 12 s read timeout
    assert transport.send(KLINES).error == DEADLINE


def test_pacer_records_the_cancelled_request_and_waits_for_its_completion(loopback):
    transport = make_transport(loopback, deadline_ns=300 * MS, grace_ns=1 * S)
    pacer = Pacer(SystemClock(), transport)
    record = pacer.execute(KLINES)
    assert record.error == DEADLINE and record.status is None
    assert 300 * MS <= record.end_ns - record.start_ns < 1_300 * MS
    assert pacer.earliest_start_ns() >= record.end_ns                                    # nothing starts before the cancellation finished


# ---------------- clock and cancellation edge cases ----------------
def test_system_clock_is_monotonic_and_never_wakes_early():
    clock = SystemClock()
    t0 = clock.now_ns()
    clock.sleep_until_ns(t0 + 30 * MS)
    t1 = clock.now_ns()
    assert t1 >= t0 + 30 * MS and t1 < t0 + 500 * MS
    clock.sleep_until_ns(t0)                                                           # a target in the past returns immediately
    assert clock.now_ns() >= t1


class StubbornConnection(FakeConnection):
    """A request that blocks until the cancellation shuts the socket down; shutdown and close both fail with OSError."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.release = threading.Event()

    def connect(self):
        self.sock = FakeSock()
        outer = self

        def failing_shutdown(how):
            outer.release.set()
            raise OSError("already closed")
        self.sock.shutdown = failing_shutdown

    def request(self, method, url, headers):
        self.release.wait(5)
        raise OSError("connection closed")

    def close(self):
        raise OSError("close failed")


def test_cancellation_tolerates_oserrors_from_shutdown_and_close():
    transport = HttpTransport(connection_factory=lambda s, h, p, t: StubbornConnection(s, h, p, t), deadline_ns=100 * MS, grace_ns=1 * S)
    result = transport.send(time_request(role="S1"))
    assert (result.status, result.error) == (None, DEADLINE)
    assert transport.close() is None


def test_a_failing_close_after_a_normal_response_does_not_hide_the_response():
    class ClosingFails(FakeConnection):
        def close(self):
            raise OSError("close failed")
    transport = HttpTransport(connection_factory=lambda s, h, p, t: ClosingFails(s, h, p, t))
    result = transport.send(time_request(role="S1"))
    assert (result.status, result.error) == (200, None)
