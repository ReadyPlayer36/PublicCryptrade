"""Repository ignore policy checks."""
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.requirement("DB-07")
def test_sqlite_wal_sidecars_ignored():
    entries=(ROOT/".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/*.db-wal" in entries
    assert "data/*.db-shm" in entries
