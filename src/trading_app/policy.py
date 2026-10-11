"""Read policy values from the Stage-1-frozen matrix; do not duplicate constants."""
from functools import lru_cache
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "matrix.yaml"

@lru_cache(maxsize=1)
def frozen_policy() -> dict[str, Any]:
    with MATRIX_PATH.open("r", encoding="utf-8") as stream:
        matrix = yaml.safe_load(stream)
    if matrix.get("schema_version") != "2.9":
        raise RuntimeError("Unexpected frozen specification version")
    return matrix

def retry_policy() -> dict[str, Any]:
    return frozen_policy()["retry"]

def cooldown_policy() -> dict[str, Any]:
    return frozen_policy()["cooldown"]

def finality_policy() -> dict[str, Any]:
    return frozen_policy()["finality"]

def storage_policy() -> dict[str, Any]:
    return frozen_policy()["storage"]
