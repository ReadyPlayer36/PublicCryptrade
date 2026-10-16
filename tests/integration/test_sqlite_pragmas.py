"""Every SQLite connection uses WAL and a busy timeout; the data directory is created first."""
import pytest
from sqlalchemy import text

from trading_app.data.repository import BUSY_TIMEOUT_MS, CandleRepository, create_engine_from_url


@pytest.mark.requirement("R5-03")
def test_data_directory_auto_created(tmp_path):
    target = tmp_path / "a" / "b" / "data" / "trading.db"
    assert not target.parent.exists()
    engine = create_engine_from_url(f"sqlite:///{target}")
    assert target.parent.is_dir()                       # created before any connection is opened
    CandleRepository(engine).create_tables()
    assert target.exists()


@pytest.mark.requirement("R5-03")
def test_relative_database_url_creates_directory_under_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    create_engine_from_url("sqlite:///./data/trading.db")
    assert (tmp_path / "data").is_dir()


@pytest.mark.requirement("R5-01")
def test_wal_and_busy_timeout(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'wal.db'}")
    first, second = engine.connect(), engine.connect()          # two distinct pooled connections
    try:
        for connection in (first, second):
            assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == BUSY_TIMEOUT_MS
        assert first.connection.dbapi_connection is not second.connection.dbapi_connection
    finally:
        first.close()
        second.close()
    assert BUSY_TIMEOUT_MS > 0


@pytest.mark.requirement("R5-01")
def test_new_connections_after_dispose_are_configured_again(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'wal.db'}")
    engine.dispose()
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == BUSY_TIMEOUT_MS


@pytest.mark.requirement("R5-01")
def test_in_memory_database_still_gets_the_busy_timeout():
    with create_engine_from_url("sqlite:///:memory:").connect() as connection:
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == BUSY_TIMEOUT_MS
