"""Safety tripwire: scan src/ and scripts/ for HTTP write calls and forbidden endpoint strings.

tests/ is explicitly exempt (it holds negative-test fixtures); the exemption and the exact
number of scanned files are printed. Exit code 1 if any finding exists.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SCANNED_DIRS = ("src", "scripts")
EXEMPT_DIRS = ("tests",)
FORBIDDEN_HTTP_METHODS = {"post", "put", "delete", "patch", "request", "send", "stream"}
FORBIDDEN_STRINGS = (
    "/api/v3/order", "/api/v3/account", "/api/v3/myTrades", "/sapi/", "/fapi/", "/dapi/", "/eapi/", "/wapi/",
    "userDataStream", "listenKey", "withdraw", "newOrder", "X-MBX-APIKEY", "apiKey", "api_key", "api-key",
    "signature", "leverage", "marginType", "testnet", "demo-api", "api1.binance", "api2.binance", "api3.binance",
    "api4.binance", "api-gcp.binance",
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str


@dataclass(frozen=True)
class TripwireReport:
    scanned_files: tuple[str, ...]
    findings: tuple[Finding, ...]
    exempt: tuple[str, ...]

    def summary(self) -> str:
        return (f"TRIPWIRE: scanned {len(self.scanned_files)} file(s) under {', '.join(SCANNED_DIRS)}; "
                f"EXEMPT: {', '.join(d + '/' for d in self.exempt)} (negative-test fixtures); "
                f"findings={len(self.findings)}")


def _scan_file(path: Path, rel: str) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_HTTP_METHODS:
            findings.append(Finding(rel, node.lineno, "http-method", f".{node.func.attr}(...)"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            for token in FORBIDDEN_STRINGS:
                if token.lower() in lowered:
                    findings.append(Finding(rel, node.lineno, "forbidden-string", token))
    return findings


def scan(root: str | Path) -> TripwireReport:
    base = Path(root)
    files: list[str] = []
    findings: list[Finding] = []
    for directory in SCANNED_DIRS:
        for path in sorted((base / directory).rglob("*.py")) if (base / directory).is_dir() else []:
            rel = path.relative_to(base).as_posix()
            files.append(rel)
            findings.extend(_scan_file(path, rel))
    return TripwireReport(tuple(files), tuple(findings), EXEMPT_DIRS)


def main(argv: list[str]) -> int:
    report = scan(argv[1] if len(argv) > 1 else ".")
    print(report.summary())
    for f in report.findings:
        print(f" - {f.path}:{f.line} [{f.kind}] {f.detail}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
