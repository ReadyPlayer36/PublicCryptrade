"""Shared harness for the Appendix A memory protocol. Deterministic, stdlib only, no network."""
from __future__ import annotations

import base64
import json
import tracemalloc

# Section 12 constants - the probes never read these from a mutable config.
MAX_BODY_BYTES = 4 * 1024 * 1024
FRAMING_ALLOWANCE_BYTES = 512
MAX_LINE = 4 * ((MAX_BODY_BYTES + 2) // 3) + FRAMING_ALLOWANCE_BYTES  # 5,592,920
CHUNK_BYTES = 65_536
SEAL_SLICE_BYTES = 49_152  # 3 x 16,384: base64-aligned, no mid-line padding
SESSION_BODY_BUDGET_BYTES = 52_428_800
HTTP_HEADROOM = 262_144
PAD_LIMIT = 4_096

BOUNDS = {
    "phase1_request": 8_781_824,
    "phase2_seal": 151_552,
    "phase2_seal_no_del": 151_552,
    "phase3_decode": 11_202_224,
    "phase3_decode_fresh": 11_202_224,
    "phase3_structure": 11_202_224,
    "native_headroom": HTTP_HEADROOM,
}

RECORD_KEYS = frozenset({
    "seq", "role", "path", "start_ns", "end_ns", "status", "error", "group_name", "group_kind",
    "boundary_ms", "body_b64", "headers",
})


def canonical(obj: object) -> str:
    """Step-1's serializer (runstore._canonical): sort_keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def body(size: int = MAX_BODY_BYTES) -> bytes:
    """Deterministic worst-case body: every byte value, repeated, exactly `size` bytes."""
    pattern = bytes(range(251))
    return (pattern * (size // len(pattern) + 1))[:size]


def record_line(body_bytes: bytes, pad: int = 0) -> bytes:
    """One schema-valid record line (12 keys, canonical order); `pad` extends the `error` field by `pad` bytes."""
    return canonical({
        "seq": 2000,
        "role": "K5m",
        "path": "/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1000&startTime=0&endTime=1",
        "start_ns": 1_700_000_000_000_000_000,
        "end_ns": 1_700_000_000_017_000_000,
        "status": 200,
        "error": "x" * pad,
        "group_name": "resync",
        "group_kind": "5m",
        "boundary_ms": 180000,
        "body_b64": base64.b64encode(body_bytes).decode("ascii"),
        "headers": [["content-type", "application/json"], ["x-mbx-used-weight-1m", "1234"]],
    }).encode("utf-8")


def line_at(content_bytes: int) -> bytes:
    """A valid record line whose UTF-8 content is EXACTLY `content_bytes` long (<= MAX_LINE)."""
    base = len(record_line(b""))
    if content_bytes < base:
        raise SystemExit(f"{content_bytes} is below the empty-body framing ({base} B)")
    target_b64 = content_bytes - base
    length = min(MAX_BODY_BYTES, 3 * (target_b64 // 4))
    line = record_line(body(length), 0)
    pad = content_bytes - len(line)
    if not 0 <= pad <= PAD_LIMIT:
        raise SystemExit(f"cannot build a {content_bytes}-byte line (pad {pad})")
    line = record_line(body(length), pad)
    assert len(line) == content_bytes, (len(line), content_bytes)
    return line


def shim():
    """ctypes handle on alloc_peak.so's getters; the caller must have LD_PRELOADed the shim (A.5.4/A.5.7)."""
    import ctypes

    lib = ctypes.CDLL(None)
    lib.alloc_peak_reset.restype = None
    lib.alloc_peak_peak.restype = ctypes.c_size_t
    lib.alloc_peak_map_peak.restype = ctypes.c_size_t
    return lib


def interposed_pair(lib, fn) -> dict[str, int]:
    """Reset the shim, run ONE measured region, and report both channels: malloc bytes and direct anon mmap bytes."""
    lib.alloc_peak_reset()
    fn()
    return {"peak": int(lib.alloc_peak_peak()), "map_peak": int(lib.alloc_peak_map_peak())}


def measure(name: str, fn, **detail) -> dict:
    """Run `fn` under tracemalloc; report the peak. INPUTS MUST BE BUILT OUTSIDE `fn` (A.1)."""
    tracemalloc.start()
    try:
        value = fn()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    bound = BOUNDS.get(name)
    return {
        "probe": name,
        "peak": peak,
        "bound": bound,
        "pass": None if bound is None else peak <= bound,
        "detail": {"value": value if isinstance(value, int) else None, **detail},
    }
