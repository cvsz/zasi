"""Explicitly versioned compatibility metadata for the pre-v2 API.

This module contains no legacy server imports and no dispatch logic. The
authoritative ASGI application owns the compatibility responses so a legacy
process cannot become a production route owner by import side effect.
"""

from __future__ import annotations

from typing import Dict


COMPATIBILITY_ROUTES: Dict[str, Dict[str, str]] = {
    "/api/status": {"method": "GET", "disposition": "read_only", "sunset": "v2"},
    "/api/telemetry": {"method": "GET", "disposition": "unavailable_disclosure", "sunset": "v2"},
    "/api/tick": {"method": "GET", "disposition": "retired", "sunset": "v2"},
    "/api/execute/{key}": {"method": "GET", "disposition": "retired", "sunset": "v2"},
    "/api/mutate": {"method": "POST", "disposition": "retired", "sunset": "v2"},
    "/api/rsi/upgrade": {"method": "POST", "disposition": "disabled", "sunset": "v2"},
    "/api/mcp": {"method": "POST", "disposition": "broker_proxy_required", "sunset": "v2"},
}


def route_metadata(path: str) -> Dict[str, str]:
    """Return a copy so callers cannot mutate the compatibility contract."""
    return dict(COMPATIBILITY_ROUTES.get(path, {"disposition": "unknown"}))
