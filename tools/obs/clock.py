"""Local MONOTONIC clock only (the wall clock is never read)."""
from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...
    def sleep_until_ns(self, target_ns: int) -> None: ...


class SystemClock:
    def now_ns(self) -> int:
        return time.monotonic_ns()

    def sleep_until_ns(self, target_ns: int) -> None:
        """Sleep until the monotonic clock has reached target_ns (never returns early)."""
        while True:
            remaining = target_ns - time.monotonic_ns()
            if remaining <= 0:
                return
            time.sleep(remaining / 1_000_000_000)
