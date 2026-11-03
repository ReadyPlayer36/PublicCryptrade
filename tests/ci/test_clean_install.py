"""CI hygiene checks for the documented install contract; no package is installed here."""
import tomllib
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("INSTALL-01")
def test_clean_python312_install():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.12"
    assert (ROOT / "src/trading_app/__init__.py").is_file()
    assert "setuptools.build_meta" == data["build-system"]["build-backend"]

@pytest.mark.requirement("INSTALL-01")
def test_m1_installation_procedure():
    doc = (ROOT / "docs/source/milestone_1.md").read_text().lower()
    assert "pip install" in doc
    assert "python" in doc
