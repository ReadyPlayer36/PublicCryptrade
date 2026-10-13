"""Documentation hygiene acceptance tests against checked-in source artifacts."""
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.requirement("ACCEPT-RISK-01")
def test_accepted_risks_document():
    text = (ROOT / "docs/accepted-risks.md").read_text()
    assert "risk" in text.lower()
    assert len(text.strip()) > 200

@pytest.mark.requirement("DOC-01")
def test_binance_docs_comparison_artifact():
    assert (ROOT / "reviewer/project_source_m1.md").is_file()
    assert (ROOT / "reviewer/project_source_m1_2.md").is_file()
    import subprocess, sys
    for source, reviewer in ((ROOT/"docs/source/milestone_1.md", ROOT/"reviewer/project_source_m1.md"), (ROOT/"docs/source/milestone_1_2.md", ROOT/"reviewer/project_source_m1_2.md")):
        result = subprocess.run([sys.executable, str(ROOT/"tools/compare_source_markdown.py"), str(source), str(reviewer)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

@pytest.mark.requirement("R6-02")
def test_conflict_policy_document():
    text = (ROOT / "docs/stage2-test-decisions.md").read_text()
    assert "numeric `Decimal` equality" in text
    assert "never silently drop" in text
