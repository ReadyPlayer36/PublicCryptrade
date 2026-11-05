"""Probe 5 - byte equality: the section 5.1.1 streaming writer vs `_lines([record_to_json(r) ...])` (G-V14-02).

1,020 deterministic records, one of them at MAX_BODY_BYTES. Equality is asserted on the SHA-256 of the whole stream.
"""
from __future__ import annotations

import base64
import hashlib

from tools.obs.probes import probe_common as C


def record(index: int) -> dict:
    size = C.MAX_BODY_BYTES if index == 1_019 else (index * 37) % 4_096
    return {"seq": index + 1, "role": "S1", "path": "/api/v3/time", "start_ns": index, "end_ns": index + 1,
            "status": 200, "error": None, "group_name": None, "group_kind": None, "boundary_ms": None,
            "body": C.body(size), "headers": []}


def reference_line(obj: dict) -> bytes:
    """Step-1 `record_to_json` + `_lines`: the byte sequence the writer must reproduce exactly."""
    return C.canonical({
        "seq": obj["seq"], "role": obj["role"], "path": obj["path"], "start_ns": obj["start_ns"],
        "end_ns": obj["end_ns"], "status": obj["status"], "error": obj["error"], "group_name": obj["group_name"],
        "group_kind": obj["group_kind"], "boundary_ms": obj["boundary_ms"], "headers": obj["headers"],
        "body_b64": base64.b64encode(obj["body"]).decode("ascii"),
    }).encode("utf-8") + b"\n"


def streamed_line(obj: dict) -> bytes:
    """Section 5.1.1 framing: `{` + "body_b64" value + `,` + the other 11 keys in canonical order + newline."""
    meta = {k: v for k, v in obj.items() if k not in ("body_b64", "body")}
    low = {k: v for k, v in meta.items() if k < "body_b64"}     # EMPTY under the frozen 12-key set
    high = {k: v for k, v in meta.items() if k > "body_b64"}    # the other 11 keys
    out = bytearray(b"{")
    if low:
        out += C.canonical(low)[1:-1].encode() + b","
    out += b'"body_b64":"'
    for offset in range(0, len(obj["body"]), C.SEAL_SLICE_BYTES):
        out += base64.b64encode(obj["body"][offset:offset + C.SEAL_SLICE_BYTES])
    out += b'"' + (b"," + C.canonical(high)[1:].encode() if high else b"}")
    out += b"\n"
    return bytes(out)


def main() -> list[dict]:
    records = [record(i) for i in range(1_020)]
    reference = b"".join(reference_line(r) for r in records)
    streamed = b"".join(streamed_line(r) for r in records)
    equal = hashlib.sha256(reference).hexdigest() == hashlib.sha256(streamed).hexdigest()
    return [{"probe": "byte_equality", "peak": 0, "bound": None, "pass": equal,
             "detail": {"bytes": len(reference), "records": len(records),
                        "max_body_bytes": C.MAX_BODY_BYTES}}]


if __name__ == "__main__":
    print(C.canonical(main()))
