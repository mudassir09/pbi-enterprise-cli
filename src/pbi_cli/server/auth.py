"""API key authentication for pbi-server."""

from __future__ import annotations

import os
import secrets

_ENV_VAR = "PBI_SERVER_KEY"


def get_configured_key() -> str | None:
    """Return the API key from env, or None if not set."""
    return os.environ.get(_ENV_VAR)


def generate_key() -> str:
    """Generate a cryptographically random 32-byte hex API key."""
    return secrets.token_hex(32)


def verify_api_key(api_key: str) -> bool:
    """Return True if the provided key matches the configured key."""
    configured = get_configured_key()
    if not configured:
        return False
    return secrets.compare_digest(api_key, configured)
