"""Secret redaction helpers for persisted operator/worker payloads.

The control plane must never persist raw credentials supplied by workers or
external adapters.  This module keeps that invariant centralized and bounded so
callers do not need to duplicate ad-hoc filtering rules.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"

_MAX_DEPTH = 12
_MAX_ITEMS = 256
_MAX_STRING_LENGTH = 16_384

_SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "lease_token",
    "claim_token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "credential",
    "credentials",
    "cookie",
    "set_cookie",
    "private_key",
}

_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b(bearer|basic|digest)\s+[A-Za-z0-9._~+/=:-]+"
)
_NAMED_SECRET_VALUE = re.compile(
    r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|"
    r"client[-_ ]?secret|password|passwd|credential|secret)\s*[:=]\s*"
    r"([^\s,;]+)"
)


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SENSITIVE_KEYS:
        return True
    return normalized.endswith(("_token", "_password", "_secret", "_credential"))


def _sanitize_string(value: str) -> str:
    bounded = value[:_MAX_STRING_LENGTH]
    bounded = _AUTHORIZATION_VALUE.sub(lambda match: f"{match.group(1)} {REDACTED}", bounded)
    bounded = _NAMED_SECRET_VALUE.sub(lambda match: f"{match.group(1)}={REDACTED}", bounded)
    if len(value) > _MAX_STRING_LENGTH:
        bounded += TRUNCATED
    return bounded


def sanitize_persisted_payload(value: Any, *, _depth: int = 0) -> Any:
    """Return a JSON-compatible copy with credential-like material removed.

    Traversal is deliberately bounded to prevent attacker-controlled worker
    payloads from causing unbounded recursion or persisted amplification.
    """

    if _depth >= _MAX_DEPTH:
        return TRUNCATED

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                sanitized[TRUNCATED] = TRUNCATED
                break
            output_key = str(key)
            sanitized[output_key] = (
                REDACTED
                if _is_sensitive_key(key)
                else sanitize_persisted_payload(item, _depth=_depth + 1)
            )
        return sanitized

    if isinstance(value, (list, tuple)):
        sanitized_items = [
            sanitize_persisted_payload(item, _depth=_depth + 1)
            for item in value[:_MAX_ITEMS]
        ]
        if len(value) > _MAX_ITEMS:
            sanitized_items.append(TRUNCATED)
        return sanitized_items

    if isinstance(value, str):
        return _sanitize_string(value)

    return value
