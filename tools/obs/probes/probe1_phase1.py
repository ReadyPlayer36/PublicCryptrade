"""Phase 1 - request path (section 6.4): chunked scratch accumulation then `bytes(scratch)`.

Normative sequence, bound 8,781,824 B. The body is built BEFORE the measurement starts (A.1): only the request-path
allocations are attributed to this phase.
"""
from __future__ import annotations

from tools.obs.probes import probe_common as C


def sequence(payload: bytes) -> int:
    scratch = bytearray()
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:offset + C.CHUNK_BYTES]      # <= 64 KiB transient, as in 6.4
        scratch += chunk
        offset += len(chunk)
        del chunk
    finished = bytes(scratch)                              # 2 x MAX_BODY peak: the bytearray AND its copy
    assert len(finished) == len(payload)
    return len(finished)


def main() -> list[dict]:
    payload = C.body()
    return [C.measure("phase1_request", lambda: sequence(payload),
                      max_body_bytes=C.MAX_BODY_BYTES, chunk_bytes=C.CHUNK_BYTES)]


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    payload = C.body()
    return C.interposed_pair(C.shim(), lambda: sequence(payload))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
