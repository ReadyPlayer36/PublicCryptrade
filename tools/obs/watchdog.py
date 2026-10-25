"""PACE-8: strict total-request deadline enforced by cancellation, with a shared cancellation state.

A blocked request is interrupted by the `cancel` callback (the transport shuts the socket down). Phases that cannot be
interrupted (for example DNS resolution inside connect) are handled by the shared `CancellationState`: the worker checks it
after connection setup and immediately before sending, atomically with the cancel, so a request can never be sent after
cancellation, even if the worker wakes up much later.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable


class CancellationFailed(RuntimeError):
    """The cancelled request did not finish within the cancellation allowance (incident)."""


class Cancelled(RuntimeError):
    """Raised inside the worker when the request was cancelled before it was sent."""


class CancellationState:
    """Shared, thread-safe cancellation flag. `begin_send` and `cancel` are mutually atomic:
    either the worker marks the request as sent first (cancel then sees it in flight and interrupts it),
    or cancel comes first and the worker must not send."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._sending = False

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def sending(self) -> bool:
        with self._lock:
            return self._sending

    def cancel(self) -> bool:
        """Mark cancelled. Returns True when a request was already being sent."""
        with self._lock:
            self._cancelled = True
            return self._sending

    def begin_send(self) -> bool:
        """Called immediately before the request is written. False means: cancelled, do not send."""
        with self._lock:
            if self._cancelled:
                return False
            self._sending = True
            return True


@dataclass(frozen=True)
class DeadlineResult:
    timed_out: bool
    value: Any = None
    error: BaseException | None = None


def run_with_deadline(fn: Callable[[], Any], cancel: Callable[[], None], *, deadline_s: float, grace_s: float = 1.0,
                      state: CancellationState | None = None) -> DeadlineResult:
    """Run `fn` in a worker; if it has not finished after `deadline_s`, mark `state` cancelled, call `cancel()` (which must
    make `fn` return or raise promptly where that is possible) and wait at most `grace_s` for the worker to end.

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

    thread = threading.Thread(target=worker, name="obs-request", daemon=True)
    thread.start()
    thread.join(max(0.0, deadline_s))
    if not thread.is_alive():
        return DeadlineResult(False, holder.get("value"), holder.get("error"))
    if state is not None:
        state.cancel()
    cancel()
    thread.join(grace_s)
    if thread.is_alive():
        raise CancellationFailed("request still running after cancellation allowance")
    return DeadlineResult(True)
