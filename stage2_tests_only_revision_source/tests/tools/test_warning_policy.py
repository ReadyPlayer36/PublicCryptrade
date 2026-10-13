"""Warnings are promoted to errors in the pytest configuration."""
from pathlib import Path
import tomllib
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.requirement("HYGIENE-05")
def test_filterwarnings_error_and_no_coverage_warning():
    config=tomllib.loads((ROOT/"pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert "error" in config["filterwarnings"]
    assert "pytest-cov" in str(tomllib.loads((ROOT/"pyproject.toml").read_text())["project"]["optional-dependencies"]["dev"])
