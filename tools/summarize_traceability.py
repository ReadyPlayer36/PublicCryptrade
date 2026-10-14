"""Classify check_traceability.py output so the CI summary is actionable.

Classes: expected_red (behavior test not passing while stubs remain),
missing_evidence (live/ci JUnit classes not yet produced), structural
(anything else: missing markers, properties, bindings, citations).
Exit 1 if any structural error exists; otherwise exit 0 (acceptance still
needs check_traceability itself to pass).
"""
import re
import sys
from collections import Counter
from pathlib import Path

EXPECTED_RED = re.compile(r"nodeid (did not pass|failed):")
MISSING_EVIDENCE = re.compile(r"missing (live|ci) JUnit evidence")


def classify(text: str) -> Counter:
    counts: Counter = Counter()
    for line in text.splitlines():
        if not line.startswith(" - "):
            continue
        if EXPECTED_RED.search(line):
            counts["expected_red"] += 1
        elif MISSING_EVIDENCE.search(line):
            counts["missing_evidence"] += 1
        else:
            counts["structural"] += 1
    return counts


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    if not path.is_file():
        print("traceability report missing", file=sys.stderr)
        return 1
    counts = classify(path.read_text(encoding="utf-8"))
    for key in ("expected_red", "missing_evidence", "structural"):
        print(f"{key}={counts.get(key, 0)}")
    return 1 if counts.get("structural", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
