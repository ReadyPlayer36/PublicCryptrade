"""Supported Python baseline policy."""
import tomllib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.requirement("CI-01")
@pytest.mark.requirement("PY-01")
def test_python_version_policy_documented():
    requirement=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    assert requirement.startswith(">=3.12")
    assert "<3.13" not in requirement
