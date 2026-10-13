#!/usr/bin/env python3
"""Run patch-based mutation checks; baseline and patch-application errors fail closed."""
from __future__ import annotations
import argparse
import shlex
import subprocess
import sys
from pathlib import Path

def run(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--patch-dir", type=Path, required=True)
    ap.add_argument("--baseline-command", required=True)
    ap.add_argument("--test-command", required=True)
    args=ap.parse_args(); root=args.root.resolve(); patch_dir=args.patch_dir.resolve()
    baseline=shlex.split(args.baseline_command); test=shlex.split(args.test_command)
    rc=run(baseline,root)
    if rc:
        print(f"FAIL: baseline command exited {rc}; no mutants executed")
        return 1
    patches=sorted(patch_dir.glob("*.patch"))
    if not patches:
        print(f"FAIL: no mutation patches found in {patch_dir}")
        return 1
    failures=[]; killed=0
    for patch in patches:
        check=subprocess.run(["git","apply","--check",str(patch)],cwd=root,capture_output=True,text=True)
        if check.returncode:
            failures.append(f"{patch.name}: patch application check failed: {(check.stderr or check.stdout).strip()}")
            continue
        apply=subprocess.run(["git","apply",str(patch)],cwd=root,capture_output=True,text=True)
        if apply.returncode:
            failures.append(f"{patch.name}: patch application failed: {(apply.stderr or apply.stdout).strip()}")
            continue
        try:
            mutant_rc=run(test,root)
            if mutant_rc:
                killed+=1; print(f"KILLED {patch.name} (test exit {mutant_rc})")
            else:
                failures.append(f"{patch.name}: mutant survived")
        finally:
            reverse=subprocess.run(["git","apply","--reverse",str(patch)],cwd=root,capture_output=True,text=True)
            if reverse.returncode:
                failures.append(f"{patch.name}: failed to reverse applied patch: {(reverse.stderr or reverse.stdout).strip()}")
    if failures:
        print(f"FAIL: {len(failures)} mutation issue(s); killed={killed}")
        for item in failures: print(" -",item)
        return 1
    print(f"PASS: {killed}/{len(patches)} mutants killed after baseline passed")
    return 0
if __name__=="__main__": raise SystemExit(main())
