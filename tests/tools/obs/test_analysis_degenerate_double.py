"""Meta-test: the analysis golden-vector suite must FAIL against degenerate doubles (constant / always raising)."""
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ("finality_boundary", "bound_k", "lag_formula", "stability", "aggregation", "rejections", "rows_equal")
PLUGINS = {
    "constant": '''
def pytest_configure(config):
    from tools.obs import analysis
    analysis.is_final = lambda *a, **k: True
    analysis.bound_k_ms = lambda *a, **k: 0
    analysis.lag_candidate = lambda *a, **k: None
    analysis.stable_from = lambda *a, **k: 0
    analysis.rows_equal = lambda *a, **k: True
    analysis.validate_row = lambda *a, **k: None
    analysis.analyze_samples = lambda *a, **k: analysis.AnalysisResult(())
    analysis.SampleInput.__post_init__ = lambda self: None
''',
    "always_raises": '''
def pytest_configure(config):
    from tools.obs import analysis
    def boom(*a, **k):
        raise analysis.AnalysisError("degenerate double always raises")
    for name in ("is_final", "bound_k_ms", "lag_candidate", "stable_from", "analyze_samples", "validate_row", "rows_equal"):
        setattr(analysis, name, boom)
    analysis.SampleInput.__post_init__ = boom
''',
}
PREFIX = {"finality_boundary": "test_vector_finality", "bound_k": "test_vector_bound_k", "lag_formula": "test_vector_lag",
          "stability": "test_vector_stability", "aggregation": "test_vector_aggregation", "rejections": "test_vector_rejections", "rows_equal": "test_vector_rows_equal"}


@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("kind", sorted(PLUGINS))
def test_analysis_vector_suite_fails_against_degenerate_double(tmp_path, kind):
    (tmp_path / "degenerate_plugin.py").write_text(PLUGINS[kind], encoding="utf-8")
    junit = tmp_path / "out.xml"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(tmp_path), env.get("PYTHONPATH", "")])
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "degenerate_plugin", "-p", "no:cacheprovider", f"--junitxml={junit}",
           "tests/tools/obs/test_analysis.py"]
    result = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode != 0, "analysis suite passed against a degenerate double"
    assert junit.is_file(), result.stdout + result.stderr
    cases = list(ET.parse(junit).getroot().iter("testcase"))
    assert cases
    bad = {c.attrib["name"] for c in cases if c.find("failure") is not None or c.find("error") is not None}
    for family in FAMILIES:
        members = [c.attrib["name"] for c in cases if c.attrib["name"].startswith(PREFIX[family])]
        assert members, family
        assert bad.intersection(members), f"{kind}: no {family} vector test failed"
    if kind == "always_raises":
        passed = [c.attrib["name"] for c in cases if c.attrib["name"].startswith("test_vector_")
                  and c.find("failure") is None and c.find("error") is None]
        assert not passed, passed
