"""CLI contract: documented exit codes, clean one-line errors (no tracebacks, no leaked values), --strict-end, --verify."""
import pytest

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
from tests.fixtures.service_env import I, NOW, S0
from trading_app.cli import EXIT_FAILURE, EXIT_INTERNAL, EXIT_OK, EXIT_STRICT_END, EXIT_USAGE, EXIT_VERIFY, main
from trading_app.config import Settings
from trading_app.data.repository import CandleRepository, create_engine_from_url

START, END = "2026-01-05T00:00:00Z", "2026-01-05T01:00:00Z"          # 12 five-minute candles
S = 1767571200000                                                       # 2026-01-05T00:00:00Z
assert S == S0
ARGS = ["--symbol", "BTCUSDT", "--timeframe", "5m", "--start", START, "--end", END]


def cfg(tmp_path, **overrides):
    values = dict(database_url=f"sqlite:///{tmp_path / 'cli.db'}", cooldown_path=str(tmp_path / "cooldown.json"), finality_lag_ms=0)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def fake(n=12, server_ms=S + 30 * I):
    return FakeHttpClient([FakeResponse(payload={"serverTime": server_ms}), FakeResponse(payload=make_rows(S, n))])


def run(args, tmp_path, http=None, **settings):
    return main(args, settings=cfg(tmp_path, **settings), http_client=http, sleep=lambda _: None, jitter=lambda: 0.0, now_ms=lambda: NOW)


def repo(tmp_path):
    return CandleRepository(create_engine_from_url(f"sqlite:///{tmp_path / 'cli.db'}"))


@pytest.mark.requirement("CLI-01")
def test_download_script_with_mocked_public_client(tmp_path, capsys):
    http = fake()
    assert run(ARGS, tmp_path, http) == EXIT_OK
    out = capsys.readouterr()
    assert out.out.splitlines() == ["New candles inserted: 12", "Total stored candles: 12"] and out.err == ""
    assert [c[0] for c in http.calls] == ["https://data-api.binance.vision/api/v3/time", "https://data-api.binance.vision/api/v3/klines"]
    assert http.calls[1][1]["startTime"] == S and http.calls[1][1]["endTime"] == S + 12 * I - 1
    assert repo(tmp_path).count(symbol="BTCUSDT", timeframe="5m") == 12
    # a rerun is idempotent
    assert run(ARGS, tmp_path, fake()) == EXIT_OK
    assert capsys.readouterr().out.splitlines() == ["New candles inserted: 0", "Total stored candles: 12"]


@pytest.mark.requirement("CLI-02")
def test_cli_exit_codes_and_clean_expected_errors(tmp_path, capsys, monkeypatch):
    def failure(args, code, text, http=None, **settings):
        assert run(args, tmp_path, http, **settings) == code
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip().splitlines()[-1] == text and "Traceback" not in captured.err
        return captured.err

    # usage errors -> 2 (argparse path raises SystemExit(2) with a fixed message that never echoes the input)
    with pytest.raises(SystemExit) as error:
        main(["--not-a-real-option"])
    assert error.value.code == 2
    assert "not-a-real-option" not in capsys.readouterr().err
    failure(["--symbol", "BTCUSDT"], EXIT_USAGE, "error: --symbol, --timeframe, --start and --end are required")
    failure(["--verify", "--symbol", "BTCUSDT"], EXIT_USAGE, "error: --verify takes no download options")
    with pytest.raises(SystemExit) as error:
        main(["--symbol", "BTCUSDT", "--timeframe", "5m", "--start", "2026-01-05T00:00:00", "--end", END])     # naive datetime
    assert error.value.code == 2
    capsys.readouterr()
    # invalid configuration -> 2, value not echoed
    monkeypatch.setenv("BINANCE_BASE_URL", "https://evil.example.test")
    assert main(ARGS) == EXIT_USAGE
    assert capsys.readouterr().err.strip() == "error: invalid configuration"
    monkeypatch.delenv("BINANCE_BASE_URL")
    # expected operational failures -> 1, one fixed line
    failure(["--symbol", "DOGEUSDT", "--timeframe", "5m", "--start", START, "--end", END], EXIT_FAILURE, "error: invalid input rejected", http=fake())
    failure(ARGS, EXIT_FAILURE, "error: binance request failed (finality lag not configured)", http=fake(), finality_lag_ms=None)
    failure(ARGS, EXIT_FAILURE, "error: binance request failed (HTTP 400)",
            http=FakeHttpClient([FakeResponse(status_code=400, payload={"msg": "secret-body-value"})]))
    # an unexpected bug -> 70, no traceback and no leaked message
    class Boom:
        def get(self, url, *, params=None):
            raise ZeroDivisionError("secret-token-123")
    err = failure(ARGS, EXIT_INTERNAL, "error: unexpected internal error", http=Boom())
    assert "secret-token-123" not in err


@pytest.mark.requirement("CLI-02")
def test_strict_end_fails_without_storing_and_default_clamps(tmp_path, capsys):
    server = S + 6 * I + 1234                                           # only 6 candles are final; 12 were requested
    assert run(ARGS, tmp_path, fake(6, server)) == EXIT_OK                # default: clamp
    assert capsys.readouterr().out.splitlines() == ["New candles inserted: 6", "Total stored candles: 6"]
    assert [f["effective_end_ms"] for f in repo(tmp_path).get_fetches()] == [S + 6 * I]
    assert repo(tmp_path).get_fetches()[0]["requested_end_ms"] == S + 12 * I

    other = tmp_path / "strict"
    other.mkdir()
    assert run(ARGS + ["--strict-end"], other, fake(6, server)) == EXIT_STRICT_END
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.strip() == "error: strict-end: requested end is later than the final-data boundary"
    strict_repo = CandleRepository(create_engine_from_url(f"sqlite:///{other / 'cli.db'}"))
    assert strict_repo.count() == 0                                       # nothing stored
    fetches = strict_repo.get_fetches()
    assert [(f["status"], f["error_class"], f["row_count"]) for f in fetches] == [("failed", "StrictEndError", 0)]

    third = tmp_path / "strict_ok"
    third.mkdir()
    assert run(ARGS + ["--strict-end"], third, fake(12)) == EXIT_OK          # end already final: strict-end is satisfied
    assert capsys.readouterr().out.splitlines()[0] == "New candles inserted: 12"


@pytest.mark.requirement("CLI-02")
def test_verify_mode_exit_codes_and_read_only(tmp_path, capsys):
    assert run(["--verify"], tmp_path) == EXIT_FAILURE                    # no database yet: clean failure
    assert "Traceback" not in capsys.readouterr().err
    assert run(ARGS, tmp_path, fake()) == EXIT_OK
    capsys.readouterr()
    assert run(["--verify"], tmp_path) == EXIT_OK
    assert capsys.readouterr().out.splitlines() == ["BTCUSDT 5m: 12 candles", "Verification: OK"]
    import sqlite3
    connection = sqlite3.connect(tmp_path / "cli.db")
    connection.execute("UPDATE candles SET high_price = '1' WHERE open_time_ms = ?", (S + 3 * I,))
    connection.execute("DELETE FROM candles WHERE open_time_ms = ?", (S + 5 * I,))
    connection.commit()
    connection.close()
    assert run(["--verify"], tmp_path) == EXIT_VERIFY
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "BTCUSDT 5m: 11 candles" and "INVALID_OHLC: 1" in out and "SERIES_GAP: 1" in out
    assert out[-1] == "Verification: PROBLEMS FOUND (nothing was changed)"
    assert repo(tmp_path).count() == 11                                    # verify never repairs


@pytest.mark.requirement("HYGIENE-01")
def test_script_wrapper_is_thin_and_runnable():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "scripts/download_candles.py").read_text()
    assert "from trading_app.cli import main" in source
    assert "raise SystemExit(main())" in source
    assert "BinanceMarketDataClient" not in source


@pytest.mark.requirement("CLI-02")
def test_invalid_iso_datetime_is_a_clean_usage_error(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--symbol", "BTCUSDT", "--timeframe", "5m", "--start", "yesterday", "--end", END])
    assert error.value.code == 2
    assert "yesterday" not in capsys.readouterr().err


@pytest.mark.requirement("CLI-02")
def test_service_rejects_non_boolean_strict_end(tmp_path):
    from tests.fixtures.service_env import Env, dt
    env = Env()
    for bad in ("yes", 1, None):
        with pytest.raises(ValueError, match="strict_end must be a bool"):
            env.service.download_and_store(symbol="BTCUSDT", timeframe="5m", start=dt(S), end=dt(S + I), strict_end=bad)
    assert env.fake.calls == []                              # rejected before any network use
