"""Evidence checker validates commit and artifact hashes, including positive control."""
import hashlib, subprocess, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("EVID-01")
def test_evidence_artifacts_exist_nonempty_commit_and_manifest(tmp_path):
    root=tmp_path/"root"; root.mkdir()
    artifact=root/"evidence"/"sample.txt"; artifact.parent.mkdir(); artifact.write_text("reviewed artifact\n")
    commit="a"*40; (root/"commit.txt").write_text(commit)
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest(); (root/"manifest.txt").write_text(f"{digest} evidence/sample.txt\n")
    matrix=tmp_path/"matrix.yaml"; matrix.write_text("acceptance_rows:\n- artifact_path: evidence/sample.txt\n")
    result=subprocess.run([sys.executable,str(ROOT/"tools/check_evidence.py"),str(matrix),"--root",str(root),"--commit-file",str(root/"commit.txt"),"--manifest",str(root/"manifest.txt")],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
