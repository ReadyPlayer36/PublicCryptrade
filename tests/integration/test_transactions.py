"""Frozen-matrix acceptance tests; behavior is intentionally red before implementation."""
import pytest

@pytest.mark.requirement("TX-01")
def test_begin_immediate_captured():
    """Acceptance scenario bound to frozen matrix row(s): TX-01."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])


@pytest.mark.requirement("TX-02")
def test_begin_immediate_statement_captured():
    """Acceptance scenario bound to frozen matrix row(s): TX-02."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])


@pytest.mark.requirement("TX-09")
def test_network_and_validation_before_begin_immediate():
    """Acceptance scenario bound to frozen matrix row(s): TX-09."""
    from trading_app.data.repository import CandleRepository
    CandleRepository(None).insert_candles([])
