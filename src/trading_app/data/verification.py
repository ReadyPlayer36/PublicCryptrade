"""Read-only verification of stored candles (VERIFY-01/02/03, M1-15).

Rules: SQL is used only for integer/text work (counts, duplicates, timestamp deltas). Every decimal
comparison (OHLC, volume) is done in Python with ``Decimal`` on the stored exact strings; no query
ever converts a decimal string to floating point. Nothing here writes or repairs data.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.engine import Engine

from trading_app.data.validator import TIMEFRAME_MS

COUNT_SQL = "SELECT symbol, timeframe, COUNT(*) AS candle_count FROM candles GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
DUPLICATE_SQL = (
    "SELECT symbol, timeframe, open_time_ms, COUNT(*) AS n FROM candles "
    "GROUP BY symbol, timeframe, open_time_ms HAVING COUNT(*) > 1 ORDER BY symbol, timeframe, open_time_ms"
)
CONTINUITY_SQL = (
    "SELECT symbol, timeframe, open_time_ms, "
    "open_time_ms - LAG(open_time_ms) OVER (PARTITION BY symbol, timeframe ORDER BY open_time_ms) AS delta_ms "
    "FROM candles ORDER BY symbol, timeframe, open_time_ms"
)
ROWS_SQL = (
    "SELECT id, symbol, timeframe, open_time_ms, open_price, high_price, low_price, close_price, volume, quote_volume "
    "FROM candles ORDER BY symbol, timeframe, open_time_ms"
)
QUERIES = {"count": COUNT_SQL, "duplicates": DUPLICATE_SQL, "continuity": CONTINUITY_SQL, "rows": ROWS_SQL}


@dataclass(frozen=True)
class VerificationIssue:
    code: str              # fixed vocabulary
    symbol: str
    timeframe: str
    open_time_ms: int | None = None


@dataclass(frozen=True)
class VerificationReport:
    counts: dict[tuple[str, str], int]
    issues: tuple[VerificationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def issue_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for issue in self.issues:
            out[issue.code] = out.get(issue.code, 0) + 1
        return dict(sorted(out.items()))


def _dec(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def verify_database(engine: Engine) -> VerificationReport:
    """Run every verification check on the stored candles. Read-only; never repairs."""
    issues: list[VerificationIssue] = []
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA query_only=ON")
        try:
            counts = {(r[0], r[1]): int(r[2]) for r in connection.exec_driver_sql(COUNT_SQL)}
            for r in connection.exec_driver_sql(DUPLICATE_SQL):
                issues.append(VerificationIssue("DUPLICATE_CANDLE", str(r[0]), str(r[1]), r[2]))
            for r in connection.exec_driver_sql(CONTINUITY_SQL):
                symbol, timeframe, open_ms, delta = r[0], r[1], r[2], r[3]
                interval = TIMEFRAME_MS.get(timeframe)
                if interval is None:
                    continue
                if open_ms % interval != 0:
                    issues.append(VerificationIssue("MISALIGNED_OPEN", symbol, timeframe, open_ms))
                if delta is None:
                    continue
                if delta == 0:
                    continue                      # reported once as DUPLICATE_CANDLE
                if delta < 0 or delta % interval != 0:
                    issues.append(VerificationIssue("IRREGULAR_SPACING", symbol, timeframe, open_ms))
                elif delta > interval:
                    issues.append(VerificationIssue("SERIES_GAP", symbol, timeframe, open_ms))
            for r in connection.exec_driver_sql(ROWS_SQL):
                issues.extend(_check_row(*r[1:]))
        finally:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only=OFF")
    return VerificationReport(counts=counts, issues=tuple(issues))


def _check_row(symbol, timeframe, open_ms, o, h, lo, c, volume, quote_volume) -> list[VerificationIssue]:
    def issue(code: str) -> VerificationIssue:
        return VerificationIssue(code, str(symbol), str(timeframe), open_ms if isinstance(open_ms, int) else None)

    prices = [_dec(x) for x in (o, h, lo, c)]
    found: list[VerificationIssue] = []
    if any(p is None for p in prices):
        found.append(issue("BAD_DECIMAL_TEXT"))
    else:
        po, ph, pl, pc = prices
        if min(prices) <= 0:
            found.append(issue("NONPOSITIVE_PRICE"))
        if ph < max(po, pc) or pl > min(po, pc) or pl > ph:
            found.append(issue("INVALID_OHLC"))
    for value in (volume, quote_volume):
        parsed = _dec(value)
        if parsed is None:
            found.append(issue("BAD_DECIMAL_TEXT"))
        elif parsed < 0:
            found.append(issue("NEGATIVE_VOLUME"))
    return found
