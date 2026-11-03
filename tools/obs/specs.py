"""Request description and the allow-list safety check (public data only)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tools.obs.params import INTERVALS, KLINES_PARAMS, KLINES_PATH, TIME_PATH

_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")


class UnsafeRequest(ValueError):
    """The request is not on the allow-list; it is refused before any socket is opened."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class RequestSpec:
    path: str
    params: tuple[tuple[str, Any], ...] = ()
    role: str = ""                       # S1, S2, K4h, K1h, K15m, K5m, T (sync/resync), K (single), ...
    group_name: str | None = None        # resync, g0, g1, g2, g3, ref, sync, ...
    group_kind: str | None = None        # "5m", "4tf" or None
    boundary_ms: int | None = None


def time_request(**tags: Any) -> RequestSpec:
    return RequestSpec(TIME_PATH, (), **tags)


def klines_request(*, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int, **tags: Any) -> RequestSpec:
    params = (("symbol", symbol), ("interval", interval), ("startTime", start_ms), ("endTime", end_ms), ("limit", limit))
    return RequestSpec(KLINES_PATH, params, **tags)


def validate_spec(spec: RequestSpec) -> None:
    """Allow-list only: anything else (other path, extra/missing parameter, odd type) is refused."""
    if spec.path == TIME_PATH:
        if spec.params:
            raise UnsafeRequest("/time takes no parameters")
        return
    if spec.path != KLINES_PATH:
        raise UnsafeRequest("path is not allowed")
    names = [name for name, _ in spec.params]
    if sorted(names) != sorted(KLINES_PARAMS) or len(set(names)) != len(names):
        raise UnsafeRequest("klines parameters must be exactly symbol, interval, startTime, endTime, limit")
    values = dict(spec.params)
    if not (isinstance(values["symbol"], str) and _SYMBOL.match(values["symbol"])):
        raise UnsafeRequest("invalid symbol")
    if values["interval"] not in INTERVALS:
        raise UnsafeRequest("invalid interval")
    for name in ("startTime", "endTime"):
        if not _is_int(values[name]) or values[name] < 0:
            raise UnsafeRequest(f"invalid {name}")
    if not _is_int(values["limit"]) or not 1 <= values["limit"] <= 1000:
        raise UnsafeRequest("invalid limit")
