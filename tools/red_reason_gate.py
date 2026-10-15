#!/usr/bin/env python3
"""Fail unless every red test is a production stub and every green test is allowlisted.

The allowlist is intentionally limited to repository tooling, CI evidence/hygiene,
source-boundary hygiene, and frozen-matrix reader checks. It is not a behavioral bypass.
"""
from __future__ import annotations
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ALLOWED_PREFIXES = ("tests/tools/", "tests/ci/")
ALLOWED_EXACT = {
    "tests/unit/test_scope.py::test_milestone_one_scope_boundary",
    "tests/unit/test_gitignore.py::test_sqlite_wal_sidecars_ignored",
    "tests/unit/test_python_policy.py::test_python_version_policy_documented",
    "tests/unit/test_project_layout.py::test_python312_project_structure",
    "tests/unit/test_dependencies.py::test_unused_dependencies_removed",
    "tests/integration/test_cli.py::test_script_wrapper_is_thin_and_runnable",
    "tests/mutation/test_mutation_runner.py::test_baseline_and_patch_failure_policy",
    "tests/mutation/test_required_mutants.py::test_each_mutant_has_killer",
    "tests/mutation/test_required_mutants.py::test_required_mutant_set",
    "tests/security/test_network_policy.py::test_no_api_keys",
    "tests/security/test_network_policy.py::test_no_private_endpoints",
    "tests/security/test_network_policy.py::test_public_spot_market_data_only",
    "tests/live/test_run_evidence.py::test_live_run_evidence_manifest",
    "tests/observations/test_obs01_boundaries.py::test_end_and_start_boundary_semantics",
    "tests/observations/test_obs03_gate.py::test_observation_gate_before_live_acceptance",
}
STUB_RE = re.compile(r"NotImplementedError")
SRC_FRAME_RE = re.compile(r"(?:src[/\\]trading_app[/\\]|trading_app[/\\]).*\.py")

def nodeid(case: ET.Element) -> str:
    cls = case.attrib.get("classname", "")
    name = case.attrib.get("name", "")
    if cls.startswith("tests."):
        cls = cls.replace(".", "/") + ".py"
    elif cls.startswith("tests/") and not cls.endswith(".py"):
        cls += ".py"
    elif cls and not cls.startswith("tests/"):
        cls = "tests/" + cls.replace(".", "/") + ".py"
    return f"{cls}::{name}"

def allowlisted(n: str) -> bool:
    return n in ALLOWED_EXACT or n.startswith(ALLOWED_PREFIXES)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("junit", type=Path)
    ap.add_argument("--pytest-exit-code", type=int, required=True)
    ap.add_argument("--implementation-stage", action="store_true",
                    help="allow passing behavioral tests (code is being implemented); "
                         "every failure must still be a NotImplementedError from an unimplemented src stub")
    args = ap.parse_args()
    if not args.junit.is_file():
        print(f"RED-REASON GATE FAIL: JUnit file missing: {args.junit}")
        return 1
    try:
        root = ET.parse(args.junit).getroot()
    except Exception as exc:
        print(f"RED-REASON GATE FAIL: invalid JUnit XML: {exc}")
        return 1
    errors: list[str] = []
    cases = list(root.iter("testcase"))
    if not cases:
        errors.append("JUnit contains no testcases")
    # Collection errors are never an acceptable expected-red result.
    for el in root.iter():
        if el.tag == "error":
            errors.append(f"collection/suite error: {el.attrib.get('message', el.text or 'unknown error')}")
    expected_red = 0
    for case in cases:
        n = nodeid(case)
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if skipped is not None:
            errors.append(f"skip is not an expected-red result: {n}")
            continue
        if failure is not None or error is not None:
            blob = "\n".join((failure.text or "", failure.attrib.get("message", ""), error.text or "" if error is not None else "", error.attrib.get("message", "") if error is not None else ""))
            if error is not None:
                errors.append(f"error is not an expected-red result: {n}")
            elif STUB_RE.search(blob) and SRC_FRAME_RE.search(blob):
                expected_red += 1
            else:
                errors.append(f"failure is not a production NotImplementedError stub: {n}")
        elif not args.implementation_stage and not allowlisted(n):
            errors.append(f"behavioral test passed against stubs and is not allowlisted: {n}")
    if args.pytest_exit_code not in (0, 1):
        errors.append(f"pytest exit code {args.pytest_exit_code} indicates collection/internal failure")
    if expected_red == 0 and not args.implementation_stage:
        errors.append("no expected production-stub failures were observed")
    if errors:
        print(f"RED-REASON GATE FAIL: {len(errors)} issue(s); expected production-stub failures={expected_red}")
        for e in errors: print(" -", e)
        return 1
    mode = "implementation stage: passes allowed" if args.implementation_stage else "all passes are allowlisted"
    print(f"RED-REASON GATE PASS: {expected_red} failure(s) are NotImplementedError from src/trading_app; {mode}; pytest exit={args.pytest_exit_code}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
