"""Transaction guard rails that need no database."""
import pytest

from tests.fixtures.candles import candle
from tests.fixtures.policy import frozen_policy
from trading_app.data.repository import MAX_CANDLES_PER_FETCH, CandleRepository, TooManyCandlesError


class ExplodingEngine:
    """Any use of the engine fails the test: oversize fetches must be rejected before persistence."""
    def __getattr__(self, name):
        raise AssertionError(f"engine.{name} used before the size check")


@pytest.mark.requirement("TX-03")
def test_max_candles_limit():
    assert MAX_CANDLES_PER_FETCH == frozen_policy()["storage"]["max_candles_per_fetch"] == 100_000
    repository = CandleRepository(ExplodingEngine(), max_candles_per_fetch=3)
    with pytest.raises(TooManyCandlesError, match="max_candles_per_fetch"):
        repository.insert_candles([candle() for _ in range(4)])
    assert CandleRepository(ExplodingEngine()).max_candles_per_fetch == 100_000


@pytest.mark.requirement("TX-03")
@pytest.mark.parametrize("bad", [0, -1, True, 1.5, None])
def test_invalid_limit_is_rejected(bad):
    with pytest.raises(ValueError):
        CandleRepository(ExplodingEngine(), max_candles_per_fetch=bad)


@pytest.mark.requirement("TX-03")
def test_limit_boundary_is_inclusive(tmp_path):
    from datetime import timedelta
    from trading_app.data.repository import create_engine_from_url
    repository = CandleRepository(create_engine_from_url("sqlite:///:memory:"), max_candles_per_fetch=3)
    repository.create_tables()
    base = candle().open_time
    assert repository.insert_candles([candle(open_time=base + timedelta(minutes=5 * i)) for i in range(3)]) == 3
    with pytest.raises(TooManyCandlesError):
        repository.insert_candles([candle(open_time=base + timedelta(minutes=5 * i)) for i in range(10, 14)])
    assert repository.count() == 3
