"""CLI contracts; production behavior remains a source stub pending approval."""
import pytest
from trading_app.data.binance_client import BinanceClientError

@pytest.mark.requirement("CLI-02")
def test_cli_exit_codes_and_clean_expected_errors():
    from scripts.download_candles import main
    with pytest.raises(SystemExit) as error:
        main(["--not-a-real-option"])
    assert error.value.code == 2

@pytest.mark.requirement("CLI-01")
def test_download_script_with_mocked_public_client():
    from scripts.download_candles import main
    # The approved CLI contract will consume public-client arguments and return 0 on success.
    assert main(["--symbol", "BTCUSDT", "--timeframe", "5m", "--start", "2026-01-05T00:00:00Z", "--end", "2026-01-05T01:00:00Z"]) == 0

@pytest.mark.requirement("HYGIENE-01")
def test_script_wrapper_is_thin_and_runnable():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "scripts/download_candles.py").read_text()
    assert "from trading_app.cli import main" in source
    assert "raise SystemExit(main())" in source
    assert "BinanceMarketDataClient" not in source
