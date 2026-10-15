"""Tripwire: no trading code, order submission or forbidden HTTP calls in src/ and scripts/."""
from pathlib import Path

import pytest

from tools.tripwire import FORBIDDEN_HTTP_METHODS, scan
from trading_app.data.binance_client import ALLOWED_PATHS, BinanceMarketDataClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.requirement("M1-16")
def test_no_trading_code_or_order_submission():
    report = scan(ROOT)
    assert report.findings == ()
    public = [n for n in dir(BinanceMarketDataClient) if not n.startswith("_")]
    assert not [n for n in public if any(w in n.lower() for w in ("order", "trade", "withdraw", "margin", "leverage", "buy", "sell"))]
    assert ALLOWED_PATHS == ("/api/v3/time", "/api/v3/klines")


@pytest.mark.requirement("TRIP-01")
def test_tripwire_forbidden_http_calls(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "bad_post.py").write_text("import httpx\nhttpx.Client().post('https://x', data={})\n")
    (tmp_path / "src" / "bad_endpoint.py").write_text("URL = 'https://api.binance.com/api/v3/order'\n")
    (tmp_path / "scripts" / "bad_header.py").write_text("H = {'X-MBX-APIKEY': 'k'}\n")
    (tmp_path / "scripts" / "bad_request.py").write_text("client.request('DELETE', u)\n")
    (tmp_path / "src" / "good.py").write_text("client.get('https://data-api.binance.vision/api/v3/time')\n")
    report = scan(tmp_path)
    found = {(f.path, f.kind) for f in report.findings}
    assert ("src/bad_post.py", "http-method") in found
    assert ("src/bad_endpoint.py", "forbidden-string") in found
    assert ("scripts/bad_header.py", "forbidden-string") in found
    assert ("scripts/bad_request.py", "http-method") in found
    assert not [f for f in report.findings if f.path == "src/good.py"]
    assert {"post", "put", "delete", "patch", "request"} <= FORBIDDEN_HTTP_METHODS


@pytest.mark.requirement("TRIP-02")
def test_tripwire_scanned_file_count_and_tests_exemption(tmp_path, capsys):
    from tools.tripwire import main
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("src/a.py", "src/b.py", "scripts/c.py"):
        (tmp_path / name).write_text("x = 1\n")
    (tmp_path / "tests" / "negative.py").write_text("U = '/api/v3/order'\nc.post(U)\n")
    assert main(["tripwire", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "scanned 3 file(s)" in out and "EXEMPT: tests/" in out
    real = scan(ROOT)
    assert len(real.scanned_files) == len([p for d in ("src", "scripts") for p in (ROOT / d).rglob("*.py")])
    assert len(real.scanned_files) >= 10
