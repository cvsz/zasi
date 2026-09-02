"""Dependency-aware readiness probes for the authoritative application."""

from __future__ import annotations

import os
from typing import Any, Dict

from backend.frontend_assets import frontend_dist_path
from src.control_plane.config import Settings
from src.control_plane.execution import ToolRegistry
from src.control_plane.storage import CURRENT_SCHEMA_VERSION, ControlPlaneStore


def probe(
    store: ControlPlaneStore,
    settings: Settings,
    registry: ToolRegistry,
    redis_runtime: Any = None,
) -> Dict[str, Any]:
    """Return truthful process/dependency state without claiming capability health."""
    checks: Dict[str, str] = {}
    try:
        checks["database"] = (
            "ready"
            if store.integrity_check() and store.schema_version() == CURRENT_SCHEMA_VERSION
            else "failed"
        )
    except Exception:
        checks["database"] = "failed"
    if settings.redis_url:
        checks["redis"] = "ready" if redis_runtime is not None and redis_runtime.ping() else "failed"
    else:
        checks["redis"] = "disabled"
    checks["external_egress"] = "configured" if settings.external_egress_enabled else "disabled"
    checks["research_execution"] = "configured" if settings.research_execution_enabled else "disabled"
    checks["physical_actuation"] = "disabled"
    bundle_path = str(frontend_dist_path() / "index.html")
    checks["frontend_bundle"] = "ready" if os.path.isfile(bundle_path) else "unavailable"
    ready = (
        checks["database"] == "ready"
        and checks["redis"] in {"ready", "disabled"}
        and checks["frontend_bundle"] == "ready"
    )
    return {
        "status": "ready" if ready else "degraded",
        "profile": settings.profile,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "checks": checks,
        "registered_capabilities": len(registry.definitions()),
        "disclosure": "Readiness describes process and dependency state, not subsystem availability.",
    }
