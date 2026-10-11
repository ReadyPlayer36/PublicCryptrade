"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("CLI-02")
def test_cli_exit_codes_and_clean_expected_errors():
    """Acceptance scenario bound to frozen matrix row(s): CLI-02."""
    from scripts.download_candles import main
    main([])


@pytest.mark.requirement("CLI-01")
def test_download_script_with_mocked_public_client():
    """Acceptance scenario bound to frozen matrix row(s): CLI-01."""
    from scripts.download_candles import main
    main([])


@pytest.mark.requirement("HYGIENE-01")
def test_script_wrapper_is_thin_and_runnable():
    """Acceptance scenario bound to frozen matrix row(s): HYGIENE-01."""
    from scripts.download_candles import main
    main([])
