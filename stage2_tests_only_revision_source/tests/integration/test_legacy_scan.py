"""Legacy database scan must report findings without rewriting source data."""
from pathlib import Path
import pytest
from trading_app.data.repository import CandleRepository

@pytest.mark.requirement("LEGACY-01")
def test_legacy_scan_flags_without_repair(tmp_path):
    repository = CandleRepository(tmp_path / "legacy.db")
    report = repository.scan_legacy_data(repair=False)
    assert report.issues
    assert repository.count() == 0
