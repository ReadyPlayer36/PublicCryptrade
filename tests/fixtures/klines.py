"""Deterministic raw Binance kline rows for offline tests."""


def make_row(open_ms: int, interval_ms: int = 300_000, price: str = "100") -> list:
    return [open_ms, price, "101", "99", "100.5", "10", open_ms + interval_ms - 1, "1005", 100, "1", "2", "0"]


def make_rows(start_ms: int, count: int, interval_ms: int = 300_000) -> list[list]:
    return [make_row(start_ms + i * interval_ms, interval_ms) for i in range(count)]
