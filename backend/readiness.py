"""Dependency-aware readiness probes for the authoritative application."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

from backend.frontend_assets import frontend_dist_path
from src.control_plane.config import Settings
from src.control_plane.execution import ToolRegistry
from src.control_plane.storage import CURRENT_SCHEMA_VERSION, ControlPlaneStore

SHA40 = re.compile(r"^[0-9a-f]{40}$")
RELEASE_IDENTITY_PROFILES = {"staging", "production"}
RELEASE_COMMIT_PATH = Path("/app/.zasi-release-commit")


def _artifact_release_commit() -> str | None:
    """Read the immutable commit identity baked into the built runtime artifact."""
    try:
        value = RELEASE_COMMIT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if SHA40.fullmatch(value) is not None else None


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

    release_commit = _artifact_release_commit()
    checks["release_identity"] = "ready" if release_commit is not None else "unavailable"
    release_identity = {
        "status": checks["release_identity"],
        "commit": release_commit,
        "source": "artifact" if release_commit is not None else None,
    }

    ready = (
        checks["database"] == "ready"
        and checks["redis"] in {"ready", "disabled"}
        and checks["frontend_bundle"] == "ready"
        and (
            settings.profile not in RELEASE_IDENTITY_PROFILES
            or checks["release_identity"] == "ready"
        )
    )
    return {
        "status": "ready" if ready else "degraded",
        "profile": settings.profile,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "checks": checks,
        "release_identity": release_identity,
        "registered_capabilities": len(registry.definitions()),
        "disclosure": "Readiness describes process and dependency state, not subsystem availability.",
    }
