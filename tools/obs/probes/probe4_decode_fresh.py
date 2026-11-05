"""Phase 3 - the same release order fed from a real buffered reader (`readline(MAX_LINE + 2)`), as `decode_pass` does.

Independent re-measurement of the same order with a line buffer the reader allocated itself.
"""
from __future__ import annotations

import io

from tools.obs.probes import probe_common as C
from tools.obs.probes.probe3_decode import decode_one


def read_then_decode(stream: io.BytesIO) -> int:
    raw = stream.readline(C.MAX_LINE + 2)        # the reader's own line buffer (<= MAX_LINE + 2 bytes)
    return decode_one(raw)


def main() -> list[dict]:
    line = C.line_at(C.MAX_LINE)

    def run() -> int:
        return read_then_decode(io.BytesIO(line))

    return [C.measure("phase3_decode_fresh", run, line_bytes=len(line))]


if __name__ == "__main__":
    print(C.canonical(main()))
