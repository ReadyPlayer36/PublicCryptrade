"""Global rate-limit cooldown state: {"until_ms": int, "reason": str}, atomic writes."""
from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Frozen minimums in seconds (matrix.yaml `cooldown.durations`); a test pins these to the YAML.
COOLDOWN_MINIMUM_S: dict[str, int] = {
    "418": 600,
    "429_exhausted": 300,
    "429_retry_after_over_60": 600,
    "429_retry_after_exceeds_sleep_budget": 600,
}


class CorruptCooldownError(ValueError):
    """Raised when cooldown state is missing, corrupt, non-integer, or negative."""


def cooldown_duration_s(trigger: str, retry_after_s: float | None) -> int:
    """max(supplied Retry-After, trigger minimum), rounded up to whole seconds."""
    try:
        minimum = COOLDOWN_MINIMUM_S[trigger]
    except KeyError as exc:
        raise ValueError(f"unknown cooldown trigger: {trigger!r}") from exc
    supplied = 0 if retry_after_s is None else retry_after_s
    if isinstance(supplied, bool) or not isinstance(supplied, (int, float)):
        raise ValueError("retry_after_s must be a number or None")
    if (isinstance(supplied, float) and not math.isfinite(supplied)) or supplied < 0:
        raise ValueError("retry_after_s must be finite and >= 0")
    return int(max(-(-supplied // 1), minimum))


def _validate(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict) or set(state) != {"until_ms", "reason"}:
        raise CorruptCooldownError("invalid cooldown state: expected exactly until_ms and reason")
    until, reason = state["until_ms"], state["reason"]
    if isinstance(until, bool) or not isinstance(until, int):
        raise CorruptCooldownError("invalid cooldown state: until_ms must be an integer")
    if until < 0:
        raise CorruptCooldownError("invalid cooldown state: until_ms is negative")
    if not isinstance(reason, str) or not reason:
        raise CorruptCooldownError("invalid cooldown state: reason must be a non-empty string")
    return {"until_ms": until, "reason": reason}


def read_cooldown(path: str | Path) -> dict[str, Any]:
    """Load and validate cooldown state; any problem (including a missing file) raises."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CorruptCooldownError(f"cooldown file missing: {target}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise CorruptCooldownError(f"cooldown file unreadable: {target}") from exc
    try:
        state = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorruptCooldownError(f"invalid cooldown JSON in {target}") from exc
    return _validate(state)


def write_cooldown(path: str | Path, state: dict[str, Any]) -> None:
    """Atomically persist validated state (temp file in same directory, fsync, replace)."""
    clean = _validate(state)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(clean, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


@contextmanager
def _exclusive_lock(path: Path):
    """Cross-process exclusive lock on a sidecar file (POSIX flock / Windows msvcrt)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a+b") as handle:
        try:
            import fcntl
        except ImportError:  # Windows
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def extend_cooldown(path: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    """Race-safe 'keep the longest deadline': lock, read, compare, atomically replace.

    Returns the state that is in force afterwards. A corrupt existing file is replaced
    by the new valid state. The whole read-compare-write runs under one exclusive lock.
    """
    clean = _validate(state)
    target = Path(path)
    with _exclusive_lock(target):
        try:
            existing = read_cooldown(target)
        except CorruptCooldownError:
            existing = None
        if existing is not None and existing["until_ms"] >= clean["until_ms"]:
            return existing
        write_cooldown(target, clean)
        return clean
