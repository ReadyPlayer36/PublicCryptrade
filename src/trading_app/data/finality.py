"""Pure finality functions and exception types (Stage A).

`is_final` must implement close_time_ms < server_time_ms - lag_ms.
`effective_end_ms` must implement min(requested_end_ms,
floor((server_time_ms-lag_ms)/interval_ms)*interval_ms). Client range validation
must raise EmptyEffectiveRangeError when effective_end_ms <= requested_start_ms.
Naive datetimes must raise NaiveDatetimeError; returned candles with close_time_ms
>= B must raise NonFinalCandleError rather than being silently dropped.
"""
class EmptyEffectiveRangeError(ValueError):
    """Raised when effective end is not greater than requested start."""
class NaiveDatetimeError(ValueError):
    """Raised when an input datetime has no timezone."""
class NonFinalCandleError(RuntimeError):
    """Raised when upstream returns a candle whose close time is >= B."""

def is_final(close_time_ms: int, server_time_ms: int, lag_ms: int) -> bool:
    """Return True iff close_time_ms < B, where B = server_time_ms - lag_ms."""
    return close_time_ms < server_time_ms - lag_ms


def effective_end_ms(requested_end_ms: int, server_time_ms: int, lag_ms: int, interval_ms: int) -> int:
    """Return min(requested_end_ms, floor((S - L) / I) * I); end is exclusive."""
    if interval_ms <= 0:
        raise ValueError("interval_ms must be positive")
    return min(requested_end_ms, ((server_time_ms - lag_ms) // interval_ms) * interval_ms)
