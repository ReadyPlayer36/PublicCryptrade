"""PACE-8: strict total-request deadline enforced by cancellation (not just library phase timeouts)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable


class CancellationFailed(RuntimeError):
    """The cancelled request did not finish within the cancellation allowance (incident)."""


@dataclass(frozen=True)
class DeadlineResult:
    timed_out: bool
    value: Any = None
    error: BaseException | None = None


def run_with_deadline(fn: Callable[[], Any], cancel: Callable[[], None], *, deadline_s: float, grace_s: float = 1.0) -> DeadlineResult:
    """Run `fn` in a worker; if it has not finished after `deadline_s`, call `cancel()` (which must make `fn` return
    or raise promptly, e.g. by closing the connection) and wait at most `grace_s` for the worker to end.

    Returns timed_out=True after a cancellation. Raises CancellationFailed if the worker is still alive after the
    allowance. An exception raised by `fn` before the deadline is returned in `error`; one raised because of the
    cancellation is swallowed (the outcome is the timeout).
    """
    holder: dict[str, Any] = {}

    def worker() -> None:
        try:
            holder["value"] = fn()
        except BaseException as exc:                      # noqa: BLE001 - reported through the result, never lost
            holder["error"] = exc

    thread = threading.Thread(target=worker, name="obs-request", daemon=True)
    thread.start()
    thread.join(deadline_s)
    if not thread.is_alive():
        return DeadlineResult(False, holder.get("value"), holder.get("error"))
    cancel()
    thread.join(grace_s)
    if thread.is_alive():
        raise CancellationFailed("request still running after cancellation allowance")
    return DeadlineResult(True)
