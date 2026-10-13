"""Mutation runner must baseline first and treat patch-application failure as failure."""
from pathlib import Path
import subprocess, sys
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("MUT-01")
def test_baseline_and_patch_failure_policy(tmp_path):
    repo=tmp_path/"repo"; repo.mkdir()
    subprocess.run(["git","init","-q"],cwd=repo,check=True)
    (repo/"value.txt").write_text("baseline\n")
    subprocess.run(["git","add","value.txt"],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Test","-c","user.email=test@example.invalid","commit","-qm","baseline"],cwd=repo,check=True)
    patches=tmp_path/"patches"; patches.mkdir(); (patches/"bad.patch").write_text("not a valid git patch\n")
    result=subprocess.run([sys.executable,str(ROOT/"tools/run_mutations.py"),"--root",str(repo),"--patch-dir",str(patches),"--baseline-command",f'"{sys.executable}" -c "pass"',"--test-command",f'"{sys.executable}" -c "pass"'],capture_output=True,text=True)
    assert result.returncode != 0
    assert "patch application" in result.stdout.lower()
