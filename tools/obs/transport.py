"""HTTP transport: allow-listed host, no redirects, no proxies, single attempt, strict start-anchored deadline (PACE-8).

Built on http.client so the watchdog can really interrupt a blocked request: it calls socket.shutdown(SHUT_RDWR) on the
connection's socket (closing the client object alone does NOT wake a blocked read; verified by experiment) and then closes it.
DNS resolution cannot be interrupted: a shared CancellationState is checked after connection setup and immediately before the
request is written, so nothing is ever sent after a cancellation, and the transport is permanently disabled when a cancellation
does not complete. The transport is also permanently disabled by any non-200 response.
"""
from __future__ import annotations

import http.client
import socket
import ssl
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlencode, urlsplit

from tools.obs.clock import Clock, SystemClock
from tools.obs.params import (CANCEL_GRACE_NS, CONNECT_TIMEOUT_S, HOST, READ_TIMEOUT_S, RESPONSE_HEADER_WHITELIST, SEND_TIMEOUT_S)
from tools.obs.specs import RequestSpec, validate_spec
from tools.obs.watchdog import Cancelled, CancellationFailed, CancellationState, run_with_deadline

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
REQUEST_HEADERS = {"Accept": "application/json", "User-Agent": "binance-research-obs/0.1"}
MAX_BODY_BYTES = 4 * 1024 * 1024

# Outcomes without an HTTP response
DEADLINE = "DEADLINE"                # strict 17 s deadline (anchored at the pacer's start_ns) reached, request cancelled
TIMEOUT = "TIMEOUT"                  # connect/read timeout raised by the socket layer
CONNECT_ERROR = "CONNECT_ERROR"      # any other transport failure
CANCEL_FAILED = "CANCEL_FAILED"      # the cancellation did not complete within the allowance (incident)


class TransportDisabled(RuntimeError):
    """The transport was permanently disabled (non-200 response or failed cancellation); nothing more is sent."""


@dataclass(frozen=True)
class TransportResult:
    status: int | None
    error: str | None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


class Connection(Protocol):
    sock: Any
    def connect(self) -> None: ...
    def request(self, method: str, url: str, headers: dict[str, str]) -> None: ...
    def getresponse(self) -> Any: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[str, str, int | None, float], Connection]


def default_connection_factory(scheme: str, host: str, port: int | None, timeout: float) -> Connection:
    if scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _close_quietly(conn: Any) -> None:
    sock = getattr(conn, "sock", None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    try:
        conn.close()
    except OSError:
        pass


class HttpTransport:
    """Sends allow-listed GET requests. `base_url` must be https://data-api.binance.vision; a loopback http URL is accepted
    only for offline tests. Environment proxies are never used (http.client does not read them).

    `send` takes the ABSOLUTE monotonic deadline (the pacer's start_ns plus the 17 s deadline), measured on `clock`, so the
    total time since the pacer started the request, not since this method was entered, is what is limited."""

    def __init__(self, *, base_url: str = f"https://{HOST}", connection_factory: ConnectionFactory = default_connection_factory,
                 grace_ns: int = CANCEL_GRACE_NS, clock: Clock | None = None) -> None:
        parts = urlsplit(base_url)
        official = parts.scheme == "https" and parts.hostname == HOST and parts.port in (None, 443)
        loopback = parts.scheme == "http" and parts.hostname in _LOOPBACK
        if not (official or loopback) or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
            raise ValueError("base_url must be https://data-api.binance.vision (loopback http is for offline tests only)")
        self._scheme, self._host, self._port = parts.scheme, parts.hostname, parts.port
        self._factory = connection_factory
        self.grace_ns = grace_ns
        self.clock: Clock = clock if clock is not None else SystemClock()
        self.sent = 0                                     # egress counter for the PACE-5 (g) cross-check
        self._lock = threading.Lock()
        self._disabled: str | None = None

    # ----- permanent disablement -----
    @property
    def disabled_reason(self) -> str | None:
        with self._lock:
            return self._disabled

    def disable(self, reason: str) -> None:
        """Permanently disable the transport; there is no way back (a new run needs a new instance)."""
        with self._lock:
            if self._disabled is None:
                self._disabled = reason

    def close(self) -> None:                              # no persistent connection is kept between requests
        return None

    # ----- sending -----
    def send(self, spec: RequestSpec, *, deadline_at_ns: int) -> TransportResult:
        with self._lock:
            if self._disabled is not None:
                raise TransportDisabled(self._disabled)
        validate_spec(spec)
        self.sent += 1
        remaining_ns = deadline_at_ns - self.clock.now_ns()
        if remaining_ns <= 0:                             # the deadline (anchored at start_ns) is already over: send nothing
            return TransportResult(None, DEADLINE)
        target = spec.path + ("?" + urlencode(spec.params) if spec.params else "")
        state = CancellationState()
        holder: dict[str, Any] = {}

        def over() -> bool:
            return self.clock.now_ns() >= deadline_at_ns          # the ABSOLUTE deadline (pacer start_ns + 17 s), re-read here

        def give_up(conn: Any, why: str) -> None:
            if conn is not None:                                  # the worker stops here: it raises, nothing else runs
                _close_quietly(conn)
            raise Cancelled(why)

        def call() -> TransportResult:
            if over():                                            # thread start-up latency must not extend the deadline
                give_up(None, "deadline passed before the worker started")
            conn = self._factory(self._scheme, self._host, self._port, CONNECT_TIMEOUT_S)
            holder["conn"] = conn
            if state.cancelled:                                   # cancelled before setup even started
                give_up(conn, "cancelled before connection setup")
            if over():
                give_up(conn, "deadline passed before connection setup")
            conn.connect()                                        # DNS + TCP + TLS: bounded by the connect timeout except DNS
            conn.auto_open = 0                                    # http.client would silently RECONNECT a closed connection on request()
            sock = conn.sock                                      # one read: a concurrent close may set conn.sock to None
            if sock is not None:
                sock.settimeout(READ_TIMEOUT_S)

            def deadline_allows() -> bool:
                return not over()                                 # evaluated INSIDE the lock, immediately before the write

            def write() -> None:
                if sock is None or conn.sock is None:             # closed by a cancellation: never write, never reconnect
                    raise Cancelled("connection closed before the request was written")
                sock.settimeout(SEND_TIMEOUT_S)                   # a stuck write is bounded; cancel() also unblocks it at once
                conn.request("GET", target, headers=dict(REQUEST_HEADERS))
                sock.settimeout(READ_TIMEOUT_S)

            if not state.guarded_send(deadline_allows, write):    # cancellation check + deadline check, then the write
                give_up(conn, "cancelled or past the deadline before the request was written")
            response = conn.getresponse()
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                return TransportResult(None, CONNECT_ERROR)
            headers = {name.lower(): value for name, value in response.getheaders() if name.lower() in RESPONSE_HEADER_WHITELIST}
            return TransportResult(response.status, None, headers, body)

        def cancel() -> None:
            """Never blocks. run_with_deadline has already flagged the shared state; this shuts the socket down, so a blocked read
            or write wakes at once and anything the worker tries to write afterwards fails in the kernel: nothing is transmitted
            after this returns."""
            conn = holder.get("conn")
            if conn is not None:
                _close_quietly(conn)

        try:
            outcome = run_with_deadline(call, cancel, deadline_at_ns=deadline_at_ns, clock=self.clock, grace_ns=self.grace_ns, state=state)
        except CancellationFailed:
            self.disable(CANCEL_FAILED)                   # the orphaned worker can no longer send (state is cancelled)
            raise
        conn = holder.get("conn")
        if conn is not None and not outcome.timed_out:
            try:
                conn.close()
            except OSError:
                pass
        if outcome.timed_out:
            return TransportResult(None, DEADLINE)
        if outcome.error is not None:
            if isinstance(outcome.error, Cancelled):
                return TransportResult(None, DEADLINE)
            return TransportResult(None, TIMEOUT if isinstance(outcome.error, (TimeoutError, socket.timeout)) else CONNECT_ERROR)
        result = outcome.value
        if result.status is not None and result.status != 200:
            self.disable(f"HTTP-{result.status}")         # any non-200 response ends all egress on this transport
        return result
