"""HTTP transport: allow-listed host, no redirects, no proxies, single attempt, strict total deadline (PACE-8).

Built on http.client so the watchdog can really interrupt a blocked request: it calls socket.shutdown(SHUT_RDWR) on the
connection's socket (closing the client object alone does NOT wake a blocked read; verified by experiment) and then closes it.
"""
from __future__ import annotations

import http.client
import socket
import ssl
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlencode, urlsplit

from tools.obs.params import (CANCEL_GRACE_NS, CONNECT_TIMEOUT_S, DEADLINE_NS, HOST, READ_TIMEOUT_S, RESPONSE_HEADER_WHITELIST, S)
from tools.obs.specs import RequestSpec, validate_spec
from tools.obs.watchdog import run_with_deadline

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
REQUEST_HEADERS = {"Accept": "application/json", "User-Agent": "binance-research-obs/0.1"}
MAX_BODY_BYTES = 4 * 1024 * 1024

# Outcomes without an HTTP response
DEADLINE = "DEADLINE"                # strict 17 s deadline reached, request cancelled
TIMEOUT = "TIMEOUT"                  # connect/read timeout raised by the socket layer
CONNECT_ERROR = "CONNECT_ERROR"      # any other transport failure


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


class HttpTransport:
    """Sends allow-listed GET requests. `base_url` must be https://data-api.binance.vision; a loopback http URL is accepted
    only for offline tests. Environment proxies are never used (http.client does not read them)."""

    def __init__(self, *, base_url: str = f"https://{HOST}", connection_factory: ConnectionFactory = default_connection_factory,
                 deadline_ns: int = DEADLINE_NS, grace_ns: int = CANCEL_GRACE_NS) -> None:
        parts = urlsplit(base_url)
        official = parts.scheme == "https" and parts.hostname == HOST and parts.port in (None, 443)
        loopback = parts.scheme == "http" and parts.hostname in _LOOPBACK
        if not (official or loopback) or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
            raise ValueError("base_url must be https://data-api.binance.vision (loopback http is for offline tests only)")
        self._scheme, self._host, self._port = parts.scheme, parts.hostname, parts.port
        self._factory = connection_factory
        self.deadline_ns = deadline_ns
        self.grace_ns = grace_ns
        self.sent = 0                                     # egress counter for the PACE-5 (g) cross-check

    def close(self) -> None:                              # no persistent connection is kept between requests
        return None

    def send(self, spec: RequestSpec) -> TransportResult:
        validate_spec(spec)
        self.sent += 1
        target = spec.path + ("?" + urlencode(spec.params) if spec.params else "")
        holder: dict[str, Any] = {}

        def call() -> TransportResult:
            conn = self._factory(self._scheme, self._host, self._port, CONNECT_TIMEOUT_S)
            holder["conn"] = conn
            conn.connect()                                # TLS handshake included, bounded by the connect timeout
            if conn.sock is not None:
                conn.sock.settimeout(READ_TIMEOUT_S)
            conn.request("GET", target, headers=dict(REQUEST_HEADERS))
            response = conn.getresponse()
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                return TransportResult(None, CONNECT_ERROR)
            headers = {name.lower(): value for name, value in response.getheaders() if name.lower() in RESPONSE_HEADER_WHITELIST}
            return TransportResult(response.status, None, headers, body)

        def cancel() -> None:
            conn = holder.get("conn")
            if conn is None:
                return
            sock = getattr(conn, "sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)       # wakes a blocked read/write immediately
                except OSError:
                    pass
            try:
                conn.close()
            except OSError:
                pass

        outcome = run_with_deadline(call, cancel, deadline_s=self.deadline_ns / S, grace_s=self.grace_ns / S)
        conn = holder.get("conn")
        if conn is not None and not outcome.timed_out:
            try:
                conn.close()
            except OSError:
                pass
        if outcome.timed_out:
            return TransportResult(None, DEADLINE)
        if outcome.error is not None:
            return TransportResult(None, TIMEOUT if isinstance(outcome.error, (TimeoutError, socket.timeout)) else CONNECT_ERROR)
        return outcome.value
