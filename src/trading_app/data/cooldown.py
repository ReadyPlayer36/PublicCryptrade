"""Cooldown persistence contract stubs; implementation is intentionally deferred.

Persist JSON exactly as {"until_ms": int, "reason": str}. The state is global
across allowed hosts and an active cooldown prevents all HTTP calls, including
server-time calls. Missing, corrupt, non-integer, and negative fields raise
CorruptCooldownError with a diagnostic message; no network call may occur first.
"""
class CorruptCooldownError(ValueError):
    """Raised when cooldown state is missing, corrupt, non-integer, or negative."""

def read_cooldown(*args, **kwargs):
    """Load and validate cooldown JSON; raises CorruptCooldownError on invalid state."""
    raise NotImplementedError("Stage-2 implementation not started: read_cooldown")

def write_cooldown(*args, **kwargs):
    """Atomically persist cooldown JSON; not implemented in Stage 2 scaffold."""
    raise NotImplementedError("Stage-2 implementation not started: write_cooldown")
