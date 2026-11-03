"""Meta-test: client/validator acceptance tests must reject degenerate doubles."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def test_client_and_validator_tests_fail_with_degenerate_double(tmp_path):
    plugin = tmp_path / "degenerate_plugin.py"
    plugin.write_text('''
def pytest_configure(config):
    from datetime import datetime
    from trading_app.data import binance_client, finality, validator
    def always_client_error(self, *args, **kwargs):
        raise binance_client.BinanceClientError("degenerate double always raises")
    binance_client.BinanceMarketDataClient.get_server_time = always_client_error
    binance_client.BinanceMarketDataClient.get_historical_klines = always_client_error
    finality.is_final = lambda *a, **k: True
    finality.effective_end_ms = lambda *a, **k: 0
    validator.assert_valid_klines = lambda *a, **k: None
    validator.validate_klines = lambda *a, **k: []
    validator.timeframe_to_ms = lambda *a, **k: 0
    validator.utc_datetime_from_ms = lambda *a, **k: datetime(2024, 1, 1)
''', encoding="utf-8")
    junit = tmp_path / "degenerate.xml"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src"), str(tmp_path), env.get("PYTHONPATH", "")])
    command = [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}", "-p", "degenerate_plugin",
               "tests/unit/test_binance_client.py", "tests/unit/test_finality.py",
               "tests/integration/test_finality.py", "tests/unit/test_validator.py"]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=90)
    assert result.returncode != 0, "client/validator acceptance tests passed against degenerate doubles"
    assert junit.is_file(), result.stdout + result.stderr
    import xml.etree.ElementTree as ET
    cases = list(ET.parse(junit).getroot().iter("testcase"))
    assert cases, "degenerate run collected no tests"
    passed = [case.attrib.get("name") for case in cases if case.find("failure") is None and case.find("error") is None and case.find("skipped") is None]
    assert not passed, f"tests passed against degenerate doubles: {passed}"
