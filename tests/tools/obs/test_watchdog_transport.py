"""PACE-8 strict start-anchored deadline, shared cancellation state (DNS-safe), non-200 disablement, allow-listed transport.
Offline only (fake connections and a loopback server)."""
import http.client
import json
import socket
import socketserver
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler

import pytest

from tests.fixtures.obs_fakes import FakeClock, audit_all
from tools.obs.clock import SystemClock
from tools.obs.pacer import NonOkResponse, Pacer, PacerAborted
from tools.obs.params import AUDIT_MAX_DURATION_NS, CANCEL_GRACE_NS, CONNECT_TIMEOUT_S, DEADLINE_NS, HOST, MS, READ_TIMEOUT_S, S
from tools.obs.specs import UnsafeRequest, klines_request, time_request
from tools.obs.transport import (CANCEL_FAILED, CONNECT_ERROR, DEADLINE, MAX_BODY_BYTES, TIMEOUT, HttpTransport, TransportDisabled)
from tools.obs.watchdog import Cancelled, CancellationFailed, CancellationState, run_with_deadline

KLINES = klines_request(symbol="BTCUSDT", interval="5m", start_ms=0, end_ms=299_999, limit=1, role="PROBE")
CLOCK = SystemClock()


def go(transport, spec, *, deadline_ns=DEADLINE_NS):
    """Send with an absolute deadline `deadline_ns` after now (what the pacer does with its recorded start_ns)."""
    return transport.send(spec, deadline_at_ns=CLOCK.now_ns() + deadline_ns)


# ---------------- watchdog and cancellation state ----------------
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
    state = CancellationState()

    def blocked():
        release.wait(10)
        raise OSError("connection closed")

    def cancel():
        cancelled.append(time.monotonic())
        release.set()

    t0 = time.monotonic()
    result = run_with_deadline(blocked, cancel, deadline_s=0.15, grace_s=1.0, state=state)
    elapsed = time.monotonic() - t0
    assert result.timed_out and result.error is None and len(cancelled) == 1 and state.cancelled
    assert 0.15 <= cancelled[0] - t0 < 0.5 and 0.15 <= elapsed < 1.0


def test_a_request_that_ignores_the_cancellation_is_an_incident_and_the_state_stays_cancelled():
    release = threading.Event()
    state = CancellationState()
    try:
        with pytest.raises(CancellationFailed):
            run_with_deadline(lambda: release.wait(5), lambda: None, deadline_s=0.05, grace_s=0.1, state=state)
        assert state.cancelled
    finally:
        release.set()


def test_a_zero_or_negative_deadline_cancels_immediately():
    release = threading.Event()
    result = run_with_deadline(lambda: release.wait(5), release.set, deadline_s=-3.0, grace_s=1.0)
    assert result.timed_out


def test_cancellation_state_semantics():
    state = CancellationState()
    assert not state.cancelled and not state.sending
    assert state.begin_send() is True and state.sending
    assert state.cancel() is True and state.cancelled                 # cancel sees the request in flight
    assert state.begin_send() is False                               # nothing may be sent after a cancellation
    fresh = CancellationState()
    assert fresh.cancel() is False and fresh.begin_send() is False


def test_begin_send_and_cancel_are_atomic_under_races():
    for _ in range(300):
        state = CancellationState()
        barrier = threading.Barrier(2)
        out = {}

        def worker():
            barrier.wait()
            out["sent"] = state.begin_send()

        def canceller():
            barrier.wait()
            out["in_flight"] = state.cancel()

        threads = [threading.Thread(target=worker), threading.Thread(target=canceller)]
        [t.start() for t in threads]
        [t.join(2) for t in threads]
        assert out["sent"] == out["in_flight"]                       # either sent-then-cancelled, or cancelled-then-never-sent


def test_protocol_constants():
    assert DEADLINE_NS == 17 * S and AUDIT_MAX_DURATION_NS == 18 * S and CANCEL_GRACE_NS == 1 * S
    assert (CONNECT_TIMEOUT_S, READ_TIMEOUT_S) == (5.0, 12.0) and DEADLINE_NS == (CONNECT_TIMEOUT_S + READ_TIMEOUT_S) * S
    transport = HttpTransport()
    assert transport.grace_ns == CANCEL_GRACE_NS and transport.sent == 0 and transport.disabled_reason is None
    assert not hasattr(transport, "deadline_ns")                     # the deadline length belongs to the pacer, anchored at start_ns


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

    def __init__(self, scheme, host, port, timeout, *, response=None, error=None, connect_error=None, connect_gate=None):
        self.scheme, self.host, self.port, self.connect_timeout = scheme, host, port, timeout
        self.response, self.error, self.connect_error, self.connect_gate = response or FakeResponse(), error, connect_error, connect_gate
        self.sock = None
        self.requests = []
        self.closed = False
        FakeConnection.instances.append(self)

    def connect(self):
        if self.connect_gate is not None:                             # simulates a DNS resolution that cannot be interrupted
            self.connect_gate.wait(10)
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
    result = go(transport, time_request(role="S1"))
    spec = klines_request(symbol="BTCUSDT", interval="5m", start_ms=1_700_000_000_000, end_ms=1_700_000_299_999, limit=1, role="K5m")
    go(transport, spec)
    first, second = FakeConnection.instances
    assert (first.scheme, first.host, first.port, first.connect_timeout) == ("https", HOST, None, CONNECT_TIMEOUT_S)
    assert first.requests == [("GET", "/api/v3/time", {"Accept": "application/json", "User-Agent": "binance-research-obs/0.1"})]
    assert second.requests[0][:2] == ("GET", "/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime=1700000000000&endTime=1700000299999&limit=1")
    assert not {"authorization", "x-mbx-apikey", "cookie"} & {k.lower() for k in second.requests[0][2]}
    assert first.sock.timeout == READ_TIMEOUT_S
    assert (result.status, result.error, result.body) == (200, None, b'{"serverTime":1}')
    assert set(result.headers) == {"date", "x-mbx-used-weight-1m", "retry-after"}
    assert transport.sent == 2 and first.closed and second.closed and transport.disabled_reason is None


@pytest.mark.parametrize("status", [204, 301, 302, 400, 403, 404, 418, 429, 500, 503])
def test_any_non_200_response_permanently_disables_the_transport(status):
    transport = HttpTransport(connection_factory=fake_factory(response=FakeResponse(status, b"", [("Location", "https://other.test/")])))
    result = go(transport, time_request(role="S1"))
    assert result.status == status and "location" not in result.headers and len(FakeConnection.instances) == 1
    assert transport.disabled_reason == f"HTTP-{status}"
    with pytest.raises(TransportDisabled):
        go(transport, time_request(role="S1"))                         # a continuation attempt: refused before any connection
    with pytest.raises(TransportDisabled):
        go(transport, KLINES)
    assert len(FakeConnection.instances) == 1 and transport.sent == 1


def test_disablement_is_permanent_and_keeps_the_first_reason():
    transport = HttpTransport(connection_factory=fake_factory())
    transport.disable("FIRST")
    transport.disable("SECOND")
    assert transport.disabled_reason == "FIRST"
    with pytest.raises(TransportDisabled):
        go(transport, time_request(role="S1"))
    assert FakeConnection.instances == [] and transport.sent == 0


def test_unsafe_specs_are_refused_before_a_connection_is_made():
    transport = HttpTransport(connection_factory=fake_factory())
    with pytest.raises(UnsafeRequest):
        go(transport, klines_request(symbol="BTCUSDT", interval="1d", start_ms=0, end_ms=1, limit=1))
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
def test_errors_without_a_response_are_classified_and_do_not_disable(kw, expected):
    transport = HttpTransport(connection_factory=fake_factory(**kw))
    result = go(transport, time_request(role="S1"))
    assert (result.status, result.error) == (None, expected) and FakeConnection.instances[0].closed
    assert transport.disabled_reason is None


def test_an_oversized_body_is_not_accepted():
    big = FakeResponse(200, b"x" * (MAX_BODY_BYTES + 5))
    result = go(HttpTransport(connection_factory=fake_factory(response=big)), time_request(role="S1"))
    assert (result.status, result.error) == (None, CONNECT_ERROR)


# ---------------- start-anchored deadline (finding 4) ----------------
def test_a_deadline_that_has_already_passed_sends_nothing():
    transport = HttpTransport(connection_factory=fake_factory())
    result = transport.send(time_request(role="S1"), deadline_at_ns=CLOCK.now_ns() - 1)
    assert (result.status, result.error) == (None, DEADLINE)
    assert FakeConnection.instances == [] and transport.sent == 1


def test_time_spent_before_the_transport_is_reached_counts_against_the_deadline():
    gate = threading.Event()
    transport = HttpTransport(connection_factory=fake_factory(connect_gate=gate), grace_ns=1 * S)
    anchor = CLOCK.now_ns()
    time.sleep(0.2)                                                   # 0.2 s are spent between the recorded start and the send
    t0 = time.monotonic()
    threading.Timer(0.3, gate.set).start()                            # DNS returns after the (shortened) deadline, inside the allowance
    result = transport.send(time_request(role="S1"), deadline_at_ns=anchor + 300 * MS)
    waited = time.monotonic() - t0
    assert result.error == DEADLINE
    assert 0.28 <= waited < 0.6                                       # the worker was released at 0.3 s; the cancellation had fired at ~0.1 s
    assert FakeConnection.instances[0].requests == []                 # cancelled at ~0.1 s (0.3 s anchor minus 0.2 s spent), so nothing was sent


# ---------------- DNS-safe cancellation (finding 3) ----------------
def wait_for(predicate, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_stalled_dns_never_sends_after_the_cancellation_and_disables_the_transport():
    gate = threading.Event()
    transport = HttpTransport(connection_factory=fake_factory(connect_gate=gate), grace_ns=100 * MS)
    with pytest.raises(CancellationFailed):
        go(transport, time_request(role="S1"), deadline_ns=100 * MS)
    conn = FakeConnection.instances[0]
    assert transport.disabled_reason == CANCEL_FAILED
    assert conn.requests == []                                        # still stuck in "DNS": nothing was written
    with pytest.raises(TransportDisabled):
        go(transport, time_request(role="S1"))                         # a new send is refused, no new connection
    assert len(FakeConnection.instances) == 1
    gate.set()                                                        # DNS finally returns
    assert wait_for(lambda: conn.closed)                              # the orphaned worker notices, closes the connection ...
    time.sleep(0.05)
    assert conn.requests == []                                        # ... and never writes the request


def test_dns_that_returns_inside_the_allowance_is_a_clean_cancellation_without_a_send():
    gate = threading.Event()
    transport = HttpTransport(connection_factory=fake_factory(connect_gate=gate), grace_ns=1 * S)
    threading.Timer(0.25, gate.set).start()                           # DNS returns after the deadline but inside the allowance
    result = go(transport, time_request(role="S1"), deadline_ns=100 * MS)
    conn = FakeConnection.instances[0]
    assert (result.status, result.error) == (None, DEADLINE)
    assert conn.requests == [] and conn.closed and transport.disabled_reason is None


def test_cancelling_before_the_connection_is_set_up_skips_the_connect():
    state = CancellationState()
    state.cancel()
    called = []

    class Conn(FakeConnection):
        def connect(self):
            called.append("connect")
    factory = lambda scheme, host, port, timeout: Conn(scheme, host, port, timeout)       # noqa: E731
    transport = HttpTransport(connection_factory=factory)
    # a deadline that is already over is handled without any connection at all
    assert transport.send(time_request(role="S1"), deadline_at_ns=CLOCK.now_ns() - 5).error == DEADLINE
    assert called == []


def test_a_worker_released_after_cancellation_never_connects_or_sends():
    gate = threading.Event()
    created = []

    class Tracking(FakeConnection):
        connected = False

        def connect(self):
            Tracking.connected = True
            super().connect()

    def slow_factory(scheme, host, port, timeout):
        gate.wait(10)                                                # construction itself is stuck, before any connect
        conn = Tracking(scheme, host, port, timeout)
        created.append(conn)
        return conn

    transport = HttpTransport(connection_factory=slow_factory, grace_ns=100 * MS)
    with pytest.raises(CancellationFailed):
        go(transport, time_request(role="S1"), deadline_ns=100 * MS)
    gate.set()
    assert wait_for(lambda: bool(created) and created[0].closed)       # the late worker saw the cancellation and closed the connection
    time.sleep(0.05)
    assert Tracking.connected is False and created[0].requests == []   # no connect (no DNS) and no request after the cancellation


def test_a_stalled_connect_inside_the_pacer_is_recorded_as_a_failed_cancellation_and_ends_the_run():
    gate = threading.Event()
    transport = HttpTransport(connection_factory=fake_factory(connect_gate=gate), grace_ns=100 * MS)
    pacer = Pacer(CLOCK, transport, deadline_ns=100 * MS)
    with pytest.raises(CancellationFailed):
        pacer.execute(time_request(role="S1"))
    record = pacer.records[0]
    assert (record.status, record.error) == (None, CANCEL_FAILED)
    assert pacer.abort_reason == "INCIDENT-CANCEL" and transport.disabled_reason == CANCEL_FAILED     # the transport disabled itself first
    with pytest.raises(PacerAborted):
        pacer.execute(time_request(role="S1"))
    gate.set()
    assert wait_for(lambda: FakeConnection.instances[0].closed)
    assert FakeConnection.instances[0].requests == [] and len(FakeConnection.instances) == 1


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
    transport = HttpTransport(connection_factory=lambda s, h, p, t: StubbornConnection(s, h, p, t), grace_ns=1 * S)
    result = go(transport, time_request(role="S1"), deadline_ns=100 * MS)
    assert (result.status, result.error) == (None, DEADLINE)
    assert transport.close() is None and transport.disabled_reason is None


def test_a_failing_close_after_a_normal_response_does_not_hide_the_response():
    class ClosingFails(FakeConnection):
        def close(self):
            raise OSError("close failed")
    result = go(HttpTransport(connection_factory=lambda s, h, p, t: ClosingFails(s, h, p, t)), time_request(role="S1"))
    assert (result.status, result.error) == (200, None)


def test_system_clock_is_monotonic_and_never_wakes_early():
    clock = SystemClock()
    t0 = clock.now_ns()
    clock.sleep_until_ns(t0 + 30 * MS)
    t1 = clock.now_ns()
    assert t1 >= t0 + 30 * MS and t1 < t0 + 500 * MS
    clock.sleep_until_ns(t0)
    assert clock.now_ns() >= t1


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
        self.server.time_hits += 1
        status = self.server.time_status
        body = json.dumps({"serverTime": 1_700_000_000_000}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def loopback():
    server = _Server(("127.0.0.1", 0), _Handler)
    server.hits = []
    server.time_hits = 0
    server.time_status = 200
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


def test_the_deadline_cancels_a_hanging_request_by_closing_its_connection(loopback):
    transport = make_transport(loopback, grace_ns=1 * S)
    t0 = time.monotonic()
    result = go(transport, KLINES, deadline_ns=300 * MS)
    elapsed = time.monotonic() - t0
    assert (result.status, result.error) == (None, DEADLINE)
    assert 0.3 <= elapsed < 1.3 and loopback.hits == [KLINES.path + "?symbol=BTCUSDT&interval=5m&startTime=0&endTime=299999&limit=1"]
    assert loopback.client_closed.wait(2)
    followup = go(transport, time_request(role="S1"))
    assert (followup.status, followup.error) == (200, None) and json.loads(followup.body) == {"serverTime": 1_700_000_000_000}


def test_library_read_timeout_is_not_what_enforces_the_deadline(loopback):
    assert go(make_transport(loopback), KLINES, deadline_ns=400 * MS).error == DEADLINE


def test_pacer_records_the_cancelled_request_and_waits_for_its_completion(loopback):
    pacer = Pacer(SystemClock(), make_transport(loopback), deadline_ns=300 * MS)
    record = pacer.execute(KLINES)
    assert record.error == DEADLINE and record.status is None
    assert 300 * MS <= record.end_ns - record.start_ns < 1_300 * MS
    assert pacer.earliest_start_ns() >= record.end_ns


def test_a_real_non_200_over_a_socket_stops_all_egress(loopback):
    loopback.time_status = 403
    transport = make_transport(loopback)
    pacer = Pacer(SystemClock(), transport)
    spec = time_request(role="T", group_name="sync")
    with pytest.raises(NonOkResponse) as raised:
        pacer.execute(spec)
    assert raised.value.record.status == 403 and pacer.abort_reason == "HTTP-403" and transport.disabled_reason == "HTTP-403"
    with pytest.raises(PacerAborted):
        pacer.execute(spec)                                            # continuation through the pacer
    with pytest.raises(TransportDisabled):
        transport.send(spec, deadline_at_ns=CLOCK.now_ns() + 5 * S)     # continuation around the pacer
    assert loopback.time_hits == 1                                     # exactly one request ever reached the server
    assert audit_all(pacer.records, abort_seq=pacer.abort_seq, wrapper_count=transport.sent).ok
