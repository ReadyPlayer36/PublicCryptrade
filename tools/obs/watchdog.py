"""PACE-8: strict total-request deadline enforced by cancellation, anchored at an ABSOLUTE monotonic deadline.

`run_with_deadline` never computes a fixed duration once: it re-reads the monotonic clock against the absolute deadline
(the pacer's `start_ns + 17 s`) every time it waits, so thread start-up latency and early wake-ups cannot stretch the deadline.

Cancellation is non-blocking by construction. `CancellationState.cancel()` takes no lock, so it can never be starved by a
request write that is in progress; the transport then forcibly shuts the socket down, which unblocks a blocked read or write
at once. A write that starts after the shutdown cannot transmit anything (the kernel refuses to send on a shut-down socket),
so no explicit lock around "check then write" is needed: the shutdown is the enforcement. Phases that cannot be interrupted
(DNS resolution inside connect) are handled by the shared state: the worker checks it after connection setup and before the
write, and the transport is disabled when a cancellation does not complete.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from tools.obs.clock import Clock
from tools.obs.params import CANCEL_GRACE_NS, S


class CancellationFailed(RuntimeError):
    """The cancelled request did not finish within the cancellation allowance (incident)."""


class Cancelled(RuntimeError):
    """Raised inside the worker when the request was cancelled before it was sent."""


class CancellationState:
    """Shared cancellation flag, deliberately lock-free so that `cancel()` is never delayed by an active write.

    Plain attribute writes are atomic in CPython. The ordering the transport relies on: `cancel()` first sets the flag and only
    then reads the connection's socket to shut it down; the worker first obtains its socket (end of connect) and only then
    reads the flag. Hence either cancel sees the socket and shuts it down, or the worker sees the flag and never writes."""

    def __init__(self) -> None:
        self._cancelled = False
        self._sending = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def sending(self) -> bool:
        return self._sending

    def cancel(self) -> bool:
        """Mark cancelled; never blocks. Returns True when a request had already been handed to the write."""
        self._cancelled = True
        return self._sending

    def guarded_send(self, allowed: Callable[[], bool], send: Callable[[], None]) -> bool:
        """Worker side: refuse if cancelled; refuse (and cancel for good) if `allowed()` is False, e.g. the absolute deadline
        has passed; otherwise mark the request as sent and run `send()`. Returns False when nothing was sent. A cancellation
        arriving after the checks is neutralised by the socket shutdown, not by blocking the canceller."""
        if self._cancelled:
            return False
        if not allowed():
            self._cancelled = True
            return False
        self._sending = True
        send()
        return True


@dataclass(frozen=True)
class DeadlineResult:
    timed_out: bool
    value: Any = None
    error: BaseException | None = None


def _wait_until(thread: threading.Thread, deadline_at_ns: int, clock: Clock) -> bool:
    """Wait for `thread` until the absolute deadline; the remaining time is recomputed from the clock on every iteration.
    Returns True when the thread has finished."""
    while True:
        if not thread.is_alive():
            return True
        remaining_ns = deadline_at_ns - clock.now_ns()
        if remaining_ns <= 0:
            return not thread.is_alive()
        thread.join(remaining_ns / S)                        # may return early (spurious wake-up): the loop re-reads the clock


def run_with_deadline(fn: Callable[[], Any], cancel: Callable[[], None], *, deadline_at_ns: int, clock: Clock,
                      grace_ns: int = CANCEL_GRACE_NS, state: CancellationState | None = None,
                      thread_factory: Callable[..., threading.Thread] = threading.Thread) -> DeadlineResult:
    """Run `fn` in a worker; if it has not finished when the ABSOLUTE monotonic `deadline_at_ns` is reached, mark `state`
    cancelled, call `cancel()` (which must make `fn` return or raise promptly where that is possible, and must not block) and
    wait until `grace_ns` after the moment the cancellation was issued.

    Returns timed_out=True after a cancellation. Raises CancellationFailed if the worker is still alive after the allowance
    (for example stuck in DNS); the worker is then orphaned but, because `state` is cancelled, it can never send. An exception
    raised by `fn` before the deadline is returned in `error`; one raised because of the cancellation is swallowed.
    """
    holder: dict[str, Any] = {}

    def worker() -> None:
        try:
            holder["value"] = fn()
        except BaseException as exc:                      # noqa: BLE001 - reported through the result, never lost
            holder["error"] = exc

    thread = thread_factory(target=worker, name="obs-request", daemon=True)
    thread.start()                                        # start-up latency is inside the absolute deadline, not added to it
    if _wait_until(thread, deadline_at_ns, clock):
        return DeadlineResult(False, holder.get("value"), holder.get("error"))
    if state is not None:
        state.cancel()
    cancel()
    if not _wait_until(thread, clock.now_ns() + grace_ns, clock):
        raise CancellationFailed("request still running after cancellation allowance")
    return DeadlineResult(True)
