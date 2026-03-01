from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    """Return SHA256 hex digest of the given text, used for skip-unchanged detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
