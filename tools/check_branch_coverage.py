#!/usr/bin/env python3
"""Fail-closed branch-coverage gate using coverage.py JSON output."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("coverage_json",type=Path); ap.add_argument("--matrix",type=Path,default=Path("matrix.yaml")); a=ap.parse_args()
    if not a.coverage_json.is_file(): print("FAIL: coverage JSON missing"); return 1
    try:
        report=json.loads(a.coverage_json.read_text(encoding="utf-8")); policy=yaml.safe_load(a.matrix.read_text(encoding="utf-8"))["coverage"]
        overall=float(report["totals"]["percent_covered_branch"])
        files=report["files"]
        if not files: raise ValueError("coverage JSON has no files")
        modules=[]
        for name,info in files.items():
            if not name.replace("\\","/").startswith("src/trading_app/"): continue
            summary=info["summary"]
            if "percent_covered_branch" not in summary: raise ValueError(f"missing branch percentage for {name}")
            modules.append((name,float(summary["percent_covered_branch"])))
        if not modules: raise ValueError("no src/trading_app modules in coverage JSON")
    except Exception as exc:
        print(f"FAIL: invalid/incomplete coverage report: {exc}"); return 1
    errors=[]
    if overall < float(policy["overall_branch_min"]): errors.append(f"overall branch coverage {overall:.2f}% < {policy['overall_branch_min']}%")
    for name,value in modules:
        if value < float(policy["per_module_branch_min"]): errors.append(f"{name}: branch coverage {value:.2f}% < {policy['per_module_branch_min']}%")
    if errors:
        print(f"FAIL: {len(errors)} coverage threshold violation(s)"); [print(" -",e) for e in errors]; return 1
    print(f"PASS: overall branch coverage {overall:.2f}% and {len(modules)} module(s) meet frozen thresholds")
    return 0
if __name__=="__main__": raise SystemExit(main())
