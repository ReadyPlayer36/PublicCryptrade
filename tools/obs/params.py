"""Protocol v0.5 constants (single source for the harness)."""
from __future__ import annotations

from fractions import Fraction

MS = 1_000_000                       # nanoseconds per millisecond
S = 1_000_000_000                    # nanoseconds per second

DELTA = Fraction(1, 10_000)          # drift allowance, 100 ppm (section 5.2)
W_MAX_NS = 250 * MS                  # synchronization adequacy limit (section 5.3)
RETENTION_NS = 600 * S               # sample retention by completion time (section 5.2)
FALLBACK_NS = 60 * S                 # sample window after an empty intersection (section 5.3)

SPACING_NS = 600 * MS                # PACE-2
WINDOWS = ((1 * S, 2), (60 * S, 60))             # PACE-3: (window ns, max starts), open left / closed right
OBS01_SPACING_NS = 2 * S
OBS01_WINDOWS = ((2 * S, 1), (60 * S, 30))

DEADLINE_NS = 17 * S                 # PACE-8 strict total deadline per request
AUDIT_MAX_DURATION_NS = 18 * S       # PACE-5 (e) backstop
CANCEL_GRACE_NS = 1 * S              # cancellation allowance after the deadline
SEND_TIMEOUT_S = 0.25                # bound on the guarded request write (held under the cancellation lock)
CONNECT_TIMEOUT_S, READ_TIMEOUT_S, WRITE_TIMEOUT_S, POOL_TIMEOUT_S = 5.0, 12.0, 5.0, 1.0
MAX_CONSECUTIVE_NO_RESPONSE = 3      # INCIDENT-NETWORK

HOST = "data-api.binance.vision"
TIME_PATH = "/api/v3/time"
KLINES_PATH = "/api/v3/klines"
PATHS = (TIME_PATH, KLINES_PATH)
KLINES_PARAMS = ("symbol", "interval", "startTime", "endTime", "limit")
INTERVALS = ("5m", "15m", "1h", "4h")
ALLOWED_REQUEST_HEADERS = ("accept", "user-agent")
RESPONSE_HEADER_WHITELIST = ("date", "content-type", "retry-after", "x-mbx-used-weight", "x-mbx-used-weight-1m")
