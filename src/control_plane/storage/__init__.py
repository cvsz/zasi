import json
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
_ORIGINAL_APPEND_AUDITED_EVENT_LOCKED = ControlPlaneStore._append_audited_event_locked


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


def _append_audited_event_locked_redacted(
    connection: Any,
    tenant_id: str,
    actor_kind: str,
    actor_id: str,
    action: str,
    target: str,
    outcome: str,
    event_type: str,
    aggregate_kind: str,
    aggregate_id: str,
    payload_json: str,
    payload: Dict[str, Any],
    now: str,
    event_id: str,
    visibility: str = "tenant",
    schema_version: int = 1,
    execution_id: Optional[str] = None,
    agent_version: Optional[str] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    sensitivity: str = "tenant",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove credential-like material before audit/event/outbox persistence."""
    del payload_json
    safe_payload = sanitize_persisted_payload(payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {"value": safe_payload}
    safe_payload_json = json.dumps(
        safe_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return _ORIGINAL_APPEND_AUDITED_EVENT_LOCKED(
        connection=connection,
        tenant_id=tenant_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        action=action,
        target=target,
        outcome=outcome,
        event_type=event_type,
        aggregate_kind=aggregate_kind,
        aggregate_id=aggregate_id,
        payload_json=safe_payload_json,
        payload=safe_payload,
        now=now,
        event_id=event_id,
        visibility=visibility,
        schema_version=schema_version,
        execution_id=execution_id,
        agent_version=agent_version,
        correlation_id=correlation_id,
        causation_id=causation_id,
        sensitivity=sensitivity,
        idempotency_key=idempotency_key,
    )


# Install persistence guards on the shared repository contract before the
# PostgreSQL subclass is imported. SQLite and PostgreSQL therefore enforce the
# same credential-hygiene invariant at every durable worker/event boundary.
ControlPlaneStore.complete_task = _complete_task_redacted
ControlPlaneStore.complete_task_run = _complete_task_run_redacted
ControlPlaneStore._append_audited_event_locked = staticmethod(
    _append_audited_event_locked_redacted
)

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
