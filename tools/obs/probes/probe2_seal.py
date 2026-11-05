"""Phase 2 - the section 5.1.1 seal: one 48 KiB slice -> b64encode -> write, `del` before the next slice.

Bound 151,552 B (normative order) ; the retained-chunk variant is the BANNED anti-pattern (A.4.4).
"""
from __future__ import annotations

import base64
import hashlib

from tools.obs.probes import probe_common as C


class Sink:
    """Stands in for the staging fd: hashes and drops every write (section 5.1.1 `write_all`)."""

    def __init__(self) -> None:
        self.sha = hashlib.sha256()
        self.bytes_written = 0

    def write(self, data: bytes) -> None:
        self.sha.update(data)
        self.bytes_written += len(data)


def sequence(payload: bytes, tail: bytes, retain: bool) -> int:
    sink = Sink()
    sink.write(b'{"body_b64":"')
    kept: list[bytes] = []
    for offset in range(0, len(payload), C.SEAL_SLICE_BYTES):
        chunk = base64.b64encode(payload[offset:offset + C.SEAL_SLICE_BYTES])
        sink.write(chunk)
        if retain:
            kept.append(chunk)                             # anti-pattern: every chunk stays alive
        else:
            del chunk                                      # normative release BEFORE the next slice
    sink.write(tail)
    return sink.bytes_written


def main() -> list[dict]:
    payload = C.body()
    tail = b'"' + b"," + C.canonical({k: v for k, v in _record_meta().items()})[1:].encode() + b"\n"
    return [
        C.measure("phase2_seal", lambda: sequence(payload, tail, False),
                  slices=-(-len(payload) // C.SEAL_SLICE_BYTES)),
        C.measure("phase2_seal_no_del", lambda: sequence(payload, tail, True)),
    ]


def _record_meta() -> dict:
    return {"seq": 2000, "role": "K5m", "path": "/api/v3/time", "start_ns": 1, "end_ns": 2, "status": 200,
            "error": None, "group_name": None, "group_kind": None, "boundary_ms": None, "headers": []}


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    payload = C.body()
    tail = b'"' + b"," + C.canonical(_record_meta())[1:].encode() + b"\n"
    return C.interposed_pair(C.shim(), lambda: sequence(payload, tail, False))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
