"""Static safety scan of the OBS harness: public read-only data only, monotonic clock only, isolated from production code."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HARNESS = sorted((ROOT / "tools" / "obs").glob("*.py"))
FORBIDDEN = re.compile(r"api[-_ ]?key|secret|signature|recvwindow|neworder|/api/v3/order|withdraw|futures|margin|leverage|testnet|"
                       r"listenkey|authorization|cookie|api\.binance\.com|api[1-4]\.binance|api-gcp|\.env|getenv|os\.environ|subprocess", re.IGNORECASE)


def test_harness_files_exist():
    assert {p.name for p in HARNESS} >= {"admission.py", "audit.py", "clock.py", "estimator.py", "pacer.py", "params.py", "specs.py",
                                         "transport.py", "watchdog.py"}


@pytest.mark.parametrize("path", HARNESS, ids=lambda p: p.name)
def test_no_credentials_orders_private_endpoints_or_other_hosts(path):
    hits = [m.group(0) for m in FORBIDDEN.finditer(path.read_text())]
    assert hits == []


@pytest.mark.parametrize("path", HARNESS, ids=lambda p: p.name)
def test_wall_clock_is_never_read(path):
    text = path.read_text()
    assert not re.search(r"time\.time\(|time_ns\(|datetime|utcnow|perf_counter|process_time", text)


def test_only_the_official_host_and_two_paths_are_named():
    text = "\n".join(p.read_text() for p in HARNESS)
    assert set(re.findall(r"[a-z0-9.-]+\.binance\.[a-z]+", text)) == {"data-api.binance.vision"}
    assert set(re.findall(r'"(/api/v3/[A-Za-z]+)"', text)) == {"/api/v3/time", "/api/v3/klines"}


def test_http_methods_are_get_only():
    text = "\n".join(p.read_text() for p in HARNESS)
    assert not re.search(r"\.(post|put|delete|patch)\(", text, re.IGNORECASE) and not re.search(r'"(POST|PUT|DELETE|PATCH)"', text)
    assert text.count('"GET"') == 1


def test_production_code_does_not_depend_on_the_harness():
    for path in (ROOT / "src").rglob("*.py"):
        assert "tools.obs" not in path.read_text()
