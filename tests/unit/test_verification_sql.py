"""Verification must be Decimal/string-safe: no SQL ever converts a decimal text value to floating point."""
import inspect
import re
from decimal import Decimal

import pytest

from trading_app.data import verification
from trading_app.data.verification import QUERIES, _check_row, _dec

FORBIDDEN = re.compile(r"\bCAST\b|\bAS\s+(REAL|FLOAT|DOUBLE|NUMERIC|DECIMAL)\b|\bREAL\b|\bFLOAT\b", re.IGNORECASE)
DECIMAL_COLUMNS = ("open_price", "high_price", "low_price", "close_price", "volume", "quote_volume")


@pytest.mark.requirement("VERIFY-02")
def test_no_cast_as_real():
    assert set(QUERIES) == {"count", "duplicates", "continuity", "rows"}
    for name, sql in QUERIES.items():
        assert not FORBIDDEN.search(sql), name
    source = inspect.getsource(verification)
    assert not re.search(r"\bfloat\s*\(", source)                      # no float() either
    # the detector itself works
    assert FORBIDDEN.search("SELECT CAST(high_price AS REAL) FROM candles")
    assert FORBIDDEN.search("select high_price+0.0 as float from t") and not FORBIDDEN.search("SELECT open_time_ms FROM candles")


@pytest.mark.requirement("VERIFY-01")
@pytest.mark.requirement("VERIFY-02")
def test_decimal_string_safe_comparisons():
    # Decimal columns are only ever selected as text and compared in Python, never in SQL.
    for name, sql in QUERIES.items():
        for column in DECIMAL_COLUMNS:
            for clause in re.findall(r"\b(?:WHERE|HAVING|ON)\b.*", sql, flags=re.IGNORECASE):
                assert column not in clause, (name, column)
    # Differences that binary floating point cannot see are caught exactly (here 1e-20 beyond 100.5).
    tiny = "100.50000000000000000001"
    flagged = _check_row("BTCUSDT", "5m", 0, "100", "100.5", "99", tiny, "1", "1")
    assert [i.code for i in flagged] == ["INVALID_OHLC"]
    assert float(Decimal(tiny)) == float(Decimal("100.5"))             # why float comparison would miss it
    assert _check_row("BTCUSDT", "5m", 0, "100", "100.5", "99", "100.5", "0.00000000000000000001", "0") == []
    assert [i.code for i in _check_row("BTCUSDT", "5m", 0, "100", "101", "99", "100.5", "-0.00000000000000000001", "0")] == ["NEGATIVE_VOLUME"]
    assert _dec("1e3") == Decimal("1000") and _dec("abc") is None and _dec("NaN") is None and _dec(5) is None
