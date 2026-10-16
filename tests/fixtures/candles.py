"""Normalized candle-like fixtures; values are deliberately independent of production constructors."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

START = datetime(2026, 1, 5, tzinfo=timezone.utc)

def candle(*, open_time=START, close_time=None, open="100.10", high="101.00", low="99.50", close="100.50", volume="12.34500000", quote_volume="1240.00000000", trade_count=100, created_at_ms=1000, symbol="BTCUSDT", timeframe="5m"):
    return SimpleNamespace(
        symbol=symbol, timeframe=timeframe, open_time=open_time,
        close_time=close_time or open_time + timedelta(minutes=5) - timedelta(milliseconds=1),
        open=Decimal(open), high=Decimal(high), low=Decimal(low), close=Decimal(close),
        volume=Decimal(volume), quote_volume=Decimal(quote_volume), trade_count=trade_count,
        created_at_ms=created_at_ms,
    )
