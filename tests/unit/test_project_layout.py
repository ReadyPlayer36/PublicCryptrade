"""Repository layout requirements; independent of production implementation."""
import tomllib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.requirement("M1-01")
def test_python312_project_structure():
    pyproject=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"] == ">=3.12"
    assert (ROOT/"src/trading_app").is_dir()
    assert (ROOT/"tests/unit").is_dir()
    assert (ROOT/".github/workflows/ci.yml").is_file()
