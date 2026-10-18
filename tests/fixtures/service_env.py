"""Shared, fully offline test environment for the download service (fake HTTP, in-memory or file SQLite)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import event

from tests.fixtures.fakes import FakeHttpClient, FakeResponse
from tests.fixtures.klines import make_rows
from trading_app.config import Settings
from trading_app.data.binance_client import BinanceMarketDataClient
from trading_app.data.repository import CandleRepository, create_engine_from_url
from trading_app.data.service import MarketDataService

S0 = 1767571200000
I = 300_000
NOW = 1_800_000_000_000
SETTINGS = Settings(_env_file=None)


def dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def time_resp(ms: int) -> FakeResponse:
    return FakeResponse(payload={"serverTime": ms})


def ok_responses(n: int = 3, start: int = S0, server_ms: int | None = None, rows=None) -> list[FakeResponse]:
    return [time_resp(server_ms if server_ms is not None else start + (n + 10) * I),
            FakeResponse(payload=rows if rows is not None else make_rows(start, n))]


class TracingHttp:
    """Wraps a fake HTTP client and records every request on a shared timeline."""
    def __init__(self, inner, timeline):
        self.inner, self.timeline = inner, timeline
        self.calls = inner.calls

    def get(self, url, *, params=None):
        self.timeline.append(("net", url))
        return self.inner.get(url, params=params)


class Env:
    def __init__(self, responses=(), errors=(), lag=0, db_url="sqlite:///:memory:", now_ms=lambda: NOW, settings=SETTINGS):
        self.timeline: list[tuple] = []
        self.fake = FakeHttpClient(responses, errors)
        self.http = TracingHttp(self.fake, self.timeline)
        self.engine = create_engine_from_url(db_url)
        self._attach_instrumentation()
        self.repo = CandleRepository(self.engine)
        self.repo.create_tables()
        self.timeline.clear()
        self.client = BinanceMarketDataClient(base_url="https://data-api.binance.vision", http_client=self.http,
                                              sleep=lambda _: None, jitter=lambda: 0.0, finality_lag_ms=lag)
        self.service = MarketDataService(settings=settings, client=self.client, repository=self.repo, now_ms=now_ms)

    def _attach_instrumentation(self):
        timeline = self.timeline

        @event.listens_for(self.engine, "connect")
        def trace(dbapi_connection, record):               # the statements SQLite itself actually executes
            dbapi_connection.set_trace_callback(lambda statement: timeline.append(("sqlite", statement.strip())))

        event.listen(self.engine, "before_cursor_execute", lambda c, cur, stmt, *a: timeline.append(("sa-exec", stmt.strip())))
        event.listen(self.engine, "commit", lambda conn: timeline.append(("sa-commit",)))
        event.listen(self.engine, "rollback", lambda conn: timeline.append(("sa-rollback",)))

    def run(self, n: int = 3, start: int = S0, symbol: str = "BTCUSDT", timeframe: str = "5m", end: int | None = None):
        return self.service.download_and_store(symbol=symbol, timeframe=timeframe, start=dt(start),
                                               end=dt(end if end is not None else start + n * I))

    def sqlite(self, *prefixes):
        """SQLite-level statements (only those starting with the given prefixes), in order."""
        return [e[1] for e in self.timeline if e[0] == "sqlite" and e[1].upper().startswith(prefixes or ("",))]

    def kinds(self):
        return [e[0] for e in self.timeline]
