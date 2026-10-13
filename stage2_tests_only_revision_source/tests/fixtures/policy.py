"""Test-only reader for the frozen acceptance matrix; production must not import it."""
from functools import lru_cache
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "matrix.yaml"

@lru_cache(maxsize=1)
def frozen_policy() -> dict[str, Any]:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    if matrix.get("schema_version") != "2.9":
        raise AssertionError("unexpected frozen specification version")
    return matrix

def retry_policy(): return frozen_policy()["retry"]
def cooldown_policy(): return frozen_policy()["cooldown"]
def finality_policy(): return frozen_policy()["finality"]
def storage_policy(): return frozen_policy()["storage"]
