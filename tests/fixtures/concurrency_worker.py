"""Worker for the separate-process SQLite tests. Run as a real subprocess; no network, no pytest.

usage: concurrency_worker.py DB READY_FILE GO_FILE OUT_FILE START COUNT VOLUME
Inserts COUNT candles starting at candle index START (identical values unless VOLUME differs), after a start barrier.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from trading_app.data.repository import CandleConflictError, CandleRepository, create_engine_from_url

S0 = datetime.fromtimestamp(1767571200, tz=timezone.utc)
INTERVAL = timedelta(minutes=5)


def make(index: int, volume: str):
    open_time = S0 + INTERVAL * index
    return SimpleNamespace(
        symbol="BTCUSDT", timeframe="5m", open_time=open_time, close_time=open_time + INTERVAL - timedelta(milliseconds=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=Decimal(volume), quote_volume=Decimal("1005"), trade_count=7, created_at_ms=int(time.time() * 1000),
    )


def main(argv):
    db, ready, go, out, start, count, volume = argv[1], argv[2], argv[3], argv[4], int(argv[5]), int(argv[6]), argv[7]
    repository = CandleRepository(create_engine_from_url(f"sqlite:///{db}"))
    candles = [make(start + i, volume) for i in range(count)]
    open(ready, "w").close()
    deadline = time.time() + 60
    while not os.path.exists(go):                       # start barrier: all workers begin together
        if time.time() > deadline:
            return 3
        time.sleep(0.001)
    try:
        result = {"ok": True, "inserted": repository.insert_candles(candles)}
    except CandleConflictError:
        result = {"ok": False, "error": "CandleConflictError"}
    except Exception as exc:                            # anything else is a real problem
        result = {"ok": False, "error": type(exc).__name__}
    tmp = out + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(result, handle)
    os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
