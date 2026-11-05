"""Phase 3 - the section 5.1.2 `scan_structure` pass: parse + key check + DISCARD, no body decode.

Bound 11,202,224 B. Retaining the dict (or the line) is the banned pattern A.4.4.
"""
from __future__ import annotations

import json

from tools.obs.probes import probe_common as C


def scan(line: bytes) -> int:
    text = line.decode("utf-8")
    del line
    obj = json.loads(text)
    del text
    ok = isinstance(obj, dict) and set(obj) == C.RECORD_KEYS
    del obj                                      # DISCARD: the structure pass retains nothing
    return int(ok)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)
    return [C.measure("phase3_structure", lambda: scan(line), line_bytes=len(line))]


if __name__ == "__main__":
    print(C.canonical(main()))
