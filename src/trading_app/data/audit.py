"""Safety rules for text stored in the failure audit (no URLs, secrets, headers, bodies or candle data)."""
from __future__ import annotations

import re

MAX_AUDIT_TEXT = 240
FORBIDDEN_AUDIT_TEXT = re.compile(
    r"https?://|://|www\.|@|api[_-]?key|apikey|secret|token|signature|password|passwd|bearer|authorization|"
    r"x-mbx|cookie|user-?agent|\b[0-9a-f]{32,}\b|\{|\}|\[\[|\bopen\s*=|\bclose\s*=",
    re.IGNORECASE,
)


def assert_safe_audit_text(text: str | None) -> None:
    """Raise ValueError if the text could carry a URL, secret, header, body or candle data."""
    if text is None:
        return
    if not isinstance(text, str) or len(text) > MAX_AUDIT_TEXT:
        raise ValueError(f"audit text must be a string of at most {MAX_AUDIT_TEXT} characters")
    if FORBIDDEN_AUDIT_TEXT.search(text):
        raise ValueError("audit text contains a forbidden pattern (URL, secret, header, body or candle data)")
