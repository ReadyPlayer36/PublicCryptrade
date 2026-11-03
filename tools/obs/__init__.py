"""OBS-01/OBS-02 observation harness building blocks (protocol v0.5).

Offline-testable pieces only: monotonic clock, server-time estimator, completion-aware pacer, strict request
deadline watchdog, PACE-5 audit and PACE-7 admission. Public Binance market data only (host and paths are
allow-listed); no credentials, no orders. Nothing here runs a live session; a runner is a separate, later commit.
"""
