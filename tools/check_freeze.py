"""Verify the frozen Stage-1 matrix and tool/source manifests."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MATRIX_SHA256 = "330c3570e7eb335caa59b42d24d149b0c5e93164b34fe3e56b6317861e82af78"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(root: Path = ROOT) -> list[str]:
    errors=[]
    matrix=root/"matrix.yaml"
    if not matrix.is_file() or sha256(matrix) != EXPECTED_MATRIX_SHA256:
        errors.append("frozen matrix hash mismatch (mandatory flags and policy are frozen)")
    approval=root/"evidence"/"freeze"/"stage1-reviewer-approval.txt"
    test_file=root/"tests"/"tools"/"test_spec_tooling.py"
    if not approval.is_file():
        errors.append("missing reviewer approval record")
    elif not test_file.is_file():
        errors.append("missing tests/tools/test_spec_tooling.py")
    else:
        record=approval.read_text(encoding="utf-8")
        expected_line=next((line for line in record.splitlines() if line.startswith("SHA-256  tests/tools/test_spec_tooling.py  ")), None)
        if expected_line is None:
            errors.append("missing tooling-test SHA-256 in reviewer approval record")
        else:
            expected=expected_line.rsplit("  ",1)[-1].strip()
            if sha256(test_file) != expected:
                errors.append("hash mismatch: tests/tools/test_spec_tooling.py")
    for manifest in ("stage1-tools-sha256.txt", "stage1-source-sha256.txt", "stage1-reviewer-source-sha256.txt"):
        path=root/"evidence"/"freeze"/manifest
        if not path.is_file():
            errors.append(f"missing freeze manifest: {manifest}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#"): continue
            try: expected, rel=line.split(None,1)
            except ValueError:
                errors.append(f"malformed manifest entry: {manifest}: {line}")
                continue
            target=root/rel
            if not target.is_file() or sha256(target) != expected:
                errors.append(f"hash mismatch: {rel}")
    return errors

def main() -> int:
    errors=check()
    if errors:
        print("FREEZE CHECK FAILED")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print("FREEZE CHECK PASSED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
