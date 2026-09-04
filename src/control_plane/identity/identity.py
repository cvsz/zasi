"""Credential hashing and scoped identity helpers."""

import hashlib
import secrets
from typing import Optional


def hash_token(token: str) -> str:
    """Return a stable one-way digest suitable for storage lookup."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token() -> str:
    """Issue a high-entropy opaque session token."""
    return secrets.token_urlsafe(32)


def issue_id(prefix: str) -> str:
    """Issue a non-guessable bounded identifier for a persisted object."""
    if not prefix or not prefix.isascii() or not prefix.replace("_", "").isalnum():
        raise ValueError("invalid identifier prefix")
    return f"{prefix}_{secrets.token_urlsafe(16)}"


def optional_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return None
    return token.strip()
