import pytest
from pathlib import Path
import shutil
import subprocess
import sys
import yaml
from tools.check_freeze import check

ROOT = Path(__file__).resolve().parents[2]

def test_freeze_checker_accepts_approved_matrix():
    assert check(ROOT) == []

def test_freeze_checker_rejects_mandatory_true_flipped(tmp_path):
    shutil.copytree(ROOT, tmp_path / "repo", ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__"))
    clone=tmp_path/"repo"
    matrix_path=clone/"matrix.yaml"
    matrix=yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    row=next(r for r in matrix["acceptance_rows"] if r["mandatory"] is True)
    row["mandatory"]=False
    matrix_path.write_text(yaml.safe_dump(matrix, sort_keys=False), encoding="utf-8")
    errors=check(clone)
    assert any("frozen matrix hash mismatch" in error for error in errors)

@pytest.mark.requirement("FREEZE-01")
def test_freeze_record_hash_manifest():
    """Acceptance scenario bound to frozen matrix row(s): FREEZE-01."""
    record=(ROOT/"evidence/freeze/stage1-reviewer-approval.txt").read_text(encoding="utf-8")
    assert "Stage-1 specification freeze approved" in record
    assert "tests/tools/test_spec_tooling.py" in record
    assert check(ROOT) == []


@pytest.mark.requirement("TOOLS-03")
def test_freeze_rejects_mandatory_downgrade(tmp_path):
    """Acceptance scenario bound to frozen matrix row(s): TOOLS-03."""
    shutil.copytree(ROOT, tmp_path/"repo", ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__"))
    clone=tmp_path/"repo"; matrix_path=clone/"matrix.yaml"
    matrix=yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    next(r for r in matrix["acceptance_rows"] if r["mandatory"] is True)["mandatory"]=False
    matrix_path.write_text(yaml.safe_dump(matrix, sort_keys=False), encoding="utf-8")
    assert any("frozen matrix hash mismatch" in e for e in check(clone))


@pytest.mark.requirement("TOOLS-07")
def test_negative_mandatory_true_to_false(tmp_path):
    """Acceptance scenario bound to frozen matrix row(s): TOOLS-07."""
    shutil.copytree(ROOT, tmp_path/"repo", ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__"))
    clone=tmp_path/"repo"; matrix_path=clone/"matrix.yaml"
    matrix=yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    next(r for r in matrix["acceptance_rows"] if r["mandatory"] is True)["mandatory"]=False
    matrix_path.write_text(yaml.safe_dump(matrix, sort_keys=False), encoding="utf-8")
    assert any("frozen matrix hash mismatch" in e for e in check(clone))


@pytest.mark.requirement("FREEZE-02")
def test_post_freeze_weakening_requires_review(tmp_path):
    """Acceptance scenario bound to frozen matrix row(s): FREEZE-02."""
    shutil.copytree(ROOT, tmp_path/"repo", ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__"))
    clone=tmp_path/"repo"; matrix_path=clone/"matrix.yaml"
    matrix_path.write_text(matrix_path.read_text(encoding="utf-8")+"\n# post-freeze edit\n", encoding="utf-8")
    assert any("frozen matrix hash mismatch" in e for e in check(clone))

@pytest.mark.requirement("FREEZE-03")
def test_freeze_rejects_changed_spec_tooling_test(tmp_path):
    shutil.copytree(ROOT, tmp_path/"repo", ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__"))
    clone=tmp_path/"repo"
    target=clone/"tests/tools/test_spec_tooling.py"
    target.write_text(target.read_text(encoding="utf-8")+"\n# weakened after freeze\n", encoding="utf-8")
    assert any("hash mismatch: tests/tools/test_spec_tooling.py" in e for e in check(clone))
