from typing import Any, Dict, Optional

from src.control_plane.redaction import sanitize_persisted_payload

from .storage import (
    CURRENT_SCHEMA_VERSION,
    ConflictError,
    ControlPlaneStore,
    NotFoundError,
    ScopeViolation,
    _prepare_private_directory,
    _prepare_private_sqlite_path,
)


_ORIGINAL_COMPLETE_TASK = ControlPlaneStore.complete_task
_ORIGINAL_COMPLETE_TASK_RUN = ControlPlaneStore.complete_task_run


def _complete_task_redacted(
    self: ControlPlaneStore,
    task_id: str,
    tenant_id: str,
    worker_id: str,
    lease_token: str,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_result = sanitize_persisted_payload(result) if result is not None else None
    return _ORIGINAL_COMPLETE_TASK(
        self,
        task_id,
        tenant_id,
        worker_id,
        lease_token,
        safe_result,
    )


def _complete_task_run_redacted(
    self: ControlPlaneStore,
    run_id: str,
    tenant_id: str,
    worker_id: str,
    lease_token: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_result = sanitize_persisted_payload(result) if result is not None else None
    safe_error = sanitize_persisted_payload(error) if error is not None else None
    return _ORIGINAL_COMPLETE_TASK_RUN(
        self,
        run_id,
        tenant_id,
        worker_id,
        lease_token,
        status,
        safe_result,
        safe_error,
    )


# Install the persistence guard on the shared repository contract before the
# PostgreSQL subclass is imported. Both SQLite and PostgreSQL therefore enforce
# the same credential-hygiene invariant at the durable storage boundary.
ControlPlaneStore.complete_task = _complete_task_redacted
ControlPlaneStore.complete_task_run = _complete_task_run_redacted

from .postgres_storage import PostgresControlPlaneStore


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ConflictError",
    "ControlPlaneStore",
    "NotFoundError",
    "PostgresControlPlaneStore",
    "ScopeViolation",
    "_prepare_private_directory",
    "_prepare_private_sqlite_path",
]
