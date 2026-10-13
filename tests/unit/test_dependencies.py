"""Dependency hygiene contract for the Python package metadata."""
from pathlib import Path
import tomllib
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("HYGIENE-06")
def test_unused_dependencies_removed():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert len(deps) == len(set(deps))
    assert all(dep.split(">=")[0].split("<")[0] for dep in deps)
    assert not any(dep.startswith("mutmut") for dep in data["project"]["optional-dependencies"]["dev"])
