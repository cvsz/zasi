"""Dependency-aware readiness probes for the authoritative application."""

from __future__ import annotations

import os
from typing import Any, Dict

from src.control_plane.config import Settings
from src.control_plane.execution import ToolRegistry
from src.control_plane.storage import ControlPlaneStore


def probe(
    store: ControlPlaneStore,
    settings: Settings,
    registry: ToolRegistry,
) -> Dict[str, Any]:
    """Return truthful process/dependency state without claiming capability health."""
    checks: Dict[str, str] = {}
    try:
        checks["database"] = "ready" if store.integrity_check() and store.schema_version() == 7 else "failed"
    except Exception:
        checks["database"] = "failed"
    checks["external_egress"] = "configured" if settings.external_egress_enabled else "disabled"
    checks["research_execution"] = "configured" if settings.research_execution_enabled else "disabled"
    checks["physical_actuation"] = "disabled"
    bundle_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "dist", "index.html"))
    checks["frontend_bundle"] = "ready" if os.path.isfile(bundle_path) else "unavailable"
    ready = checks["database"] == "ready"
    return {
        "status": "ready" if ready else "degraded",
        "profile": settings.profile,
        "schema_version": 7,
        "checks": checks,
        "registered_capabilities": len(registry.definitions()),
        "disclosure": "Readiness describes process and dependency state, not subsystem availability.",
    }
