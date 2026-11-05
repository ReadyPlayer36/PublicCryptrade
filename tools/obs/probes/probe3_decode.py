"""Phase 3 - the section 5.1.2 `decode_pass` order on ONE line at MAX_LINE.

Normative release order: decode -> del line bytes -> json.loads -> del text -> pop body_b64 -> encode ascii ->
del the str -> b64decode(bytes) -> del raw. Bound 11,202,224 B.
"""
from __future__ import annotations

import base64
import json

from tools.obs.probes import probe_common as C


def decode_one(line: bytes) -> int:
    text = line.decode("utf-8")
    del line                                     # release the bytes BEFORE parsing
    obj = json.loads(text)
    del text                                     # release the text BEFORE touching the value
    if not isinstance(obj, dict) or set(obj) != C.RECORD_KEYS:
        raise SystemExit("fixture is not a schema-valid record line")
    value = obj.pop("body_b64")                  # the <= 5,592,408 B str leaves the dict FIRST
    raw = value.encode("ascii")
    del value                                    # release the str BEFORE decoding
    body = base64.b64decode(raw, validate=True)
    del raw                                      # BYTES in: b64decode(str) would re-encode the whole string
    return len(body) + len(obj)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)
    return [C.measure("phase3_decode", lambda: decode_one(line), line_bytes=len(line))]


def interposed_pair() -> dict[str, int]:
    """Both interposed channels for this phase: malloc bytes and direct anonymous mmap bytes (A.5.4/A.5.7)."""
    line = C.line_at(C.MAX_LINE)
    return C.interposed_pair(C.shim(), lambda: decode_one(line))


def interposed() -> int:
    return interposed_pair()["peak"]


if __name__ == "__main__":
    print(C.canonical(main()))
