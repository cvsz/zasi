"""Small durable SQLite repository with tenant-scoped events and audit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
import threading
import time
import hmac
from typing import Any, Dict, List, Optional, Tuple

from .identity import hash_token


CURRENT_SCHEMA_VERSION = 10


class NotFoundError(LookupError):
    """Requested object does not exist in the current repository."""


class ScopeViolation(PermissionError):
    """Object exists outside the requested tenant scope."""


class ConflictError(RuntimeError):
    """The requested state transition conflicts with the durable record."""


def _is_unique_integrity_error(error: BaseException) -> bool:
    """Recognize SQLite and PostgreSQL unique-key violations without coupling imports."""
    return isinstance(error, sqlite3.IntegrityError) or getattr(error, "sqlstate", None) == "23505"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_optional_timestamp(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"{field_name} must include a timezone")
        return _timestamp(value)
    return _timestamp(_parse_utc_timestamp(value, field_name))


class ControlPlaneStore:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            if self.database_path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self.database_path))
                os.makedirs(parent, exist_ok=True)
            connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if self.database_path != ":memory:":
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    policy_version TEXT NOT NULL DEFAULT 'policy.v1',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS principals (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    device_id TEXT,
                    token_hash TEXT NOT NULL UNIQUE,
                    scope_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    label TEXT NOT NULL DEFAULT 'device',
                    status TEXT NOT NULL,
                    enrollment_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS device_pairing_challenges (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    device_label TEXT NOT NULL,
                    challenge_hash TEXT NOT NULL,
                    idempotency_key TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS capabilities (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    tool_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    source_kind TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    goal_json TEXT NOT NULL,
                    requested_mode TEXT NOT NULL,
                    requested_risk_tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    intent_id TEXT NOT NULL REFERENCES intents(id),
                    digest TEXT NOT NULL,
                    scope_digest TEXT NOT NULL DEFAULT '',
                    steps_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    digest TEXT NOT NULL,
                    scope_digest TEXT NOT NULL,
                    approver_id TEXT NOT NULL REFERENCES principals(id),
                    required_capability TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL DEFAULT '',
                    plan_id TEXT,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    unknown_reason TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    UNIQUE (tenant_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    step_id TEXT,
                    tool_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    timeout_ms INTEGER NOT NULL DEFAULT 2000,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    retry_policy TEXT NOT NULL DEFAULT 'none',
                    next_attempt_at TEXT,
                    worker_id TEXT,
                    lease_token TEXT,
                    lease_until TEXT,
                    last_error TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    unknown_reason TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    artifact_ref TEXT,
                    supersedes TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS action_evidence (
                    action_id TEXT PRIMARY KEY REFERENCES actions(id),
                    evidence_id TEXT NOT NULL REFERENCES evidence(id)
                );
                CREATE TABLE IF NOT EXISTS audit_records (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    actor_kind TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    sequence INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    aggregate_kind TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    actor_kind TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'tenant',
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE (tenant_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    event_id TEXT NOT NULL REFERENCES events(id),
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    last_error TEXT,
                    dead_lettered_at TEXT,
                    claimed_at TEXT,
                    lease_until TEXT,
                    claim_token TEXT
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    subject TEXT NOT NULL,
                    bucket INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    reset_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject, bucket)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    digest TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    storage_ref TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'conversation',
                    project_id TEXT,
                    source_ref TEXT NOT NULL DEFAULT '',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    trust TEXT NOT NULL DEFAULT 'operator',
                    last_verified_at TEXT,
                    fresh_until TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS briefings (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sequences (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    name TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    steps_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sequence_runs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    sequence_id TEXT NOT NULL REFERENCES sequences(id),
                    revision INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    UNIQUE (tenant_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    due_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES goals(id),
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    title TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    not_before TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    idempotency_key TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_token TEXT,
                    lease_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE (tenant_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    depends_on_task_id TEXT NOT NULL REFERENCES tasks(id),
                    PRIMARY KEY (task_id, depends_on_task_id)
                );
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    principal_id TEXT NOT NULL REFERENCES principals(id),
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    next_run_at TEXT NOT NULL,
                    interval_seconds INTEGER,
                    misfire_policy TEXT NOT NULL DEFAULT 'skip',
                    idempotency_key TEXT NOT NULL,
                    last_run_at TEXT,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    UNIQUE (tenant_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    goal_id TEXT NOT NULL REFERENCES goals(id),
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    schedule_id TEXT REFERENCES schedules(id),
                    occurrence_key TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    worker_id TEXT,
                    lease_token TEXT,
                    lease_until TEXT,
                    scheduled_for TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    UNIQUE (tenant_id, idempotency_key),
                    UNIQUE (tenant_id, schedule_id, occurrence_key)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_tenant
                    ON sessions(tenant_id, status, expires_at);
                CREATE INDEX IF NOT EXISTS idx_events_tenant_sequence
                    ON events(tenant_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_runs_tenant_idempotency
                    ON runs(tenant_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_actions_claimable
                    ON actions(status, next_attempt_at, lease_until);
                CREATE INDEX IF NOT EXISTS idx_approvals_tenant_plan
                    ON approvals(tenant_id, plan_id, decision, expires_at);
                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                    ON outbox(status, next_attempt_at);
                CREATE INDEX IF NOT EXISTS idx_devices_tenant
                    ON devices(tenant_id, status, created_at);
                CREATE INDEX IF NOT EXISTS idx_sequences_tenant
                    ON sequences(tenant_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_sequence_runs_tenant_idempotency
                    ON sequence_runs(tenant_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_goals_tenant_status
                    ON goals(tenant_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_tenant_status_due
                    ON tasks(tenant_id, status, not_before, updated_at);
                CREATE INDEX IF NOT EXISTS idx_task_dependencies_task
                    ON task_dependencies(tenant_id, task_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_schedules_tenant_idempotency
                    ON schedules(tenant_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_schedules_due
                    ON schedules(tenant_id, status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_task_runs_task_history
                    ON task_runs(tenant_id, task_id, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_task_runs_claimable
                    ON task_runs(tenant_id, status, lease_until, scheduled_for);
                """
            )
            tenant_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tenants)").fetchall()
            }
            if "policy_version" not in tenant_columns:
                connection.execute(
                    "ALTER TABLE tenants ADD COLUMN policy_version TEXT NOT NULL DEFAULT 'policy.v1'"
                )
            plan_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(plans)").fetchall()
            }
            if "principal_id" not in plan_columns:
                connection.execute(
                    "ALTER TABLE plans ADD COLUMN principal_id TEXT NOT NULL DEFAULT ''"
                )
            if "scope_digest" not in plan_columns:
                connection.execute(
                    "ALTER TABLE plans ADD COLUMN scope_digest TEXT NOT NULL DEFAULT ''"
                )
            session_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "scope_json" not in session_columns:
                connection.execute(
                    "ALTER TABLE sessions ADD COLUMN scope_json TEXT NOT NULL DEFAULT '[]'"
                )
            evidence_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(evidence)").fetchall()
            }
            if "result_json" not in evidence_columns:
                connection.execute(
                    "ALTER TABLE evidence ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "supersedes" not in evidence_columns:
                connection.execute(
                    "ALTER TABLE evidence ADD COLUMN supersedes TEXT"
                )
            device_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(devices)").fetchall()
            }
            if "label" not in device_columns:
                connection.execute(
                    "ALTER TABLE devices ADD COLUMN label TEXT NOT NULL DEFAULT 'device'"
                )
            if "revoked_at" not in device_columns:
                connection.execute("ALTER TABLE devices ADD COLUMN revoked_at TEXT")
            pairing_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(device_pairing_challenges)"
                ).fetchall()
            }
            if "idempotency_key" not in pairing_columns:
                connection.execute(
                    "ALTER TABLE device_pairing_challenges ADD COLUMN idempotency_key TEXT"
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_pairing_tenant_idempotency "
                "ON device_pairing_challenges(tenant_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
            event_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(events)").fetchall()
            }
            if "visibility" not in event_columns:
                connection.execute(
                    "ALTER TABLE events ADD COLUMN visibility TEXT NOT NULL DEFAULT 'tenant'"
                )
            if "schema_version" not in event_columns:
                connection.execute(
                    "ALTER TABLE events ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1"
                )
            outbox_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(outbox)").fetchall()
            }
            if "max_attempts" not in outbox_columns:
                connection.execute(
                    "ALTER TABLE outbox ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5"
                )
            if "last_error" not in outbox_columns:
                connection.execute("ALTER TABLE outbox ADD COLUMN last_error TEXT")
            if "dead_lettered_at" not in outbox_columns:
                connection.execute("ALTER TABLE outbox ADD COLUMN dead_lettered_at TEXT")
            if "claimed_at" not in outbox_columns:
                connection.execute("ALTER TABLE outbox ADD COLUMN claimed_at TEXT")
            if "lease_until" not in outbox_columns:
                connection.execute("ALTER TABLE outbox ADD COLUMN lease_until TEXT")
            if "claim_token" not in outbox_columns:
                connection.execute("ALTER TABLE outbox ADD COLUMN claim_token TEXT")
            artifact_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
            }
            if "storage_ref" not in artifact_columns:
                connection.execute(
                    "ALTER TABLE artifacts ADD COLUMN storage_ref TEXT NOT NULL DEFAULT ''"
                )
            memory_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(memory_items)").fetchall()
            }
            if "memory_type" not in memory_columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN memory_type TEXT NOT NULL DEFAULT 'conversation'"
                )
            if "project_id" not in memory_columns:
                connection.execute("ALTER TABLE memory_items ADD COLUMN project_id TEXT")
            if "source_ref" not in memory_columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''"
                )
            if "provenance_json" not in memory_columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "trust" not in memory_columns:
                connection.execute(
                    "ALTER TABLE memory_items ADD COLUMN trust TEXT NOT NULL DEFAULT 'operator'"
                )
            if "last_verified_at" not in memory_columns:
                connection.execute("ALTER TABLE memory_items ADD COLUMN last_verified_at TEXT")
            if "fresh_until" not in memory_columns:
                connection.execute("ALTER TABLE memory_items ADD COLUMN fresh_until TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_project_scope "
                "ON memory_items(tenant_id, project_id, status, created_at)"
            )
            run_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "principal_id" not in run_columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN principal_id TEXT NOT NULL DEFAULT ''"
                )
            if "request_digest" not in run_columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN request_digest TEXT NOT NULL DEFAULT ''"
                )
            if "cancel_requested" not in run_columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
                )
            if "unknown_reason" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN unknown_reason TEXT")
            action_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(actions)").fetchall()
            }
            action_migrations = (
                ("payload_json", "ALTER TABLE actions ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"),
                ("timeout_ms", "ALTER TABLE actions ADD COLUMN timeout_ms INTEGER NOT NULL DEFAULT 2000"),
                ("max_attempts", "ALTER TABLE actions ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 1"),
                ("retry_policy", "ALTER TABLE actions ADD COLUMN retry_policy TEXT NOT NULL DEFAULT 'none'"),
                ("next_attempt_at", "ALTER TABLE actions ADD COLUMN next_attempt_at TEXT"),
                ("worker_id", "ALTER TABLE actions ADD COLUMN worker_id TEXT"),
                ("lease_token", "ALTER TABLE actions ADD COLUMN lease_token TEXT"),
                ("lease_until", "ALTER TABLE actions ADD COLUMN lease_until TEXT"),
                ("last_error", "ALTER TABLE actions ADD COLUMN last_error TEXT"),
                ("cancel_requested", "ALTER TABLE actions ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"),
                ("unknown_reason", "ALTER TABLE actions ADD COLUMN unknown_reason TEXT"),
            )
            for column_name, statement in action_migrations:
                if column_name not in action_columns:
                    connection.execute(statement)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_actions_claimable "
                "ON actions(status, next_attempt_at, lease_until)"
            )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if task_columns and "lease_owner" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN lease_owner TEXT")
            schema_row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if schema_row is not None:
                try:
                    current_schema = int(schema_row["value"])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError("schema version metadata is invalid") from exc
                if current_schema > CURRENT_SCHEMA_VERSION:
                    raise RuntimeError("database schema is newer than this application")
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(CURRENT_SCHEMA_VERSION),),
            )
            self._connection = connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("ControlPlaneStore.initialize() must be called first")
        return self._connection

    def schema_version(self) -> int:
        with self._lock:
            row = self._conn().execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        if row is None:
            raise RuntimeError("schema version metadata is missing")
        return int(row["value"])

    def integrity_check(self) -> bool:
        with self._lock:
            row = self._conn().execute("PRAGMA integrity_check").fetchone()
        return bool(row and row[0] == "ok")

    def backup_to(self, backup_path: str) -> None:
        """Create a consistent SQLite backup without mutating the source DB."""
        if not backup_path or backup_path == ":memory:":
            raise ValueError("backup path must be a filesystem path")
        source_path = os.path.abspath(self.database_path)
        target_path = os.path.abspath(backup_path)
        if source_path == target_path:
            raise ValueError("backup path must differ from database path")
        parent = os.path.dirname(target_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._lock:
            destination = sqlite3.connect(target_path)
            try:
                self._conn().backup(destination)
            finally:
                destination.close()

    def create_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._conn().execute(
                "INSERT OR IGNORE INTO tenants(id, status, created_at) VALUES(?, 'active', ?)",
                (tenant_id, _timestamp(_utcnow())),
            )

    def create_principal(self, principal_id: str, tenant_id: str) -> None:
        with self._lock:
            self._conn().execute(
                "INSERT OR IGNORE INTO principals(id, tenant_id, status, created_at) "
                "VALUES(?, ?, 'active', ?)",
                (principal_id, tenant_id, _timestamp(_utcnow())),
            )

    def upsert_capability(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Persist the code-owned capability manifest for audit and inspection."""
        tool_id = manifest.get("tool_id")
        version = manifest.get("version")
        if not isinstance(tool_id, str) or not tool_id or not isinstance(version, str) or not version:
            raise ValueError("capability manifest requires a tool_id and version")
        capability_id = str(manifest.get("capability_id") or tool_id)
        capability_row_id = "cap_" + hash_token(f"{capability_id}:{version}")[:26]
        now = _timestamp(_utcnow())
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock:
            self._conn().execute(
                "INSERT INTO capabilities(id, tenant_id, tool_id, version, risk_tier, manifest_json, status, created_at) "
                "VALUES(?, NULL, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET version=excluded.version, risk_tier=excluded.risk_tier, "
                "manifest_json=excluded.manifest_json, status=excluded.status",
                (
                    capability_row_id,
                    tool_id,
                    version,
                    manifest.get("risk_tier", "R0"),
                    payload,
                    manifest.get("availability", "disabled"),
                    now,
                ),
            )
        return {
            "capability_id": capability_id,
            "registry_id": capability_row_id,
            "tool_id": tool_id,
            "version": version,
            "manifest": dict(manifest),
            "status": manifest.get("availability", "disabled"),
        }

    def list_capabilities(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM capabilities ORDER BY tool_id, version"
            ).fetchall()
        return [
            {
                "registry_id": row["id"],
                "tenant_id": row["tenant_id"],
                "tool_id": row["tool_id"],
                "version": row["version"],
                "risk_tier": row["risk_tier"],
                "manifest": json.loads(row["manifest_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def create_pairing_challenge(
        self,
        challenge_id: str,
        device_id: str,
        tenant_id: str,
        principal_id: str,
        device_label: str,
        challenge_hash: str,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a one-time device challenge without persisting its plaintext."""
        if not device_label or len(device_label) > 128:
            raise ValueError("device label must be non-empty and bounded")
        if idempotency_key is not None and (
            not idempotency_key
            or len(idempotency_key) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in idempotency_key)
        ):
            raise ValueError("invalid pairing idempotency key")
        now = _timestamp(_utcnow())
        expires = _timestamp(expires_at)
        if _parse_utc_timestamp(expires, "expires_at") <= _utcnow():
            raise ValueError("pairing challenge must expire in the future")
        record = {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "tenant_id": tenant_id,
            "device_label": device_label,
            "status": "pending",
            "created_at": now,
            "expires_at": expires,
        }
        with self._lock:
            connection = self._conn()
            if idempotency_key is not None:
                existing = connection.execute(
                    "SELECT 1 FROM device_pairing_challenges "
                    "WHERE tenant_id = ? AND idempotency_key = ?",
                    (tenant_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    raise ConflictError("pairing idempotency key has already been used")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO device_pairing_challenges("
                    "id, device_id, tenant_id, principal_id, device_label, challenge_hash, "
                    "idempotency_key, status, created_at, expires_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (
                        challenge_id,
                        device_id,
                        tenant_id,
                        principal_id,
                        device_label,
                        challenge_hash,
                        idempotency_key,
                        now,
                        expires,
                    ),
                )
                payload = {
                    "challenge_id": challenge_id,
                    "device_id": device_id,
                    "device_label": device_label,
                    "status": "pending",
                    "expires_at": expires,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{challenge_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="device.pairing.created",
                    target=device_id,
                    outcome="success",
                    event_type="device.pairing.created",
                    aggregate_kind="device_pairing",
                    aggregate_id=challenge_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raise ConflictError(
                        "pairing challenge conflicts with an existing record"
                    ) from error
                raise
        return record

    def approve_pairing_challenge(
        self,
        device_id: str,
        tenant_id: str,
        principal_id: str,
        challenge: str,
        enrollment_hash: str,
    ) -> Dict[str, Any]:
        """Consume one challenge and enroll exactly one active device."""
        if not challenge or len(challenge) > 512:
            raise ConflictError("pairing challenge is invalid")
        challenge_hash = hash_token(challenge)
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM device_pairing_challenges "
                "WHERE device_id = ? AND tenant_id = ? AND status = 'pending'",
                (device_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("pairing challenge not found")
            if _parse_utc_timestamp(row["expires_at"], "pairing.expires_at") <= _utcnow():
                connection.execute(
                    "UPDATE device_pairing_challenges SET status = 'expired' "
                    "WHERE id = ? AND status = 'pending'",
                    (row["id"],),
                )
                raise ConflictError("pairing challenge expired")
            if not hmac.compare_digest(challenge_hash, row["challenge_hash"]):
                raise ConflictError("pairing challenge is invalid")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO devices(id, tenant_id, label, status, enrollment_hash, created_at) "
                    "VALUES(?, ?, ?, 'active', ?, ?)",
                    (device_id, tenant_id, row["device_label"], enrollment_hash, now),
                )
                connection.execute(
                    "UPDATE device_pairing_challenges SET status = 'approved', used_at = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (now, row["id"]),
                )
                payload = {
                    "device_id": device_id,
                    "device_label": row["device_label"],
                    "status": "active",
                    "challenge_id": row["id"],
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{device_id}:approved:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="device.pairing.approved",
                    target=device_id,
                    outcome="success",
                    event_type="device.pairing.approved",
                    aggregate_kind="device",
                    aggregate_id=device_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_device(device_id, tenant_id)

    @staticmethod
    def _device_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "device_id": row["id"],
            "tenant_id": row["tenant_id"],
            "label": row["label"],
            "status": row["status"],
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
            "revoked_at": row["revoked_at"],
        }

    def get_device(self, device_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM devices WHERE id = ? AND tenant_id = ?",
                (device_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("device not found")
        return self._device_record(row)

    def list_devices(self, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid device limit")
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM devices WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [self._device_record(row) for row in rows]

    def revoke_device(
        self, device_id: str, tenant_id: str, principal_id: str
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM devices WHERE id = ? AND tenant_id = ?",
                (device_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("device not found")
            if row["status"] == "revoked":
                return self._device_record(row)
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE devices SET status = 'revoked', revoked_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND status != 'revoked'",
                    (now, device_id, tenant_id),
                )
                connection.execute(
                    "UPDATE sessions SET status = 'revoked', revoked_at = ? "
                    "WHERE device_id = ? AND tenant_id = ? AND status = 'active'",
                    (now, device_id, tenant_id),
                )
                payload = {"device_id": device_id, "status": "revoked"}
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{device_id}:revoked:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="device.revoked",
                    target=device_id,
                    outcome="success",
                    event_type="device.revoked",
                    aggregate_kind="device",
                    aggregate_id=device_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_device(device_id, tenant_id)

    def create_session(
        self,
        session_id: str,
        tenant_id: str,
        principal_id: str,
        device_id: Optional[str],
        token_hash: str,
        expires_at: datetime,
        scopes: Optional[List[str]] = None,
    ) -> None:
        scope_json = json.dumps(
            sorted(set(scopes or ["workspace:read", "intent:create", "plan:create"])),
            separators=(",", ":"),
        )
        with self._lock:
            connection = self._conn()
            now = _timestamp(_utcnow())
            expires = _timestamp(expires_at)
            payload = {
                "session_id": session_id,
                "device_id": device_id,
                "scopes": json.loads(scope_json),
                "expires_at": expires,
            }
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            event_id = "evt_" + hash_token(
                f"{tenant_id}:{session_id}:{os.urandom(16).hex()}"
            )[:26]
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO sessions("
                    "id, tenant_id, principal_id, device_id, token_hash, scope_json, status, created_at, expires_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                    (
                        session_id,
                        tenant_id,
                        principal_id,
                        device_id,
                        token_hash,
                        scope_json,
                        now,
                        expires,
                    ),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="session.created",
                    target=session_id,
                    outcome="success",
                    event_type="session.created",
                    aggregate_kind="session",
                    aggregate_id=session_id,
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def get_session(self, session_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("session not found")
        if tenant_id is not None and row["tenant_id"] != tenant_id:
            raise ScopeViolation("session is outside tenant scope")
        return dict(row)

    def authenticate_session(self, token: str) -> Optional[Dict[str, Any]]:
        token_hash = hash_token(token)
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM sessions WHERE token_hash = ? AND status = 'active'",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        expires_at = _parse_utc_timestamp(row["expires_at"], "session.expires_at")
        if expires_at <= _utcnow():
            return None
        return dict(row)

    def revoke_session(self, session_id: str) -> None:
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT tenant_id, principal_id, status FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("session not found")
            if row["status"] == "revoked":
                return
            now = _timestamp(_utcnow())
            payload = {"session_id": session_id, "status": "revoked"}
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            event_id = "evt_" + hash_token(
                f"{row['tenant_id']}:{session_id}:{os.urandom(16).hex()}"
            )[:26]
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE sessions SET status = 'revoked', revoked_at = ? WHERE id = ?",
                    (now, session_id),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=row["tenant_id"],
                    actor_kind="principal",
                    actor_id=row["principal_id"],
                    action="session.revoked",
                    target=session_id,
                    outcome="success",
                    event_type="session.revoked",
                    aggregate_kind="session",
                    aggregate_id=session_id,
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def append_audited_event(
        self,
        tenant_id: str,
        actor_kind: str,
        actor_id: str,
        action: str,
        target: str,
        outcome: str,
        event_type: str,
        aggregate_kind: str,
        aggregate_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        now = _timestamp(_utcnow())
        event_id = "evt_" + hash_token(f"{tenant_id}:{now}:{os.urandom(16).hex()}")[:26]
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                event = self._append_audited_event_locked(
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
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return event

    @staticmethod
    def _append_audited_event_locked(
        connection: sqlite3.Connection,
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
    ) -> Dict[str, Any]:
        if visibility not in {"tenant", "workspace", "principal"}:
            raise ValueError("invalid event visibility")
        if not 1 <= schema_version <= 100:
            raise ValueError("invalid event schema version")
        sequence_lock = getattr(connection, "lock_event_sequence", None)
        if sequence_lock is not None:
            sequence_lock(tenant_id)
        audit_id = "aud_" + event_id[4:]
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
            "FROM events WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        sequence = int(row["next_sequence"])
        connection.execute(
            "INSERT INTO audit_records("
            "id, tenant_id, actor_kind, actor_id, action, target, outcome, metadata_json, created_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit_id,
                tenant_id,
                actor_kind,
                actor_id,
                action,
                target,
                outcome,
                payload_json,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO events("
            "id, tenant_id, sequence, type, aggregate_kind, aggregate_id, "
            "actor_kind, actor_id, payload_json, visibility, schema_version, created_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                tenant_id,
                sequence,
                event_type,
                aggregate_kind,
                aggregate_id,
                actor_kind,
                actor_id,
                payload_json,
                visibility,
                schema_version,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO outbox("
            "id, tenant_id, event_id, destination, status, next_attempt_at, attempt_count"
            ") VALUES(?, ?, ?, 'event_stream', 'pending', ?, 0)",
            ("out_" + event_id[4:], tenant_id, event_id, now),
        )
        return {
            "event_id": event_id,
            "tenant_id": tenant_id,
            "sequence": sequence,
            "type": event_type,
            "aggregate": {"kind": aggregate_kind, "id": aggregate_id},
            "actor": {"kind": actor_kind, "id": actor_id},
            "payload": payload,
            "visibility": visibility,
            "schema_version": schema_version,
            "occurred_at": now,
        }

    def create_intent(
        self,
        intent_id: str,
        tenant_id: str,
        principal_id: str,
        source_kind: str,
        source_text: str,
        goal_json: str,
        requested_mode: str,
        requested_risk_tier: str,
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        payload = {
            "intent_id": intent_id,
            "status": "created",
            "requested_risk_tier": requested_risk_tier,
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_id = "evt_" + hash_token(f"{tenant_id}:{intent_id}:{os.urandom(16).hex()}")[:26]
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO intents("
                    "id, tenant_id, principal_id, source_kind, source_text, goal_json, "
                    "requested_mode, requested_risk_tier, status, created_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'created', ?)",
                    (
                        intent_id,
                        tenant_id,
                        principal_id,
                        source_kind,
                        source_text,
                        goal_json,
                        requested_mode,
                        requested_risk_tier,
                        now,
                    ),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="intent.created",
                    target=intent_id,
                    outcome="success",
                    event_type="intent.created",
                    aggregate_kind="intent",
                    aggregate_id=intent_id,
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "source_kind": source_kind,
            "source_text": source_text,
            "goal": json.loads(goal_json),
            "requested_mode": requested_mode,
            "requested_risk_tier": requested_risk_tier,
            "status": "created",
            "created_at": now,
        }

    def get_intent(self, intent_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM intents WHERE id = ?", (intent_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("intent not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("intent is outside tenant scope")
        return {
            "intent_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "source_kind": row["source_kind"],
            "source_text": row["source_text"],
            "goal": json.loads(row["goal_json"]),
            "requested_mode": row["requested_mode"],
            "requested_risk_tier": row["requested_risk_tier"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def create_plan(
        self,
        plan_id: str,
        tenant_id: str,
        principal_id: str,
        intent_id: str,
        digest: str,
        steps_json: str,
        expires_at: datetime,
        scope_digest: str = "",
        status: str = "draft",
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        expires = _timestamp(expires_at)
        payload = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "status": status,
            "digest": digest,
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_id = "evt_" + hash_token(f"{tenant_id}:{plan_id}:{os.urandom(16).hex()}")[:26]
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO plans("
                    "id, tenant_id, principal_id, intent_id, digest, scope_digest, steps_json, status, created_at, expires_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        plan_id,
                        tenant_id,
                        principal_id,
                        intent_id,
                        digest,
                        scope_digest,
                        steps_json,
                        status,
                        now,
                        expires,
                    ),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="plan.created",
                    target=plan_id,
                    outcome="success",
                    event_type="plan.created",
                    aggregate_kind="plan",
                    aggregate_id=plan_id,
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {
            "plan_id": plan_id,
            "tenant_id": tenant_id,
            "principal_id": principal_id,
            "intent_id": intent_id,
            "digest": digest,
            "scope_digest": scope_digest,
            "steps": json.loads(steps_json),
            "status": status,
            "created_at": now,
            "expires_at": expires,
        }

    def get_plan(self, plan_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM plans WHERE id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("plan not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("plan is outside tenant scope")
        return {
            "plan_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "intent_id": row["intent_id"],
            "digest": row["digest"],
            "scope_digest": row["scope_digest"],
            "steps": json.loads(row["steps_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    def transition_plan(
        self,
        plan_id: str,
        tenant_id: str,
        principal_id: str,
        target_status: str,
    ) -> Dict[str, Any]:
        allowed = {
            "draft": {"awaiting_approval", "executing", "expired", "rejected"},
            "awaiting_approval": {"approved", "expired", "rejected"},
            "approved": {"executing", "expired", "rejected", "awaiting_approval"},
            "executing": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
            "expired": set(),
            "rejected": set(),
        }
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM plans WHERE id = ? AND tenant_id = ?",
                (plan_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("plan not found")
            current_status = row["status"]
            if target_status not in allowed.get(current_status, set()):
                raise ConflictError(
                    f"illegal plan transition: {current_status} -> {target_status}"
                )
            now = _timestamp(_utcnow())
            payload = {
                "plan_id": plan_id,
                "from_status": current_status,
                "to_status": target_status,
            }
            event_id = "evt_" + hash_token(
                f"{tenant_id}:{plan_id}:{target_status}:{os.urandom(16).hex()}"
            )[:26]
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE plans SET status = ? WHERE id = ? AND tenant_id = ?",
                    (target_status, plan_id, tenant_id),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action=f"plan.{target_status}",
                    target=plan_id,
                    outcome="success",
                    event_type="plan.updated",
                    aggregate_kind="plan",
                    aggregate_id=plan_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_plan(plan_id, tenant_id)

    @staticmethod
    def _approval_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "approval_id": row["id"],
            "tenant_id": row["tenant_id"],
            "plan_id": row["plan_id"],
            "digest": row["digest"],
            "scope_digest": row["scope_digest"],
            "approver_principal_id": row["approver_id"],
            "required_capability": row["required_capability"],
            "risk_tier": row["risk_tier"],
            "decision": row["decision"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "approved_at": row["approved_at"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
        }

    def approve_plan(
        self,
        approval_id: str,
        plan_id: str,
        tenant_id: str,
        approver_id: str,
        digest: str,
        scope_digest: str,
        required_capability: str,
        risk_tier: str,
        reason: str,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        """Approve one immutable plan digest in the same transaction as its event."""
        if not reason or len(reason) > 2000:
            raise ValueError("approval reason must be non-empty and bounded")
        now = _timestamp(_utcnow())
        expires = _timestamp(expires_at)
        payload = {
            "approval_id": approval_id,
            "plan_id": plan_id,
            "digest": digest,
            "risk_tier": risk_tier,
            "decision": "approved",
            "expires_at": expires,
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._lock:
            connection = self._conn()
            plan = connection.execute(
                "SELECT * FROM plans WHERE id = ? AND tenant_id = ?",
                (plan_id, tenant_id),
            ).fetchone()
            if plan is None:
                raise NotFoundError("plan not found")
            if plan["digest"] != digest or plan["scope_digest"] != scope_digest:
                raise ConflictError("approval binding does not match the plan")
            if _parse_utc_timestamp(plan["expires_at"], "plan.expires_at") <= _utcnow():
                raise ConflictError("plan approval window expired")
            if plan["status"] in {"rejected", "expired", "completed", "failed"}:
                raise ConflictError("plan is not approvable in its current state")
            if _parse_utc_timestamp(expires, "expires_at") <= _utcnow():
                raise ValueError("approval expiry must be in the future")
            existing = connection.execute(
                "SELECT * FROM approvals WHERE plan_id = ? AND tenant_id = ? "
                "AND digest = ? AND scope_digest = ? AND approver_id = ? "
                "AND decision = 'approved' AND revoked_at IS NULL",
                (plan_id, tenant_id, digest, scope_digest, approver_id),
            ).fetchone()
            if existing is not None:
                return self._approval_record(existing)
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO approvals("
                    "id, tenant_id, plan_id, digest, scope_digest, approver_id, "
                    "required_capability, risk_tier, decision, reason, created_at, "
                    "approved_at, expires_at, revoked_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?, NULL)",
                    (
                        approval_id,
                        tenant_id,
                        plan_id,
                        digest,
                        scope_digest,
                        approver_id,
                        required_capability,
                        risk_tier,
                        reason,
                        now,
                        now,
                        expires,
                    ),
                )
                connection.execute(
                    "UPDATE plans SET status = 'approved' WHERE id = ? AND tenant_id = ?",
                    (plan_id, tenant_id),
                )
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{approval_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=approver_id,
                    action="plan.approved",
                    target=plan_id,
                    outcome="success",
                    event_type="approval.approved",
                    aggregate_kind="approval",
                    aggregate_id=approval_id,
                    payload_json=payload_json,
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            row = connection.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError("approval was not persisted")
            return self._approval_record(row)

    def list_approvals(
        self, tenant_id: str, approver_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid approval limit")
        query = "SELECT * FROM approvals WHERE tenant_id = ?"
        parameters: List[Any] = [tenant_id]
        if approver_id is not None:
            query += " AND approver_id = ?"
            parameters.append(approver_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._conn().execute(query, parameters).fetchall()
        return [self._approval_record(row) for row in rows]

    def list_pending_approvals(
        self, tenant_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid pending approval limit")
        now = _timestamp(_utcnow())
        with self._lock:
            rows = self._conn().execute(
                "SELECT id, intent_id, digest, expires_at FROM plans "
                "WHERE tenant_id = ? AND status = 'awaiting_approval' "
                "AND expires_at > ? ORDER BY created_at ASC, id ASC LIMIT ?",
                (tenant_id, now, limit),
            ).fetchall()
        return [
            {
                "plan_id": row["id"],
                "intent_id": row["intent_id"],
                "digest": row["digest"],
                "status": "awaiting_approval",
                "expires_at": row["expires_at"],
                "observed_at": now,
                "source_ref": f"control-plane://tenant/{tenant_id}/plan/{row['id']}",
            }
            for row in rows
        ]

    def get_approval(self, approval_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM approvals WHERE id = ? AND tenant_id = ?",
                (approval_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("approval not found")
        return self._approval_record(row)

    def revoke_approval(
        self, approval_id: str, tenant_id: str, principal_id: str
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM approvals WHERE id = ? AND tenant_id = ?",
                (approval_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("approval not found")
            if row["decision"] != "approved" or row["revoked_at"] is not None:
                raise ConflictError("approval is not revocable")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE approvals SET decision = 'revoked', revoked_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND decision = 'approved'",
                    (now, approval_id, tenant_id),
                )
                connection.execute(
                    "UPDATE plans SET status = 'awaiting_approval' WHERE id = ? "
                    "AND tenant_id = ? AND status = 'approved'",
                    (row["plan_id"], tenant_id),
                )
                payload = {
                    "approval_id": approval_id,
                    "plan_id": row["plan_id"],
                    "decision": "revoked",
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{approval_id}:revoke:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="approval.revoked",
                    target=approval_id,
                    outcome="success",
                    event_type="approval.revoked",
                    aggregate_kind="approval",
                    aggregate_id=approval_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            updated = connection.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            return self._approval_record(updated)

    def has_valid_approval(
        self,
        plan_id: str,
        tenant_id: str,
        digest: str,
        scope_digest: str,
    ) -> bool:
        now = _timestamp(_utcnow())
        with self._lock:
            row = self._conn().execute(
                "SELECT 1 FROM approvals WHERE plan_id = ? AND tenant_id = ? "
                "AND digest = ? AND scope_digest = ? AND decision = 'approved' "
                "AND revoked_at IS NULL AND expires_at > ? LIMIT 1",
                (plan_id, tenant_id, digest, scope_digest, now),
            ).fetchone()
        return row is not None

    def list_audit(
        self, tenant_id: str, limit: int = 100, after: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid audit limit")
        query = "SELECT * FROM audit_records WHERE tenant_id = ?"
        parameters: List[Any] = [tenant_id]
        if after:
            if "|" in after:
                after_created_at, after_id = after.rsplit("|", 1)
                if not after_created_at or not after_id:
                    raise ValueError("invalid audit cursor")
                try:
                    datetime.fromisoformat(after_created_at)
                except ValueError as exc:
                    raise ValueError("invalid audit cursor") from exc
                query += " AND (created_at < ? OR (created_at = ? AND id < ?))"
                parameters.extend([after_created_at, after_created_at, after_id])
            else:
                # Accept the pre-cursor timestamp form during migration. New
                # responses always return the stable timestamp+ID cursor.
                try:
                    datetime.fromisoformat(after)
                except ValueError as exc:
                    raise ValueError("invalid audit cursor") from exc
                query += " AND created_at < ?"
                parameters.append(after)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._conn().execute(query, parameters).fetchall()
        return [
            {
                "audit_id": row["id"],
                "tenant_id": row["tenant_id"],
                "actor": {"kind": row["actor_kind"], "id": row["actor_id"]},
                "action": row["action"],
                "target": row["target"],
                "outcome": row["outcome"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def audit_cursor(record: Dict[str, Any]) -> str:
        """Return a stable cursor that remains deterministic for equal timestamps."""
        created_at = record.get("created_at")
        audit_id = record.get("audit_id")
        if not isinstance(created_at, str) or not isinstance(audit_id, str):
            raise ValueError("audit record does not contain cursor fields")
        return f"{created_at}|{audit_id}"

    def get_evidence(self, evidence_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM evidence WHERE id = ? AND tenant_id = ?",
                (evidence_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("evidence not found")
        provenance = json.loads(row["provenance_json"])
        return {
            "evidence_id": row["id"],
            "tenant_id": row["tenant_id"],
            "kind": row["kind"],
            "status": row["status"],
            "provenance": provenance,
            "result": json.loads(row["result_json"]),
            "artifact_ref": row["artifact_ref"],
            "supersedes": row["supersedes"],
            "created_at": row["created_at"],
        }

    def create_evidence(
        self,
        evidence_id: str,
        tenant_id: str,
        principal_id: str,
        kind: str,
        status: str,
        provenance: Dict[str, Any],
        result: Dict[str, Any],
        artifact_ref: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append immutable evidence and its audit/event record."""
        allowed_statuses = {
            "verified",
            "rejected",
            "unknown",
            "unavailable",
            "simulated",
            "research_only",
        }
        if status not in allowed_statuses:
            raise ValueError("invalid evidence status")
        if not kind or len(kind) > 128:
            raise ValueError("evidence kind is invalid")
        if not isinstance(provenance, dict) or not isinstance(result, dict):
            raise ValueError("evidence provenance and result must be objects")
        provenance_payload = dict(provenance)
        observed_at = provenance_payload.setdefault("observed_at", _timestamp(_utcnow()))
        observed_datetime = _parse_utc_timestamp(observed_at, "observed_at")
        try:
            freshness_seconds = int(provenance_payload.get("freshness_seconds", 60))
        except (TypeError, ValueError):
            freshness_seconds = 60
        freshness_seconds = max(0, min(freshness_seconds, 86_400))
        provenance_payload.setdefault(
            "fresh_until",
            _timestamp(
                observed_datetime
                + timedelta(seconds=freshness_seconds)
            ),
        )
        result_json_for_digest = json.dumps(
            result, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        provenance_payload.setdefault(
            "input_digest", "sha256:" + hash_token(json.dumps(provenance, sort_keys=True, separators=(",", ":")))
        )
        provenance_payload.setdefault(
            "output_digest", "sha256:" + hash_token(result_json_for_digest)
        )
        provenance_payload.setdefault(
            "method_ref", f"procedure.{provenance_payload.get('adapter_id', 'unknown')}.v1"
        )
        provenance_payload.setdefault("artifact_ref", artifact_ref)
        provenance_payload.setdefault(
            "source",
            {
                "adapter_id": provenance_payload.get("adapter_id", "unknown"),
                "adapter_version": provenance_payload.get("adapter_version", "unknown"),
                "origin": provenance_payload.get("origin", "unknown"),
                "input_digest": provenance_payload.get("input_digest"),
            },
        )
        provenance_payload.setdefault("disclosure", "Evidence limitations are recorded by the adapter.")
        result_payload = dict(result)
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            if supersedes is not None:
                parent = connection.execute(
                    "SELECT 1 FROM evidence WHERE id = ? AND tenant_id = ?",
                    (supersedes, tenant_id),
                ).fetchone()
                if parent is None:
                    raise NotFoundError("evidence to supersede not found")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO evidence("
                    "id, tenant_id, kind, status, provenance_json, result_json, artifact_ref, supersedes, created_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        evidence_id,
                        tenant_id,
                        kind,
                        status,
                        json.dumps(provenance_payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
                        json.dumps(result_payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
                        artifact_ref,
                        supersedes,
                        now,
                    ),
                )
                payload = {
                    "evidence_id": evidence_id,
                    "kind": kind,
                    "status": status,
                    "artifact_ref": artifact_ref,
                    "supersedes": supersedes,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{evidence_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="evidence.superseded" if supersedes else "evidence.created",
                    target=evidence_id,
                    outcome="success",
                    event_type="evidence.superseded" if supersedes else "evidence.created",
                    aggregate_kind="evidence",
                    aggregate_id=evidence_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_evidence(evidence_id, tenant_id)

    def list_outbox(self, status: str = "pending", limit: int = 100) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid outbox limit")
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM outbox WHERE status = ? ORDER BY next_attempt_at, id LIMIT ?",
                (status, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_outbox(self, outbox_id: str, lease_seconds: int = 60) -> Optional[Dict[str, Any]]:
        if not 1 <= lease_seconds <= 86_400:
            raise ValueError("invalid outbox lease")
        now = _timestamp(_utcnow())
        lease_until = _timestamp(_utcnow() + timedelta(seconds=lease_seconds))
        claim_token = hash_token(f"outbox:{outbox_id}:{now}:{os.urandom(16).hex()}")
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM outbox WHERE id = ? AND "
                    "((status = 'pending' AND next_attempt_at <= ?) "
                    "OR (status = 'processing' AND lease_until IS NOT NULL AND lease_until <= ?))",
                    (outbox_id, now, now),
                ).fetchone()
                if row is None:
                    connection.execute("ROLLBACK")
                    return None
                connection.execute(
                    "UPDATE outbox SET status = 'processing', attempt_count = attempt_count + 1, "
                    "claimed_at = ?, lease_until = ?, claim_token = ? WHERE id = ? AND ("
                    "(status = 'pending' AND next_attempt_at <= ?) OR "
                    "(status = 'processing' AND lease_until IS NOT NULL AND lease_until <= ?))",
                    (now, lease_until, claim_token, outbox_id, now, now),
                )
                updated = connection.execute(
                    "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return dict(updated) if updated is not None else None
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def finish_outbox(
        self,
        outbox_id: str,
        success: bool,
        retry_at: Optional[datetime] = None,
        error: Optional[str] = None,
        claim_token: Optional[str] = None,
    ) -> None:
        with self._lock:
            claim_filter = " AND claim_token = ?" if claim_token else ""
            if success:
                self._conn().execute(
                    "UPDATE outbox SET status = 'delivered', last_error = NULL, "
                    "claimed_at = NULL, lease_until = NULL, claim_token = NULL "
                    "WHERE id = ? AND status = 'processing'" + claim_filter,
                    (outbox_id, claim_token) if claim_token else (outbox_id,),
                )
            else:
                next_attempt = _timestamp(retry_at or (_utcnow() + timedelta(seconds=30)))
                safe_error = (error or "delivery failed")[:500]
                row = self._conn().execute(
                    "SELECT attempt_count, max_attempts FROM outbox WHERE id = ? AND status = 'processing'"
                    + claim_filter,
                    (outbox_id, claim_token) if claim_token else (outbox_id,),
                ).fetchone()
                if row is None:
                    return
                if int(row["attempt_count"]) >= int(row["max_attempts"]):
                    self._conn().execute(
                        "UPDATE outbox SET status = 'dead_letter', last_error = ?, dead_lettered_at = ? "
                        ", claimed_at = NULL, lease_until = NULL, claim_token = NULL "
                        "WHERE id = ? AND status = 'processing'" + claim_filter,
                        (safe_error, _timestamp(_utcnow()), outbox_id, claim_token)
                        if claim_token
                        else (safe_error, _timestamp(_utcnow()), outbox_id),
                    )
                else:
                    self._conn().execute(
                        "UPDATE outbox SET status = 'pending', next_attempt_at = ?, last_error = ?, "
                        "claimed_at = NULL, lease_until = NULL, claim_token = NULL "
                        "WHERE id = ? AND status = 'processing'" + claim_filter,
                        (next_attempt, safe_error, outbox_id, claim_token)
                        if claim_token
                        else (next_attempt, safe_error, outbox_id),
                    )

    def consume_rate_limit(
        self, tenant_id: str, subject: str, limit: int, window_seconds: int
    ) -> Tuple[bool, int]:
        """Atomically consume one fixed-window token in durable storage."""
        if not subject or not 1 <= limit <= 1_000_000 or not 1 <= window_seconds <= 86_400:
            raise ValueError("invalid rate limit configuration")
        now_seconds = int(time.time())
        bucket = now_seconds // window_seconds
        reset_epoch = (bucket + 1) * window_seconds
        reset_at = datetime.fromtimestamp(reset_epoch, timezone.utc)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT count FROM rate_limits WHERE tenant_id = ? AND subject = ? AND bucket = ?",
                    (tenant_id, subject, bucket),
                ).fetchone()
                count = int(row["count"]) if row is not None else 0
                allowed = count < limit
                if allowed:
                    if row is None:
                        connection.execute(
                            "INSERT INTO rate_limits(tenant_id, subject, bucket, count, reset_at) "
                            "VALUES(?, ?, ?, 1, ?)",
                            (tenant_id, subject, bucket, _timestamp(reset_at)),
                        )
                    else:
                        connection.execute(
                            "UPDATE rate_limits SET count = count + 1 WHERE tenant_id = ? "
                            "AND subject = ? AND bucket = ?",
                            (tenant_id, subject, bucket),
                        )
                    count += 1
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return allowed, max(0, int(reset_epoch - now_seconds))

    def create_artifact(
        self,
        artifact_id: str,
        tenant_id: str,
        principal_id: str,
        digest: str,
        media_type: str,
        size_bytes: int,
        metadata: Dict[str, Any],
        storage_ref: str = "",
    ) -> Dict[str, Any]:
        if not 0 <= size_bytes <= 16 * 1024 * 1024:
            raise ValueError("artifact size is outside the safe bound")
        now = _timestamp(_utcnow())
        record = {
            "artifact_id": artifact_id,
            "digest": digest,
            "media_type": media_type,
            "size_bytes": size_bytes,
            "status": "quarantined",
            "storage_ref": storage_ref or artifact_id,
            "metadata": dict(metadata),
            "created_at": now,
        }
        payload_json = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO artifacts(id, tenant_id, principal_id, digest, media_type, size_bytes, status, storage_ref, metadata_json, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, 'quarantined', ?, ?, ?)",
                    (
                        artifact_id,
                        tenant_id,
                        principal_id,
                        digest,
                        media_type,
                        size_bytes,
                        storage_ref or artifact_id,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False),
                        now,
                    ),
                )
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{artifact_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="artifact.created",
                    target=artifact_id,
                    outcome="success",
                    event_type="artifact.created",
                    aggregate_kind="artifact",
                    aggregate_id=artifact_id,
                    payload_json=payload_json,
                    payload=record,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {"tenant_id": tenant_id, **record}

    def get_artifact(self, artifact_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM artifacts WHERE id = ? AND tenant_id = ?",
                (artifact_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("artifact not found")
        return {
            "artifact_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "digest": row["digest"],
            "media_type": row["media_type"],
            "size_bytes": row["size_bytes"],
            "status": row["status"],
            "storage_ref": row["storage_ref"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _memory_record(row: Any) -> Dict[str, Any]:
        return {
            "memory_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "content": row["content"],
            "scope": row["scope"],
            "memory_type": row["memory_type"],
            "project_id": row["project_id"],
            "source_ref": row["source_ref"],
            "provenance": json.loads(row["provenance_json"]),
            "trust": row["trust"],
            "last_verified_at": row["last_verified_at"],
            "fresh_until": row["fresh_until"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _validate_memory_namespace(value: Optional[str], field_name: str) -> None:
        if value is None:
            return
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        ):
            raise ValueError(f"{field_name} must be non-empty and bounded")

    def create_memory(
        self,
        memory_id: str,
        tenant_id: str,
        principal_id: str,
        content: str,
        scope: str,
        memory_type: str = "conversation",
        project_id: Optional[str] = None,
        source_ref: str = "",
        provenance: Optional[Dict[str, Any]] = None,
        trust: str = "operator",
        last_verified_at: Any = None,
        fresh_until: Any = None,
    ) -> Dict[str, Any]:
        if not isinstance(content, str) or not content.strip() or len(content) > 16_384:
            raise ValueError("memory content must be non-empty and bounded")
        if scope not in {"workspace", "project"}:
            raise ValueError("memory scope must be workspace or project")
        if memory_type not in {
            "core",
            "working",
            "conversation",
            "episodic",
            "semantic",
            "project",
            "tool",
            "audit",
        }:
            raise ValueError("invalid memory type")
        self._validate_memory_namespace(project_id, "project_id")
        if scope == "project" and project_id is None:
            raise ValueError("project memory requires a project_id")
        if scope == "workspace" and project_id is not None:
            raise ValueError("project_id requires project memory scope")
        if memory_type == "project" and project_id is None:
            raise ValueError("project memory requires a project_id")
        if not isinstance(source_ref, str) or len(source_ref) > 512 or any(
            ord(char) < 0x20 or ord(char) == 0x7F for char in source_ref
        ):
            raise ValueError("source_ref is invalid")
        if provenance is None:
            provenance = {}
        if not isinstance(provenance, dict):
            raise ValueError("memory provenance must be an object")
        if trust not in {
            "operator",
            "verified_local",
            "verified_external",
            "inferred",
            "unverified",
        }:
            raise ValueError("invalid memory trust level")
        provenance_json = json.dumps(
            provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        last_verified = _normalize_optional_timestamp(last_verified_at, "last_verified_at")
        expires = _normalize_optional_timestamp(fresh_until, "fresh_until")
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                connection.execute(
                    "INSERT INTO memory_items("
                    "id, tenant_id, principal_id, content, scope, memory_type, project_id, "
                    "source_ref, provenance_json, trust, last_verified_at, fresh_until, "
                    "status, created_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                    (
                        memory_id,
                        tenant_id,
                        principal_id,
                        content,
                        scope,
                        memory_type,
                        project_id,
                        source_ref,
                        provenance_json,
                        trust,
                        last_verified,
                        expires,
                        now,
                    ),
                )
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{memory_id}:{os.urandom(16).hex()}"
                )[:26]
                payload = {
                    "memory_id": memory_id,
                    "scope": scope,
                    "memory_type": memory_type,
                    "project_id": project_id,
                    "source_ref": source_ref,
                    "trust": trust,
                    "fresh_until": expires,
                    "status": "active",
                }
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="memory.created",
                    target=memory_id,
                    outcome="success",
                    event_type="memory.created",
                    aggregate_kind="memory",
                    aggregate_id=memory_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._memory_record(
            {
                "id": memory_id,
                "tenant_id": tenant_id,
                "principal_id": principal_id,
                "content": content,
                "scope": scope,
                "memory_type": memory_type,
                "project_id": project_id,
                "source_ref": source_ref,
                "provenance_json": provenance_json,
                "trust": trust,
                "last_verified_at": last_verified,
                "fresh_until": expires,
                "status": "active",
                "created_at": now,
            }
        )

    def _invalidate_stale_memory_locked(
        self, connection: Any, tenant_id: str, now_value: str
    ) -> int:
        rows = connection.execute(
            "SELECT id, principal_id FROM memory_items WHERE tenant_id = ? "
            "AND status = 'active' AND fresh_until IS NOT NULL AND fresh_until <= ?",
            (tenant_id, now_value),
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE memory_items SET status = 'stale' WHERE id = ? AND tenant_id = ? "
                "AND status = 'active'",
                (row["id"], tenant_id),
            )
            payload = {"memory_id": row["id"], "status": "stale"}
            event_id = "evt_" + hash_token(
                f"{tenant_id}:{row['id']}:stale:{os.urandom(16).hex()}"
            )[:26]
            self._append_audited_event_locked(
                connection=connection,
                tenant_id=tenant_id,
                actor_kind="system",
                actor_id="memory-router",
                action="memory.invalidated",
                target=row["id"],
                outcome="success",
                event_type="memory.invalidated",
                aggregate_kind="memory",
                aggregate_id=row["id"],
                payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                payload=payload,
                now=now_value,
                event_id=event_id,
            )
        return len(rows)

    def invalidate_stale_memory(
        self, tenant_id: str, now: Optional[datetime] = None
    ) -> int:
        now_value = _timestamp(_utcnow() if now is None else now)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                invalidated = self._invalidate_stale_memory_locked(
                    connection, tenant_id, now_value
                )
                connection.execute("COMMIT")
                return invalidated
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def search_memory(
        self,
        tenant_id: str,
        query: str,
        limit: int = 50,
        project_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        include_stale: bool = False,
    ) -> List[Dict[str, Any]]:
        if not isinstance(query, str) or not 1 <= limit <= 100 or len(query) > 256:
            raise ValueError("invalid memory search")
        self._validate_memory_namespace(project_id, "project_id")
        if memory_type is not None and memory_type not in {
            "core",
            "working",
            "conversation",
            "episodic",
            "semantic",
            "project",
            "tool",
            "audit",
        }:
            raise ValueError("invalid memory type")
        now_value = _timestamp(_utcnow())
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._invalidate_stale_memory_locked(connection, tenant_id, now_value)
                statement = (
                    "SELECT * FROM memory_items WHERE tenant_id = ? "
                    "AND status IN ('active', 'stale') "
                    "AND content LIKE ? ESCAPE '\\'"
                )
                parameters: List[Any] = [tenant_id, f"%{escaped_query}%"]
                if not include_stale:
                    statement = statement.replace("status IN ('active', 'stale')", "status = 'active'")
                if project_id is None:
                    statement += " AND project_id IS NULL"
                else:
                    statement += " AND project_id = ?"
                    parameters.append(project_id)
                if memory_type is not None:
                    statement += " AND memory_type = ?"
                    parameters.append(memory_type)
                statement += " ORDER BY created_at DESC, id DESC LIMIT ?"
                parameters.append(limit)
                rows = connection.execute(statement, parameters).fetchall()
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return [self._memory_record(row) for row in rows]

    def delete_memory(self, memory_id: str, tenant_id: str, principal_id: str) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM memory_items WHERE id = ? AND tenant_id = ? "
                "AND status IN ('active', 'stale')",
                (memory_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("memory item not found")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE memory_items SET status = 'deleted', deleted_at = ? WHERE id = ? AND tenant_id = ?",
                    (now, memory_id, tenant_id),
                )
                payload = {"memory_id": memory_id, "status": "deleted"}
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{memory_id}:delete:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="memory.deleted",
                    target=memory_id,
                    outcome="success",
                    event_type="memory.deleted",
                    aggregate_kind="memory",
                    aggregate_id=memory_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {"memory_id": memory_id, "status": "deleted", "deleted_at": now}

    @staticmethod
    def _validate_worker_id(worker_id: str) -> None:
        if (
            not isinstance(worker_id, str)
            or not worker_id
            or len(worker_id) > 128
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in worker_id)
        ):
            raise ValueError("worker_id must be non-empty and bounded")

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> None:
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in idempotency_key)
        ):
            raise ValueError("idempotency_key must be non-empty and bounded")

    @staticmethod
    def _validate_principal_locked(connection: Any, tenant_id: str, principal_id: str) -> None:
        row = connection.execute(
            "SELECT tenant_id, status FROM principals WHERE id = ?", (principal_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("principal not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("principal is outside tenant scope")
        if row["status"] != "active":
            raise ConflictError("principal is not active")

    @staticmethod
    def _goal_record(row: Any) -> Dict[str, Any]:
        return {
            "goal_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "priority": row["priority"],
            "due_at": row["due_at"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    @staticmethod
    def _task_record(
        row: Any,
        dependencies: List[str],
        include_lease_token: bool = False,
    ) -> Dict[str, Any]:
        record = {
            "task_id": row["id"],
            "goal_id": row["goal_id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "title": row["title"],
            "instruction": row["instruction"],
            "status": row["status"],
            "priority": row["priority"],
            "not_before": row["not_before"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "idempotency_key": row["idempotency_key"],
            "lease_until": row["lease_until"],
            "dependencies": dependencies,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
            "result": json.loads(row["result_json"]),
        }
        if include_lease_token:
            record["lease_token"] = row["lease_token"]
        return record

    @staticmethod
    def _task_dependencies_locked(connection: Any, task_id: str, tenant_id: str) -> List[str]:
        rows = connection.execute(
            "SELECT depends_on_task_id FROM task_dependencies "
            "WHERE task_id = ? AND tenant_id = ? ORDER BY depends_on_task_id",
            (task_id, tenant_id),
        ).fetchall()
        return [row["depends_on_task_id"] for row in rows]

    def create_goal(
        self,
        goal_id: str,
        tenant_id: str,
        principal_id: str,
        title: str,
        description: str = "",
        priority: int = 50,
        due_at: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            raise ValueError("goal title must be non-empty and bounded")
        if not isinstance(description, str) or len(description) > 4096:
            raise ValueError("goal description is too long")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
            raise ValueError("goal priority must be between 0 and 100")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("goal metadata must be an object")
        metadata_json = json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        due = _normalize_optional_timestamp(due_at, "due_at")
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                connection.execute(
                    "INSERT INTO goals("
                    "id, tenant_id, principal_id, title, description, status, priority, due_at, "
                    "metadata_json, created_at, updated_at"
                    ") VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)",
                    (
                        goal_id,
                        tenant_id,
                        principal_id,
                        title,
                        description,
                        priority,
                        due,
                        metadata_json,
                        now,
                        now,
                    ),
                )
                payload = {
                    "goal_id": goal_id,
                    "status": "active",
                    "priority": priority,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{goal_id}:created:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="goal.created",
                    target=goal_id,
                    outcome="success",
                    event_type="goal.created",
                    aggregate_kind="goal",
                    aggregate_id=goal_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raise ConflictError("goal conflicts with an existing record") from error
                raise
        return self.get_goal(goal_id, tenant_id)

    def get_goal(self, goal_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM goals WHERE id = ?", (goal_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("goal not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("goal is outside tenant scope")
        return self._goal_record(row)

    def list_goals(
        self, tenant_id: str, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid goal limit")
        if status is not None and status not in {"active", "completed", "cancelled"}:
            raise ValueError("invalid goal status")
        statement = "SELECT * FROM goals WHERE tenant_id = ?"
        parameters: List[Any] = [tenant_id]
        if status is not None:
            statement += " AND status = ?"
            parameters.append(status)
        statement += " ORDER BY priority, created_at, id LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._conn().execute(statement, parameters).fetchall()
        return [self._goal_record(row) for row in rows]

    def create_task(
        self,
        task_id: str,
        goal_id: str,
        tenant_id: str,
        principal_id: str,
        title: str,
        instruction: str,
        idempotency_key: str,
        priority: int = 50,
        not_before: Any = None,
        max_attempts: int = 3,
        depends_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            raise ValueError("task title must be non-empty and bounded")
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 16_384:
            raise ValueError("task instruction must be non-empty and bounded")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
            raise ValueError("task priority must be between 0 and 100")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self._validate_idempotency_key(idempotency_key)
        not_before_value = _normalize_optional_timestamp(not_before, "not_before")
        dependency_ids = list(depends_on or [])
        if len(dependency_ids) > 64:
            raise ValueError("a task cannot have more than 64 dependencies")
        if len(set(dependency_ids)) != len(dependency_ids):
            raise ValueError("task dependencies must be unique")
        for dependency_id in dependency_ids:
            if (
                not isinstance(dependency_id, str)
                or not dependency_id
                or len(dependency_id) > 128
                or any(ord(char) < 0x20 or ord(char) == 0x7F for char in dependency_id)
            ):
                raise ValueError("task dependency identifiers are invalid")
        if task_id in dependency_ids:
            raise ValueError("a task cannot depend on itself")
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                goal = connection.execute(
                    "SELECT tenant_id, status FROM goals WHERE id = ?", (goal_id,)
                ).fetchone()
                if goal is None:
                    raise NotFoundError("goal not found")
                if goal["tenant_id"] != tenant_id:
                    raise ScopeViolation("goal is outside tenant scope")
                if goal["status"] != "active":
                    raise ConflictError("tasks cannot be added to an inactive goal")
                if dependency_ids:
                    placeholders = ",".join("?" for _ in dependency_ids)
                    dependency_rows = connection.execute(
                        "SELECT id, tenant_id, goal_id FROM tasks "
                        f"WHERE id IN ({placeholders})",
                        dependency_ids,
                    ).fetchall()
                    dependencies_by_id = {row["id"]: row for row in dependency_rows}
                    for dependency_id in dependency_ids:
                        dependency = dependencies_by_id.get(dependency_id)
                        if dependency is None:
                            raise NotFoundError("task dependency not found")
                        if dependency["tenant_id"] != tenant_id:
                            raise ScopeViolation("task dependency is outside tenant scope")
                        if dependency["goal_id"] != goal_id:
                            raise ConflictError("task dependency belongs to another goal")
                connection.execute(
                    "INSERT INTO tasks("
                    "id, goal_id, tenant_id, principal_id, title, instruction, status, priority, "
                    "not_before, attempt_count, max_attempts, idempotency_key, created_at, updated_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, 'queued', ?, ?, 0, ?, ?, ?, ?)",
                    (
                        task_id,
                        goal_id,
                        tenant_id,
                        principal_id,
                        title,
                        instruction,
                        priority,
                        not_before_value,
                        max_attempts,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
                for dependency_id in dependency_ids:
                    connection.execute(
                        "INSERT INTO task_dependencies(tenant_id, task_id, depends_on_task_id) "
                        "VALUES(?, ?, ?)",
                        (tenant_id, task_id, dependency_id),
                    )
                payload = {
                    "task_id": task_id,
                    "goal_id": goal_id,
                    "status": "queued",
                    "priority": priority,
                    "dependencies": dependency_ids,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{task_id}:created:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="task.created",
                    target=task_id,
                    outcome="success",
                    event_type="task.created",
                    aggregate_kind="task",
                    aggregate_id=task_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raise ConflictError("task conflicts with an existing record") from error
                raise
        return self.get_task(task_id, tenant_id)

    def get_task(self, task_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("task not found")
            if row["tenant_id"] != tenant_id:
                raise ScopeViolation("task is outside tenant scope")
            dependencies = self._task_dependencies_locked(connection, task_id, tenant_id)
        return self._task_record(row, dependencies)

    def list_tasks(self, goal_id: str, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid task limit")
        with self._lock:
            connection = self._conn()
            goal = connection.execute(
                "SELECT tenant_id FROM goals WHERE id = ?", (goal_id,)
            ).fetchone()
            if goal is None:
                raise NotFoundError("goal not found")
            if goal["tenant_id"] != tenant_id:
                raise ScopeViolation("goal is outside tenant scope")
            rows = connection.execute(
                "SELECT * FROM tasks WHERE goal_id = ? AND tenant_id = ? "
                "ORDER BY priority, created_at, id LIMIT ?",
                (goal_id, tenant_id, limit),
            ).fetchall()
            records = [
                self._task_record(
                    row,
                    self._task_dependencies_locked(connection, row["id"], tenant_id),
                )
                for row in rows
            ]
        return records

    def claim_due_task(
        self,
        task_id: str,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        self._validate_worker_id(worker_id)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        now_dt = _utcnow() if now is None else now
        if not isinstance(now_dt, datetime) or now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=lease_seconds))
        lease_token = hash_token(
            f"{tenant_id}:{task_id}:{worker_id}:{now_value}:{os.urandom(32).hex()}"
        )
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError("task not found")
                if row["tenant_id"] != tenant_id:
                    raise ScopeViolation("task is outside tenant scope")
                lease_expired = (
                    row["status"] == "running"
                    and row["lease_until"] is not None
                    and row["lease_until"] <= now_value
                )
                claimable_status = row["status"] in {"queued", "retry"} or lease_expired
                not_before_passed = row["not_before"] is None or row["not_before"] <= now_value
                dependencies_pending = connection.execute(
                    "SELECT COUNT(*) AS count FROM task_dependencies d "
                    "JOIN tasks dependency ON dependency.id = d.depends_on_task_id "
                    "WHERE d.tenant_id = ? AND d.task_id = ? AND dependency.status != 'completed'",
                    (tenant_id, task_id),
                ).fetchone()
                eligible = (
                    claimable_status
                    and not_before_passed
                    and int(row["attempt_count"]) < int(row["max_attempts"])
                    and int(dependencies_pending["count"]) == 0
                )
                if not eligible:
                    connection.execute("ROLLBACK")
                    return None
                updated = connection.execute(
                    "UPDATE tasks SET status = 'running', attempt_count = attempt_count + 1, "
                    "lease_owner = ?, lease_token = ?, lease_until = ?, updated_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND attempt_count < max_attempts AND "
                    "(status IN ('queued', 'retry') OR "
                    "(status = 'running' AND lease_until IS NOT NULL AND lease_until <= ?)) AND "
                    "(not_before IS NULL OR not_before <= ?)",
                    (
                        worker_id,
                        lease_token,
                        lease_until,
                        now_value,
                        task_id,
                        tenant_id,
                        now_value,
                        now_value,
                    ),
                )
                if getattr(updated, "rowcount", 1) != 1:
                    connection.execute("ROLLBACK")
                    return None
                claimed = connection.execute(
                    "SELECT * FROM tasks WHERE id = ? AND tenant_id = ?",
                    (task_id, tenant_id),
                ).fetchone()
                attempt_count = int(claimed["attempt_count"])
                task_run_id = "trun_" + hash_token(
                    f"{tenant_id}:{task_id}:manual:{attempt_count}:{os.urandom(32).hex()}"
                )[:26]
                connection.execute(
                    "INSERT INTO task_runs("
                    "id, tenant_id, goal_id, task_id, occurrence_key, idempotency_key, "
                    "status, attempt_count, max_attempts, worker_id, lease_token, lease_until, "
                    "scheduled_for, created_at, started_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        task_run_id,
                        tenant_id,
                        claimed["goal_id"],
                        task_id,
                        f"manual:{attempt_count}",
                        f"task:{task_id}:attempt:{attempt_count}",
                        attempt_count,
                        claimed["max_attempts"],
                        worker_id,
                        lease_token,
                        lease_until,
                        now_value,
                        now_value,
                        now_value,
                    ),
                )
                payload = {
                    "task_id": task_id,
                    "task_run_id": task_run_id,
                    "status": "running",
                    "attempt_count": attempt_count,
                    "lease_until": lease_until,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{task_id}:claimed:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action="task.claimed",
                    target=task_id,
                    outcome="success",
                    event_type="task.claimed",
                    aggregate_kind="task",
                    aggregate_id=task_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now_value,
                    event_id=event_id,
                )
                record = self._task_record(
                    claimed,
                    self._task_dependencies_locked(connection, task_id, tenant_id),
                    include_lease_token=True,
                )
                record["task_run_id"] = task_run_id
                connection.execute("COMMIT")
                return record
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def complete_task(
        self,
        task_id: str,
        tenant_id: str,
        worker_id: str,
        lease_token: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._validate_worker_id(worker_id)
        if not isinstance(lease_token, str) or not lease_token or len(lease_token) > 512:
            raise ValueError("lease_token is invalid")
        if not isinstance(result, dict):
            raise ValueError("task result must be an object")
        result_json = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError("task not found")
                if row["tenant_id"] != tenant_id:
                    raise ScopeViolation("task is outside tenant scope")
                if row["status"] != "running":
                    raise ConflictError("task is not running")
                if row["lease_until"] is None or row["lease_until"] <= now:
                    raise ConflictError("task lease has expired")
                if not hmac.compare_digest(str(row["lease_owner"] or ""), worker_id):
                    raise ConflictError("task lease belongs to another worker")
                if not hmac.compare_digest(str(row["lease_token"] or ""), lease_token):
                    raise ConflictError("task lease token is invalid")
                task_run = connection.execute(
                    "SELECT * FROM task_runs WHERE task_id = ? AND tenant_id = ? "
                    "AND status = 'running' AND worker_id = ? AND lease_token = ? "
                    "ORDER BY attempt_count DESC, created_at DESC LIMIT 1",
                    (task_id, tenant_id, worker_id, lease_token),
                ).fetchone()
                updated = connection.execute(
                    "UPDATE tasks SET status = 'completed', result_json = ?, completed_at = ?, "
                    "updated_at = ?, lease_owner = NULL, lease_token = NULL, lease_until = NULL "
                    "WHERE id = ? AND tenant_id = ? AND status = 'running' "
                    "AND lease_owner = ? AND lease_token = ?",
                    (result_json, now, now, task_id, tenant_id, worker_id, lease_token),
                )
                if getattr(updated, "rowcount", 1) != 1:
                    raise ConflictError("task lease is no longer valid")
                if task_run is not None:
                    connection.execute(
                        "UPDATE task_runs SET status = 'succeeded', result_json = ?, "
                        "worker_id = NULL, lease_token = NULL, lease_until = NULL, "
                        "finished_at = ? WHERE id = ? AND tenant_id = ? AND status = 'running'",
                        (result_json, now, task_run["id"], tenant_id),
                    )
                payload = {
                    "task_id": task_id,
                    "task_run_id": task_run["id"] if task_run is not None else None,
                    "status": "completed",
                    "attempt_count": int(row["attempt_count"]),
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{task_id}:completed:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action="task.completed",
                    target=task_id,
                    outcome="success",
                    event_type="task.completed",
                    aggregate_kind="task",
                    aggregate_id=task_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                goal = connection.execute(
                    "SELECT id, status FROM goals WHERE id = ? AND tenant_id = ?",
                    (row["goal_id"], tenant_id),
                ).fetchone()
                total_tasks = connection.execute(
                    "SELECT COUNT(*) AS count FROM tasks WHERE goal_id = ? AND tenant_id = ?",
                    (row["goal_id"], tenant_id),
                ).fetchone()
                incomplete_tasks = connection.execute(
                    "SELECT COUNT(*) AS count FROM tasks WHERE goal_id = ? AND tenant_id = ? "
                    "AND status != 'completed'",
                    (row["goal_id"], tenant_id),
                ).fetchone()
                if (
                    goal is not None
                    and goal["status"] == "active"
                    and int(total_tasks["count"]) > 0
                    and int(incomplete_tasks["count"]) == 0
                ):
                    connection.execute(
                        "UPDATE goals SET status = 'completed', completed_at = ?, updated_at = ? "
                        "WHERE id = ? AND tenant_id = ? AND status = 'active'",
                        (now, now, row["goal_id"], tenant_id),
                    )
                    goal_payload = {
                        "goal_id": row["goal_id"],
                        "status": "completed",
                    }
                    goal_event_id = "evt_" + hash_token(
                        f"{tenant_id}:{row['goal_id']}:completed:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="worker",
                        actor_id=worker_id,
                        action="goal.completed",
                        target=row["goal_id"],
                        outcome="success",
                        event_type="goal.completed",
                        aggregate_kind="goal",
                        aggregate_id=row["goal_id"],
                        payload_json=json.dumps(
                            goal_payload, sort_keys=True, separators=(",", ":")
                        ),
                        payload=goal_payload,
                        now=now,
                        event_id=goal_event_id,
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        record = self.get_task(task_id, tenant_id)
        if task_run is not None:
            record["task_run_id"] = task_run["id"]
        return record

    @staticmethod
    def _schedule_record(row: Any) -> Dict[str, Any]:
        return {
            "schedule_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "task_id": row["task_id"],
            "kind": row["kind"],
            "status": row["status"],
            "next_run_at": row["next_run_at"],
            "interval_seconds": row["interval_seconds"],
            "misfire_policy": row["misfire_policy"],
            "idempotency_key": row["idempotency_key"],
            "last_run_at": row["last_run_at"],
            "run_count": row["run_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "cancelled_at": row["cancelled_at"],
        }

    @staticmethod
    def _task_run_record(row: Any, include_lease_token: bool = False) -> Dict[str, Any]:
        record = {
            "run_id": row["id"],
            "tenant_id": row["tenant_id"],
            "goal_id": row["goal_id"],
            "task_id": row["task_id"],
            "schedule_id": row["schedule_id"],
            "occurrence_key": row["occurrence_key"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "worker_id": row["worker_id"],
            "lease_until": row["lease_until"],
            "scheduled_for": row["scheduled_for"],
            "result": json.loads(row["result_json"]),
            "error": json.loads(row["error_json"]),
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }
        if include_lease_token:
            record["lease_token"] = row["lease_token"]
        return record

    @staticmethod
    def _required_timestamp(value: Any, field_name: str) -> str:
        normalized = _normalize_optional_timestamp(value, field_name)
        if normalized is None:
            raise ValueError(f"{field_name} is required")
        return normalized

    @staticmethod
    def _next_interval_run(
        scheduled_for: datetime,
        now: datetime,
        interval_seconds: int,
        misfire_policy: str,
    ) -> str:
        if misfire_policy == "run_once":
            return _timestamp(now + timedelta(seconds=interval_seconds))
        elapsed_seconds = max(0, (now - scheduled_for).total_seconds())
        intervals = max(1, int(elapsed_seconds // interval_seconds) + 1)
        return _timestamp(scheduled_for + timedelta(seconds=intervals * interval_seconds))

    def create_schedule(
        self,
        schedule_id: str,
        tenant_id: str,
        principal_id: str,
        task_id: str,
        kind: str,
        next_run_at: Any,
        idempotency_key: str,
        interval_seconds: Optional[int] = None,
        misfire_policy: str = "skip",
    ) -> Dict[str, Any]:
        if (
            not isinstance(schedule_id, str)
            or not schedule_id
            or len(schedule_id) > 128
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in schedule_id)
        ):
            raise ValueError("schedule_id must be non-empty and bounded")
        if kind not in {"once", "interval"}:
            raise ValueError("schedule kind must be once or interval")
        if misfire_policy not in {"skip", "run_once"}:
            raise ValueError("invalid misfire policy")
        if kind == "interval":
            if (
                isinstance(interval_seconds, bool)
                or not isinstance(interval_seconds, int)
                or not 1 <= interval_seconds <= 31_536_000
            ):
                raise ValueError("interval schedules require a bounded interval_seconds")
        elif interval_seconds is not None:
            raise ValueError("once schedules must not specify interval_seconds")
        self._validate_idempotency_key(idempotency_key)
        next_run = self._required_timestamp(next_run_at, "next_run_at")
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                task = connection.execute(
                    "SELECT goal_id, tenant_id FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if task is None:
                    raise NotFoundError("task not found")
                if task["tenant_id"] != tenant_id:
                    raise ScopeViolation("task is outside tenant scope")
                connection.execute(
                    "INSERT INTO schedules("
                    "id, tenant_id, principal_id, task_id, kind, status, next_run_at, "
                    "interval_seconds, misfire_policy, idempotency_key, created_at, updated_at"
                    ") VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)",
                    (
                        schedule_id,
                        tenant_id,
                        principal_id,
                        task_id,
                        kind,
                        next_run,
                        interval_seconds,
                        misfire_policy,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
                payload = {
                    "schedule_id": schedule_id,
                    "task_id": task_id,
                    "kind": kind,
                    "status": "active",
                    "next_run_at": next_run,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{schedule_id}:created:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="schedule.created",
                    target=schedule_id,
                    outcome="success",
                    event_type="schedule.created",
                    aggregate_kind="schedule",
                    aggregate_id=schedule_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raise ConflictError("schedule conflicts with an existing record") from error
                raise
        return self.get_schedule(schedule_id, tenant_id)

    def get_schedule(self, schedule_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("schedule not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("schedule is outside tenant scope")
        return self._schedule_record(row)

    def list_schedules(
        self,
        tenant_id: str,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        goal_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid schedule limit")
        if status is not None and status not in {
            "active",
            "running",
            "completed",
            "failed",
            "cancelled",
        }:
            raise ValueError("invalid schedule status")
        statement = "SELECT schedules.* FROM schedules WHERE schedules.tenant_id = ?"
        parameters: List[Any] = [tenant_id]
        if task_id is not None:
            statement += " AND schedules.task_id = ?"
            parameters.append(task_id)
        if goal_id is not None:
            with self._lock:
                goal = self._conn().execute(
                    "SELECT tenant_id FROM goals WHERE id = ?", (goal_id,)
                ).fetchone()
            if goal is None:
                raise NotFoundError("goal not found")
            if goal["tenant_id"] != tenant_id:
                raise ScopeViolation("goal is outside tenant scope")
            statement += (
                " AND schedules.task_id IN (SELECT id FROM tasks "
                "WHERE goal_id = ? AND tenant_id = ?)"
            )
            parameters.extend([goal_id, tenant_id])
        if status is not None:
            statement += " AND schedules.status = ?"
            parameters.append(status)
        statement += " ORDER BY schedules.next_run_at, schedules.id LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._conn().execute(statement, parameters).fetchall()
        return [self._schedule_record(row) for row in rows]

    def cancel_schedule(
        self, schedule_id: str, tenant_id: str, principal_id: str
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                schedule = connection.execute(
                    "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
                ).fetchone()
                if schedule is None:
                    raise NotFoundError("schedule not found")
                if schedule["tenant_id"] != tenant_id:
                    raise ScopeViolation("schedule is outside tenant scope")
                if schedule["status"] == "cancelled":
                    connection.execute("COMMIT")
                    return self._schedule_record(schedule)
                if schedule["status"] in {"completed", "failed"}:
                    raise ConflictError("schedule is already terminal")
                connection.execute(
                    "UPDATE schedules SET status = 'cancelled', cancelled_at = ?, updated_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND status IN ('active', 'running')",
                    (now, now, schedule_id, tenant_id),
                )
                running_runs = connection.execute(
                    "SELECT id FROM task_runs WHERE schedule_id = ? AND tenant_id = ? "
                    "AND status = 'running'",
                    (schedule_id, tenant_id),
                ).fetchall()
                for running_run in running_runs:
                    connection.execute(
                        "UPDATE task_runs SET status = 'cancelled', worker_id = NULL, "
                        "lease_token = NULL, lease_until = NULL, finished_at = ? "
                        "WHERE id = ? AND tenant_id = ? AND status = 'running'",
                        (now, running_run["id"], tenant_id),
                    )
                    run_payload = {
                        "run_id": running_run["id"],
                        "schedule_id": schedule_id,
                        "status": "cancelled",
                    }
                    run_event_id = "evt_" + hash_token(
                        f"{tenant_id}:{running_run['id']}:cancelled:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="principal",
                        actor_id=principal_id,
                        action="task_run.cancelled",
                        target=running_run["id"],
                        outcome="success",
                        event_type="task_run.cancelled",
                        aggregate_kind="task_run",
                        aggregate_id=running_run["id"],
                        payload_json=json.dumps(
                            run_payload, sort_keys=True, separators=(",", ":")
                        ),
                        payload=run_payload,
                        now=now,
                        event_id=run_event_id,
                    )
                payload = {"schedule_id": schedule_id, "status": "cancelled"}
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{schedule_id}:cancelled:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="schedule.cancelled",
                    target=schedule_id,
                    outcome="success",
                    event_type="schedule.cancelled",
                    aggregate_kind="schedule",
                    aggregate_id=schedule_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                current = connection.execute(
                    "SELECT * FROM schedules WHERE id = ? AND tenant_id = ?",
                    (schedule_id, tenant_id),
                ).fetchone()
                connection.execute("COMMIT")
                return self._schedule_record(current)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _task_run_by_id_locked(
        self, connection: Any, run_id: str, tenant_id: str
    ) -> Any:
        row = connection.execute(
            "SELECT * FROM task_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("task run not found")
        if row["tenant_id"] != tenant_id:
            raise ScopeViolation("task run is outside tenant scope")
        return row

    def get_task_run(self, run_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._task_run_by_id_locked(self._conn(), run_id, tenant_id)
        return self._task_run_record(row)

    def list_task_runs(
        self, task_id: str, tenant_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid task run limit")
        with self._lock:
            connection = self._conn()
            task = connection.execute(
                "SELECT tenant_id FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if task is None:
                raise NotFoundError("task not found")
            if task["tenant_id"] != tenant_id:
                raise ScopeViolation("task is outside tenant scope")
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE task_id = ? AND tenant_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (task_id, tenant_id, limit),
            ).fetchall()
        return [self._task_run_record(row) for row in rows]

    def claim_due_schedule(
        self,
        schedule_id: str,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        self._validate_worker_id(worker_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 3600
        ):
            raise ValueError("lease_seconds must be between 1 and 3600")
        now_dt = _utcnow() if now is None else now
        if not isinstance(now_dt, datetime) or now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=lease_seconds))
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                schedule = connection.execute(
                    "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
                ).fetchone()
                if schedule is None:
                    raise NotFoundError("schedule not found")
                if schedule["tenant_id"] != tenant_id:
                    raise ScopeViolation("schedule is outside tenant scope")
                if schedule["status"] != "active" or schedule["next_run_at"] > now_value:
                    connection.execute("ROLLBACK")
                    return None
                task = connection.execute(
                    "SELECT * FROM tasks WHERE id = ? AND tenant_id = ?",
                    (schedule["task_id"], tenant_id),
                ).fetchone()
                if task is None:
                    raise NotFoundError("scheduled task not found")
                pending = connection.execute(
                    "SELECT COUNT(*) AS count FROM task_dependencies d "
                    "JOIN tasks dependency ON dependency.id = d.depends_on_task_id "
                    "WHERE d.tenant_id = ? AND d.task_id = ? "
                    "AND dependency.status != 'completed'",
                    (tenant_id, task["id"]),
                ).fetchone()
                if int(pending["count"]) != 0:
                    connection.execute("ROLLBACK")
                    return None
                running = connection.execute(
                    "SELECT id FROM task_runs WHERE tenant_id = ? AND schedule_id = ? "
                    "AND status = 'running' LIMIT 1",
                    (tenant_id, schedule_id),
                ).fetchone()
                if running is not None:
                    connection.execute("ROLLBACK")
                    return None
                occurrence_key = schedule["next_run_at"]
                existing = connection.execute(
                    "SELECT id FROM task_runs WHERE tenant_id = ? AND schedule_id = ? "
                    "AND occurrence_key = ?",
                    (tenant_id, schedule_id, occurrence_key),
                ).fetchone()
                if existing is not None:
                    connection.execute("ROLLBACK")
                    return None
                lease_token = hash_token(
                    f"{tenant_id}:{schedule_id}:{worker_id}:{now_value}:{os.urandom(32).hex()}"
                )
                run_id = "trun_" + hash_token(
                    f"{tenant_id}:{schedule_id}:{occurrence_key}:{os.urandom(32).hex()}"
                )[:26]
                run_idempotency_key = f"schedule:{schedule_id}:{occurrence_key}"
                connection.execute(
                    "INSERT INTO task_runs("
                    "id, tenant_id, goal_id, task_id, schedule_id, occurrence_key, "
                    "idempotency_key, status, attempt_count, max_attempts, worker_id, "
                    "lease_token, lease_until, scheduled_for, created_at, started_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, 'running', 1, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        tenant_id,
                        task["goal_id"],
                        task["id"],
                        schedule_id,
                        occurrence_key,
                        run_idempotency_key,
                        task["max_attempts"],
                        worker_id,
                        lease_token,
                        lease_until,
                        occurrence_key,
                        now_value,
                        now_value,
                    ),
                )
                if schedule["kind"] == "interval":
                    next_run = self._next_interval_run(
                        _parse_utc_timestamp(occurrence_key, "next_run_at"),
                        now_dt.astimezone(timezone.utc),
                        int(schedule["interval_seconds"]),
                        schedule["misfire_policy"],
                    )
                else:
                    next_run = occurrence_key
                connection.execute(
                    "UPDATE schedules SET status = ?, next_run_at = ?, last_run_at = ?, "
                    "run_count = run_count + 1, updated_at = ? WHERE id = ? AND tenant_id = ?",
                    (
                        "active" if schedule["kind"] == "interval" else "running",
                        next_run,
                        occurrence_key,
                        now_value,
                        schedule_id,
                        tenant_id,
                    ),
                )
                payload = {
                    "schedule_id": schedule_id,
                    "task_id": task["id"],
                    "run_id": run_id,
                    "status": "running",
                    "attempt_count": 1,
                    "scheduled_for": occurrence_key,
                    "lease_until": lease_until,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:claimed:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action="task_run.claimed",
                    target=run_id,
                    outcome="success",
                    event_type="task_run.claimed",
                    aggregate_kind="task_run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now_value,
                    event_id=event_id,
                )
                current_schedule = connection.execute(
                    "SELECT * FROM schedules WHERE id = ? AND tenant_id = ?",
                    (schedule_id, tenant_id),
                ).fetchone()
                current_run = connection.execute(
                    "SELECT * FROM task_runs WHERE id = ? AND tenant_id = ?",
                    (run_id, tenant_id),
                ).fetchone()
                connection.execute("COMMIT")
                return {
                    "schedule": self._schedule_record(current_schedule),
                    "run": self._task_run_record(current_run, include_lease_token=True),
                }
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    return None
                raise

    def claim_task_run(
        self,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        self._validate_worker_id(worker_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 3600
        ):
            raise ValueError("lease_seconds must be between 1 and 3600")
        now_dt = _utcnow() if now is None else now
        if not isinstance(now_dt, datetime) or now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=lease_seconds))
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._task_run_by_id_locked(connection, run_id, tenant_id)
                expired = (
                    row["status"] == "running"
                    and row["lease_until"] is not None
                    and row["lease_until"] <= now_value
                )
                if row["status"] not in {"queued", "retry"} and not expired:
                    connection.execute("ROLLBACK")
                    return None
                next_attempt = int(row["attempt_count"]) + 1
                if next_attempt > int(row["max_attempts"]):
                    connection.execute(
                        "UPDATE task_runs SET status = 'dead_lettered', worker_id = NULL, "
                        "lease_token = NULL, lease_until = NULL, finished_at = ? "
                        "WHERE id = ? AND tenant_id = ?",
                        (now_value, run_id, tenant_id),
                    )
                    if row["schedule_id"] is not None:
                        schedule = connection.execute(
                            "SELECT kind FROM schedules WHERE id = ? AND tenant_id = ?",
                            (row["schedule_id"], tenant_id),
                        ).fetchone()
                        if schedule is not None and schedule["kind"] == "once":
                            connection.execute(
                                "UPDATE schedules SET status = 'failed', updated_at = ? "
                                "WHERE id = ? AND tenant_id = ? AND status IN ('active', 'running')",
                                (now_value, row["schedule_id"], tenant_id),
                            )
                    connection.execute(
                        "UPDATE tasks SET status = 'failed', lease_owner = NULL, "
                        "lease_token = NULL, lease_until = NULL, updated_at = ? "
                        "WHERE id = ? AND tenant_id = ? AND status IN ('queued', 'running', 'retry')",
                        (now_value, row["task_id"], tenant_id),
                    )
                    payload = {
                        "run_id": run_id,
                        "task_id": row["task_id"],
                        "schedule_id": row["schedule_id"],
                        "status": "dead_lettered",
                        "attempt_count": int(row["attempt_count"]),
                    }
                    event_id = "evt_" + hash_token(
                        f"{tenant_id}:{run_id}:dead_lettered:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="worker",
                        actor_id=worker_id,
                        action="task_run.dead_lettered",
                        target=run_id,
                        outcome="dead_lettered",
                        event_type="task_run.dead_lettered",
                        aggregate_kind="task_run",
                        aggregate_id=run_id,
                        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        payload=payload,
                        now=now_value,
                        event_id=event_id,
                    )
                    connection.execute("COMMIT")
                    return None
                lease_token = hash_token(
                    f"{tenant_id}:{run_id}:{worker_id}:{now_value}:{os.urandom(32).hex()}"
                )
                updated = connection.execute(
                    "UPDATE task_runs SET status = 'running', attempt_count = ?, worker_id = ?, "
                    "lease_token = ?, lease_until = ?, started_at = COALESCE(started_at, ?), "
                    "finished_at = NULL WHERE id = ? AND tenant_id = ?",
                    (
                        next_attempt,
                        worker_id,
                        lease_token,
                        lease_until,
                        now_value,
                        run_id,
                        tenant_id,
                    ),
                )
                if getattr(updated, "rowcount", 1) != 1:
                    connection.execute("ROLLBACK")
                    return None
                if row["schedule_id"] is None:
                    connection.execute(
                        "UPDATE tasks SET status = 'running', lease_owner = ?, lease_token = ?, "
                        "lease_until = ?, updated_at = ? WHERE id = ? AND tenant_id = ? "
                        "AND status IN ('queued', 'retry', 'running')",
                        (
                            worker_id,
                            lease_token,
                            lease_until,
                            now_value,
                            row["task_id"],
                            tenant_id,
                        ),
                    )
                payload = {
                    "run_id": run_id,
                    "task_id": row["task_id"],
                    "status": "running",
                    "attempt_count": next_attempt,
                    "lease_until": lease_until,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:reclaimed:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action="task_run.claimed",
                    target=run_id,
                    outcome="success",
                    event_type="task_run.claimed",
                    aggregate_kind="task_run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now_value,
                    event_id=event_id,
                )
                current = connection.execute(
                    "SELECT * FROM task_runs WHERE id = ? AND tenant_id = ?",
                    (run_id, tenant_id),
                ).fetchone()
                connection.execute("COMMIT")
                return self._task_run_record(current, include_lease_token=True)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def complete_task_run(
        self,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        lease_token: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._validate_worker_id(worker_id)
        if not isinstance(lease_token, str) or not lease_token or len(lease_token) > 512:
            raise ValueError("lease_token is invalid")
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("invalid task run status")
        if result is None:
            result = {}
        if error is None:
            error = {}
        if not isinstance(result, dict) or not isinstance(error, dict):
            raise ValueError("task run result and error must be objects")
        result_json = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        error_json = json.dumps(
            error, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._task_run_by_id_locked(connection, run_id, tenant_id)
                if row["status"] != "running":
                    raise ConflictError("task run is not running")
                if row["lease_until"] is None or row["lease_until"] <= now:
                    raise ConflictError("task run lease has expired")
                if not hmac.compare_digest(str(row["worker_id"] or ""), worker_id):
                    raise ConflictError("task run lease belongs to another worker")
                if not hmac.compare_digest(str(row["lease_token"] or ""), lease_token):
                    raise ConflictError("task run lease token is invalid")
                effective_status = status
                if status == "failed":
                    effective_status = (
                        "retry"
                        if int(row["attempt_count"]) < int(row["max_attempts"])
                        else "dead_lettered"
                    )
                updated = connection.execute(
                    "UPDATE task_runs SET status = ?, result_json = ?, error_json = ?, "
                    "worker_id = NULL, lease_token = NULL, lease_until = NULL, finished_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND status = 'running' "
                    "AND worker_id = ? AND lease_token = ?",
                    (
                        effective_status,
                        result_json,
                        error_json,
                        now,
                        run_id,
                        tenant_id,
                        worker_id,
                        lease_token,
                    ),
                )
                if getattr(updated, "rowcount", 1) != 1:
                    raise ConflictError("task run lease is no longer valid")
                schedule = None
                if row["schedule_id"] is not None:
                    schedule = connection.execute(
                        "SELECT * FROM schedules WHERE id = ? AND tenant_id = ?",
                        (row["schedule_id"], tenant_id),
                    ).fetchone()
                    if schedule is not None and schedule["kind"] == "once":
                        schedule_status = {
                            "succeeded": "completed",
                            "dead_lettered": "failed",
                            "cancelled": "cancelled",
                            "retry": "active",
                        }.get(effective_status)
                        if schedule_status is not None:
                            connection.execute(
                                "UPDATE schedules SET status = ?, updated_at = ?, "
                                "cancelled_at = ? WHERE id = ? AND tenant_id = ?",
                                (
                                    schedule_status,
                                    now,
                                    now if schedule_status == "cancelled" else None,
                                    row["schedule_id"],
                                    tenant_id,
                                ),
                            )
                if effective_status == "succeeded":
                    connection.execute(
                        "UPDATE tasks SET status = 'completed', completed_at = ?, updated_at = ?, "
                        "lease_owner = NULL, lease_token = NULL, lease_until = NULL "
                        "WHERE id = ? AND tenant_id = ? AND status IN ('queued', 'running', 'retry')",
                        (now, now, row["task_id"], tenant_id),
                    )
                elif effective_status == "dead_lettered":
                    connection.execute(
                        "UPDATE tasks SET status = 'failed', updated_at = ? "
                        "WHERE id = ? AND tenant_id = ? AND status IN ('queued', 'running', 'retry')",
                        (now, row["task_id"], tenant_id),
                    )
                elif row["schedule_id"] is None and effective_status == "retry":
                    connection.execute(
                        "UPDATE tasks SET status = 'retry', lease_owner = NULL, lease_token = NULL, "
                        "lease_until = NULL, updated_at = ? WHERE id = ? AND tenant_id = ?",
                        (now, row["task_id"], tenant_id),
                    )
                elif row["schedule_id"] is None and effective_status == "cancelled":
                    connection.execute(
                        "UPDATE tasks SET status = 'queued', completed_at = NULL, "
                        "lease_owner = NULL, lease_token = NULL, lease_until = NULL, updated_at = ? "
                        "WHERE id = ? AND tenant_id = ? AND status IN ('queued', 'running', 'retry')",
                        (now, row["task_id"], tenant_id),
                    )
                payload = {
                    "run_id": run_id,
                    "task_id": row["task_id"],
                    "schedule_id": row["schedule_id"],
                    "status": effective_status,
                    "attempt_count": int(row["attempt_count"]),
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:{effective_status}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action=f"task_run.{effective_status}",
                    target=run_id,
                    outcome="success" if effective_status == "succeeded" else effective_status,
                    event_type="task_run.completed",
                    aggregate_kind="task_run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                if effective_status == "succeeded":
                    goal = connection.execute(
                        "SELECT id, status FROM goals WHERE id = ? AND tenant_id = ?",
                        (row["goal_id"], tenant_id),
                    ).fetchone()
                    incomplete = connection.execute(
                        "SELECT COUNT(*) AS count FROM tasks WHERE goal_id = ? AND tenant_id = ? "
                        "AND status != 'completed'",
                        (row["goal_id"], tenant_id),
                    ).fetchone()
                    if (
                        goal is not None
                        and goal["status"] == "active"
                        and int(incomplete["count"]) == 0
                    ):
                        connection.execute(
                            "UPDATE goals SET status = 'completed', completed_at = ?, updated_at = ? "
                            "WHERE id = ? AND tenant_id = ? AND status = 'active'",
                            (now, now, row["goal_id"], tenant_id),
                        )
                        goal_payload = {"goal_id": row["goal_id"], "status": "completed"}
                        goal_event_id = "evt_" + hash_token(
                            f"{tenant_id}:{row['goal_id']}:completed:{os.urandom(16).hex()}"
                        )[:26]
                        self._append_audited_event_locked(
                            connection=connection,
                            tenant_id=tenant_id,
                            actor_kind="worker",
                            actor_id=worker_id,
                            action="goal.completed",
                            target=row["goal_id"],
                            outcome="success",
                            event_type="goal.completed",
                            aggregate_kind="goal",
                            aggregate_id=row["goal_id"],
                            payload_json=json.dumps(
                                goal_payload, sort_keys=True, separators=(",", ":")
                            ),
                            payload=goal_payload,
                            now=now,
                            event_id=goal_event_id,
                        )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_task_run(run_id, tenant_id)

    def create_briefing(
        self,
        briefing_id: str,
        tenant_id: str,
        principal_id: str,
        content: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = _timestamp(_utcnow())
        content_json = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO briefings(id, tenant_id, principal_id, content_json, created_at) VALUES(?, ?, ?, ?, ?)",
                    (briefing_id, tenant_id, principal_id, content_json, now),
                )
                payload = {"briefing_id": briefing_id, "status": content.get("status", "unknown")}
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{briefing_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="briefing.created",
                    target=briefing_id,
                    outcome="success",
                    event_type="briefing.created",
                    aggregate_kind="briefing",
                    aggregate_id=briefing_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {"briefing_id": briefing_id, "tenant_id": tenant_id, "principal_id": principal_id, "content": content, "created_at": now}

    def get_briefing(self, briefing_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM briefings WHERE id = ? AND tenant_id = ?",
                (briefing_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("briefing not found")
        return {
            "briefing_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "content": json.loads(row["content_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _sequence_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "sequence_id": row["id"],
            "tenant_id": row["tenant_id"],
            "principal_id": row["principal_id"],
            "name": row["name"],
            "revision": row["revision"],
            "steps": json.loads(row["steps_json"]),
            "digest": row["digest"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

    def create_sequence(
        self,
        sequence_id: str,
        tenant_id: str,
        principal_id: str,
        name: str,
        steps_json: str,
        digest: str,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not name or len(name) > 128:
            raise ValueError("sequence name must be non-empty and bounded")
        steps = json.loads(steps_json)
        if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
            raise ValueError("sequence must contain between one and 64 steps")
        now = _timestamp(_utcnow())
        expires = _timestamp(expires_at) if expires_at is not None else None
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO sequences("
                    "id, tenant_id, principal_id, name, revision, steps_json, digest, status, created_at, updated_at, expires_at"
                    ") VALUES(?, ?, ?, ?, 1, ?, ?, 'draft', ?, ?, ?)",
                    (sequence_id, tenant_id, principal_id, name, steps_json, digest, now, now, expires),
                )
                payload = {
                    "sequence_id": sequence_id,
                    "revision": 1,
                    "digest": digest,
                    "status": "draft",
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{sequence_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="sequence.created",
                    target=sequence_id,
                    outcome="success",
                    event_type="sequence.created",
                    aggregate_kind="sequence",
                    aggregate_id=sequence_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            row = connection.execute(
                "SELECT * FROM sequences WHERE id = ? AND tenant_id = ?",
                (sequence_id, tenant_id),
            ).fetchone()
        return self._sequence_record(row)

    def get_sequence(self, sequence_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM sequences WHERE id = ? AND tenant_id = ?",
                (sequence_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("sequence not found")
        return self._sequence_record(row)

    def transition_sequence(
        self,
        sequence_id: str,
        tenant_id: str,
        principal_id: str,
        target_status: str,
    ) -> Dict[str, Any]:
        allowed = {
            "draft": {"validated", "rejected"},
            "validated": {"awaiting_approval", "executing", "expired", "rejected"},
            "awaiting_approval": {"approved", "expired", "rejected"},
            "approved": {"executing", "expired", "rejected"},
            "executing": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
            "expired": set(),
            "rejected": set(),
        }
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM sequences WHERE id = ? AND tenant_id = ?",
                (sequence_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("sequence not found")
            if target_status not in allowed.get(row["status"], set()):
                raise ConflictError(
                    f"illegal sequence transition: {row['status']} -> {target_status}"
                )
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE sequences SET status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                    (target_status, now, sequence_id, tenant_id),
                )
                payload = {
                    "sequence_id": sequence_id,
                    "from_status": row["status"],
                    "to_status": target_status,
                    "revision": row["revision"],
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{sequence_id}:{target_status}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action=f"sequence.{target_status}",
                    target=sequence_id,
                    outcome="success",
                    event_type="sequence.updated",
                    aggregate_kind="sequence",
                    aggregate_id=sequence_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_sequence(sequence_id, tenant_id)

    def start_sequence_run(
        self,
        sequence_run_id: str,
        sequence_id: str,
        tenant_id: str,
        principal_id: str,
        revision: int,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("invalid idempotency key")
        with self._lock:
            connection = self._conn()
            existing = connection.execute(
                "SELECT * FROM sequence_runs WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["sequence_id"] != sequence_id or existing["revision"] != revision:
                    raise ConflictError("idempotency key is bound to another sequence revision")
                return {"created": False, "run": self.get_sequence_run(existing["id"], tenant_id)}
            now = _timestamp(_utcnow())
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO sequence_runs("
                    "id, tenant_id, sequence_id, revision, idempotency_key, status, result_json, created_at"
                    ") VALUES(?, ?, ?, ?, ?, 'running', '{}', ?)",
                    (sequence_run_id, tenant_id, sequence_id, revision, idempotency_key, now),
                )
                payload = {
                    "sequence_run_id": sequence_run_id,
                    "sequence_id": sequence_id,
                    "revision": revision,
                    "status": "running",
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{sequence_run_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="sequence.run.created",
                    target=sequence_run_id,
                    outcome="success",
                    event_type="sequence.run.created",
                    aggregate_kind="sequence_run",
                    aggregate_id=sequence_run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raced = connection.execute(
                        "SELECT * FROM sequence_runs WHERE tenant_id = ? AND idempotency_key = ?",
                        (tenant_id, idempotency_key),
                    ).fetchone()
                    if raced is not None:
                        if raced["sequence_id"] != sequence_id or raced["revision"] != revision:
                            raise ConflictError(
                                "idempotency key is bound to another sequence revision"
                            ) from error
                        return {
                            "created": False,
                            "run": self.get_sequence_run(raced["id"], tenant_id),
                        }
                raise
            return {"created": True, "run": self.get_sequence_run(sequence_run_id, tenant_id)}

    def get_sequence_run_by_idempotency(
        self,
        sequence_id: str,
        tenant_id: str,
        revision: int,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        """Return a completed or in-flight sequence run for a safe retry."""
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM sequence_runs WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        if row["sequence_id"] != sequence_id or row["revision"] != revision:
            raise ConflictError("idempotency key is bound to another sequence revision")
        return self.get_sequence_run(row["id"], tenant_id)

    def complete_sequence_run(
        self,
        sequence_run_id: str,
        tenant_id: str,
        principal_id: str,
        status: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if status not in {"completed", "failed", "unknown", "cancelled"}:
            raise ValueError("invalid sequence run status")
        now = _timestamp(_utcnow())
        result_json = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._lock:
            connection = self._conn()
            row = connection.execute(
                "SELECT * FROM sequence_runs WHERE id = ? AND tenant_id = ?",
                (sequence_run_id, tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("sequence run not found")
            if row["status"] != "running":
                if row["status"] == status and row["result_json"] == result_json:
                    return self.get_sequence_run(sequence_run_id, tenant_id)
                raise ConflictError("sequence run has already reached a terminal state")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE sequence_runs SET status = ?, result_json = ?, finished_at = ? "
                    "WHERE id = ? AND tenant_id = ? AND status = 'running'",
                    (status, result_json, now, sequence_run_id, tenant_id),
                )
                payload = {
                    "sequence_run_id": sequence_run_id,
                    "sequence_id": row["sequence_id"],
                    "status": status,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{sequence_run_id}:{status}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="system",
                    actor_id=principal_id,
                    action=f"sequence.run.{status}",
                    target=sequence_run_id,
                    outcome="success" if status == "completed" else "failure",
                    event_type="sequence.run.updated",
                    aggregate_kind="sequence_run",
                    aggregate_id=sequence_run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_sequence_run(sequence_run_id, tenant_id)

    def get_sequence_run(self, sequence_run_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn().execute(
                "SELECT * FROM sequence_runs WHERE id = ? AND tenant_id = ?",
                (sequence_run_id, tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("sequence run not found")
        return {
            "sequence_run_id": row["id"],
            "tenant_id": row["tenant_id"],
            "sequence_id": row["sequence_id"],
            "revision": row["revision"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }

    def list_sequence_events(
        self, sequence_id: str, tenant_id: str, after: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid sequence event cursor or limit")
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM events WHERE tenant_id = ? AND aggregate_kind IN ('sequence', 'sequence_run') "
                "AND aggregate_id IN (?, ?) AND sequence > ? ORDER BY sequence ASC LIMIT ?",
                (tenant_id, sequence_id, sequence_id, after, limit),
            ).fetchall()
        return [
            {
                "event_id": row["id"],
                "tenant_id": row["tenant_id"],
                "sequence": row["sequence"],
                "type": row["type"],
                "aggregate": {"kind": row["aggregate_kind"], "id": row["aggregate_id"]},
                "actor": {"kind": row["actor_kind"], "id": row["actor_id"]},
                "payload": json.loads(row["payload_json"]),
                "visibility": row["visibility"],
                "schema_version": row["schema_version"],
                "occurred_at": row["created_at"],
            }
            for row in rows
        ]

    def list_events(self, tenant_id: str, after: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid event cursor or limit")
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM events WHERE tenant_id = ? AND sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (tenant_id, after, limit),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "event_id": row["id"],
                    "tenant_id": row["tenant_id"],
                    "sequence": row["sequence"],
                    "type": row["type"],
                    "aggregate": {
                        "kind": row["aggregate_kind"],
                        "id": row["aggregate_id"],
                    },
                    "actor": {"kind": row["actor_kind"], "id": row["actor_id"]},
                    "payload": json.loads(row["payload_json"]),
                    "visibility": row["visibility"],
                    "schema_version": row["schema_version"],
                    "occurred_at": row["created_at"],
                }
            )
        return result

    def latest_sequence(self, tenant_id: str) -> int:
        with self._lock:
            row = self._conn().execute(
                "SELECT COALESCE(MAX(sequence), 0) AS latest FROM events WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        return int(row["latest"])

    @staticmethod
    def _action_record(
        row: Any,
        include_payload: bool = False,
        include_lease_token: bool = False,
    ) -> Dict[str, Any]:
        record = {
            "action_id": row["id"],
            "tenant_id": row["tenant_id"],
            "run_id": row["run_id"],
            "step_id": row["step_id"],
            "tool_id": row["tool_id"],
            "status": row["status"],
            "attempt_count": int(row["attempt_count"]),
            "timeout_ms": int(row["timeout_ms"]),
            "max_attempts": int(row["max_attempts"]),
            "retry_policy": row["retry_policy"],
            "next_attempt_at": row["next_attempt_at"],
            "worker_id": row["worker_id"],
            "lease_until": row["lease_until"],
            "last_error": row["last_error"],
            "cancel_requested": bool(row["cancel_requested"]),
            "unknown_reason": row["unknown_reason"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }
        if include_payload:
            record["payload"] = json.loads(row["payload_json"])
        if include_lease_token:
            record["lease_token"] = row["lease_token"]
        return record

    @staticmethod
    def _bounded_json_object(
        value: Dict[str, Any], field_name: str, max_bytes: int
    ) -> str:
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be an object")
        try:
            encoded = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be JSON serializable") from exc
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError(f"{field_name} exceeds the configured limit")
        return encoded

    def _action_and_run_locked(
        self, connection: Any, run_id: str, tenant_id: str
    ) -> Tuple[Any, Any]:
        run = connection.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise NotFoundError("run not found")
        if run["tenant_id"] != tenant_id:
            raise ScopeViolation("run is outside tenant scope")
        action = connection.execute(
            "SELECT * FROM actions WHERE run_id = ? AND tenant_id = ? "
            "ORDER BY created_at, id LIMIT 1",
            (run_id, tenant_id),
        ).fetchone()
        if action is None:
            raise ScopeViolation("run action is not available in tenant scope")
        return run, action

    @staticmethod
    def _action_error_code(error: Optional[Dict[str, Any]]) -> str:
        if not isinstance(error, dict):
            return "ACTION_FAILED"
        candidate = error.get("error_code", error.get("code"))
        if (
            isinstance(candidate, str)
            and 1 <= len(candidate) <= 128
            and candidate.isascii()
            and all(char.isalnum() or char in {"_", "-", "."} for char in candidate)
        ):
            return candidate
        return "ACTION_FAILED"

    def _prepare_action_evidence(
        self,
        run_id: str,
        result: Dict[str, Any],
        evidence_status: str,
        provenance: Dict[str, Any],
        disclosure: str,
        now: str,
    ) -> Tuple[str, str]:
        allowed_statuses = {
            "verified",
            "rejected",
            "unknown",
            "unavailable",
            "simulated",
            "research_only",
        }
        if evidence_status not in allowed_statuses:
            raise ValueError("invalid evidence status")
        result_json = self._bounded_json_object(result, "action result", 1_048_576)
        if not isinstance(provenance, dict):
            raise ValueError("action provenance must be an object")
        provenance_payload = dict(provenance)
        observed_at = provenance_payload.setdefault("observed_at", now)
        observed_datetime = _parse_utc_timestamp(observed_at, "observed_at")
        try:
            freshness_seconds = int(provenance_payload.get("freshness_seconds", 60))
        except (TypeError, ValueError):
            freshness_seconds = 60
        freshness_seconds = max(0, min(freshness_seconds, 86_400))
        provenance_payload.setdefault(
            "fresh_until",
            _timestamp(observed_datetime + timedelta(seconds=freshness_seconds)),
        )
        provenance_payload.setdefault("output_digest", "sha256:" + hash_token(result_json))
        provenance_payload.setdefault(
            "input_digest", "sha256:" + hash_token(f"run:{run_id}")
        )
        provenance_payload.setdefault(
            "method_ref",
            f"procedure.{provenance_payload.get('adapter_id', 'unknown')}.v1",
        )
        provenance_payload.setdefault("artifact_ref", None)
        provenance_payload.setdefault(
            "source",
            {
                "adapter_id": provenance_payload.get("adapter_id", "unknown"),
                "adapter_version": provenance_payload.get("adapter_version", "unknown"),
                "origin": provenance_payload.get("origin", "unknown"),
                "input_digest": provenance_payload.get("input_digest"),
            },
        )
        provenance_payload["disclosure"] = disclosure
        provenance_json = self._bounded_json_object(
            provenance_payload, "action provenance", 65_536
        )
        return result_json, provenance_json

    def _finalize_action_locked(
        self,
        connection: Any,
        run: Any,
        action: Any,
        tenant_id: str,
        final_status: str,
        evidence_status: str,
        result: Dict[str, Any],
        provenance: Dict[str, Any],
        disclosure: str,
        actor_kind: str,
        actor_id: str,
        now: str,
        unknown_reason: Optional[str] = None,
    ) -> str:
        if final_status not in {"succeeded", "failed", "unknown", "cancelled"}:
            raise ValueError("invalid terminal action status")
        previous_evidence = connection.execute(
            "SELECT evidence_id FROM action_evidence WHERE action_id = ?",
            (action["id"],),
        ).fetchone()
        supersedes = previous_evidence["evidence_id"] if previous_evidence is not None else None
        result_json, provenance_json = self._prepare_action_evidence(
            run["id"], result, evidence_status, provenance, disclosure, now
        )
        evidence_id = "ev_" + hash_token(
            f"{tenant_id}:{run['id']}:{action['id']}:{os.urandom(16).hex()}"
        )[:26]
        connection.execute(
            "INSERT INTO evidence("
            "id, tenant_id, kind, status, provenance_json, result_json, artifact_ref, supersedes, created_at"
            ") VALUES(?, ?, 'action_result', ?, ?, ?, ?, ?, ?)",
            (
                evidence_id,
                tenant_id,
                evidence_status,
                provenance_json,
                result_json,
                json.loads(provenance_json).get("artifact_ref"),
                supersedes,
                now,
            ),
        )
        if previous_evidence is None:
            connection.execute(
                "INSERT INTO action_evidence(action_id, evidence_id) VALUES(?, ?)",
                (action["id"], evidence_id),
            )
        else:
            connection.execute(
                "UPDATE action_evidence SET evidence_id = ? WHERE action_id = ?",
                (evidence_id, action["id"]),
            )
        updated_action = connection.execute(
            "UPDATE actions SET status = ?, finished_at = ?, next_attempt_at = NULL, "
            "worker_id = NULL, lease_token = NULL, lease_until = NULL, "
            "cancel_requested = 0, unknown_reason = ?, last_error = ? "
            "WHERE id = ? AND tenant_id = ? AND status IN ('queued', 'retry', 'running', 'cancel_requested', 'unknown')",
            (
                final_status,
                now,
                unknown_reason,
                unknown_reason,
                action["id"],
                tenant_id,
            ),
        )
        if getattr(updated_action, "rowcount", 1) != 1:
            raise ConflictError("action is no longer in a finalizable state")
        updated_run = connection.execute(
            "UPDATE runs SET status = ?, finished_at = ?, cancel_requested = 0, "
            "unknown_reason = ? WHERE id = ? AND tenant_id = ? "
            "AND status IN ('queued', 'retry', 'running', 'cancel_requested', 'unknown')",
            (final_status, now, unknown_reason, run["id"], tenant_id),
        )
        if getattr(updated_run, "rowcount", 1) != 1:
            raise ConflictError("run is no longer in a finalizable state")
        evidence_payload = {
            "evidence_id": evidence_id,
            "run_id": run["id"],
            "action_id": action["id"],
            "status": evidence_status,
        }
        evidence_event_id = "evt_" + hash_token(
            f"{tenant_id}:{evidence_id}:{os.urandom(16).hex()}"
        )[:26]
        self._append_audited_event_locked(
            connection=connection,
            tenant_id=tenant_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            action="evidence.created",
            target=evidence_id,
            outcome="success",
            event_type="evidence.created",
            aggregate_kind="evidence",
            aggregate_id=evidence_id,
            payload_json=json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")),
            payload=evidence_payload,
            now=now,
            event_id=evidence_event_id,
        )
        run_payload = {
            "run_id": run["id"],
            "action_id": action["id"],
            "status": final_status,
            "evidence_id": evidence_id,
            "attempt_count": int(action["attempt_count"]),
        }
        if unknown_reason is not None:
            run_payload["unknown_reason"] = unknown_reason
        run_event_id = "evt_" + hash_token(
            f"{tenant_id}:{run['id']}:{final_status}:{os.urandom(16).hex()}"
        )[:26]
        self._append_audited_event_locked(
            connection=connection,
            tenant_id=tenant_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            action=f"run.{final_status}",
            target=run["id"],
            outcome="success" if final_status in {"succeeded", "cancelled"} else final_status,
            event_type=f"run.{final_status}",
            aggregate_kind="run",
            aggregate_id=run["id"],
            payload_json=json.dumps(run_payload, sort_keys=True, separators=(",", ":")),
            payload=run_payload,
            now=now,
            event_id=run_event_id,
        )
        return evidence_id

    def _mark_action_unknown_locked(
        self,
        connection: Any,
        run: Any,
        action: Any,
        tenant_id: str,
        actor_id: str,
        reason: str,
        now: str,
    ) -> None:
        safe_reason = reason if reason in {
            "lease_expired",
            "action_timeout",
            "side_effect_uncertain",
            "cancel_requested_during_execution",
            "tool_unavailable",
        } else "action_unknown"
        self._finalize_action_locked(
            connection=connection,
            run=run,
            action=action,
            tenant_id=tenant_id,
            final_status="unknown",
            evidence_status="unknown",
            result={"error_code": safe_reason.upper()},
            provenance={
                "adapter_id": "zasi-action-worker",
                "adapter_version": "1.0.0",
                "origin": "control-plane",
                "method_ref": "procedure.action.uncertain-result.v1",
            },
            disclosure="The control plane lost certainty about the action outcome; reconciliation is required before retry.",
            actor_kind="worker",
            actor_id=actor_id,
            now=now,
            unknown_reason=safe_reason,
        )

    def list_claimable_actions(
        self, tenant_id: str, limit: int = 100, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid action limit")
        now_value = _timestamp(_utcnow() if now is None else now)
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM actions WHERE tenant_id = ? AND status IN ('queued', 'retry') "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                "ORDER BY next_attempt_at, created_at, id LIMIT ?",
                (tenant_id, now_value, limit),
            ).fetchall()
        return [self._action_record(row) for row in rows]

    def claim_action(
        self,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        self._validate_worker_id(worker_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 3600
        ):
            raise ValueError("lease_seconds must be between 1 and 3600")
        now_dt = _utcnow() if now is None else now
        if not isinstance(now_dt, datetime) or now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=lease_seconds))
        lease_token = hash_token(
            f"{tenant_id}:{run_id}:{worker_id}:{now_value}:{os.urandom(32).hex()}"
        )
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                run, action = self._action_and_run_locked(connection, run_id, tenant_id)
                if action["status"] == "running":
                    if action["lease_until"] is not None and action["lease_until"] <= now_value:
                        self._mark_action_unknown_locked(
                            connection,
                            run,
                            action,
                            tenant_id,
                            worker_id,
                            "lease_expired",
                            now_value,
                        )
                        connection.execute("COMMIT")
                    else:
                        connection.execute("ROLLBACK")
                    return None
                if action["status"] not in {"queued", "retry"}:
                    connection.execute("ROLLBACK")
                    return None
                if run["cancel_requested"] or run["status"] == "cancel_requested" or action["cancel_requested"]:
                    connection.execute(
                        "UPDATE actions SET status = 'cancelled', finished_at = ?, "
                        "next_attempt_at = NULL, worker_id = NULL, lease_token = NULL, "
                        "lease_until = NULL, cancel_requested = 0 WHERE id = ? AND tenant_id = ?",
                        (now_value, action["id"], tenant_id),
                    )
                    connection.execute(
                        "UPDATE runs SET status = 'cancelled', finished_at = ?, cancel_requested = 0 "
                        "WHERE id = ? AND tenant_id = ?",
                        (now_value, run_id, tenant_id),
                    )
                    payload = {"run_id": run_id, "action_id": action["id"], "status": "cancelled"}
                    event_id = "evt_" + hash_token(
                        f"{tenant_id}:{run_id}:cancelled:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="worker",
                        actor_id=worker_id,
                        action="run.cancelled",
                        target=run_id,
                        outcome="success",
                        event_type="run.cancelled",
                        aggregate_kind="run",
                        aggregate_id=run_id,
                        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        payload=payload,
                        now=now_value,
                        event_id=event_id,
                    )
                    connection.execute("COMMIT")
                    return None
                if action["next_attempt_at"] is not None and action["next_attempt_at"] > now_value:
                    connection.execute("ROLLBACK")
                    return None
                if int(action["attempt_count"]) >= int(action["max_attempts"]):
                    self._finalize_action_locked(
                        connection=connection,
                        run=run,
                        action=action,
                        tenant_id=tenant_id,
                        final_status="failed",
                        evidence_status="unknown",
                        result={"error_code": "ACTION_ATTEMPTS_EXHAUSTED"},
                        provenance={
                            "adapter_id": "zasi-action-worker",
                            "adapter_version": "1.0.0",
                            "origin": "control-plane",
                            "method_ref": "procedure.action.retry-limit.v1",
                        },
                        disclosure="The bounded action retry policy was exhausted.",
                        actor_kind="worker",
                        actor_id=worker_id,
                        now=now_value,
                    )
                    connection.execute("COMMIT")
                    return None
                next_attempt = int(action["attempt_count"]) + 1
                updated = connection.execute(
                    "UPDATE actions SET status = 'running', attempt_count = ?, worker_id = ?, "
                    "lease_token = ?, lease_until = ?, next_attempt_at = NULL, "
                    "last_error = NULL, unknown_reason = NULL WHERE id = ? AND tenant_id = ? "
                    "AND status IN ('queued', 'retry')",
                    (
                        next_attempt,
                        worker_id,
                        lease_token,
                        lease_until,
                        action["id"],
                        tenant_id,
                    ),
                )
                if getattr(updated, "rowcount", 1) != 1:
                    connection.execute("ROLLBACK")
                    return None
                connection.execute(
                    "UPDATE runs SET status = 'running', finished_at = NULL, "
                    "cancel_requested = 0, unknown_reason = NULL WHERE id = ? AND tenant_id = ? "
                    "AND status IN ('queued', 'retry', 'created')",
                    (run_id, tenant_id),
                )
                payload = {
                    "run_id": run_id,
                    "action_id": action["id"],
                    "tool_id": action["tool_id"],
                    "status": "running",
                    "attempt_count": next_attempt,
                    "lease_until": lease_until,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:claimed:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="worker",
                    actor_id=worker_id,
                    action="run.claimed",
                    target=run_id,
                    outcome="success",
                    event_type="run.claimed",
                    aggregate_kind="run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now_value,
                    event_id=event_id,
                )
                current = connection.execute(
                    "SELECT * FROM actions WHERE id = ? AND tenant_id = ?",
                    (action["id"], tenant_id),
                ).fetchone()
                connection.execute("COMMIT")
                record = self._action_record(
                    current, include_payload=True, include_lease_token=True
                )
                record["principal_id"] = run["principal_id"]
                record["plan_id"] = run["plan_id"]
                return record
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def finish_action(
        self,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        lease_token: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
        evidence_status: str = "unknown",
        provenance: Optional[Dict[str, Any]] = None,
        disclosure: str = "Action result was produced by a governed worker.",
        now: Optional[datetime] = None,
        unknown_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_worker_id(worker_id)
        if not isinstance(lease_token, str) or not lease_token or len(lease_token) > 512:
            raise ValueError("lease_token is invalid")
        if status not in {"succeeded", "failed", "unknown", "cancelled"}:
            raise ValueError("invalid action status")
        allowed_unknown_reasons = {
            None,
            "lease_expired",
            "action_timeout",
            "side_effect_uncertain",
            "cancel_requested_during_execution",
            "tool_unavailable",
        }
        if unknown_reason not in allowed_unknown_reasons:
            raise ValueError("invalid unknown reason")
        result = {} if result is None else result
        error = {} if error is None else error
        provenance = {} if provenance is None else provenance
        if not isinstance(result, dict) or not isinstance(error, dict) or not isinstance(provenance, dict):
            raise ValueError("action result, error, and provenance must be objects")
        now_dt = _utcnow() if now is None else now
        if not isinstance(now_dt, datetime) or now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                run, action = self._action_and_run_locked(connection, run_id, tenant_id)
                if action["status"] not in {"running", "cancel_requested"}:
                    raise ConflictError("action is not running")
                if not hmac.compare_digest(str(action["worker_id"] or ""), worker_id):
                    raise ConflictError("action lease belongs to another worker")
                if not hmac.compare_digest(str(action["lease_token"] or ""), lease_token):
                    raise ConflictError("action lease token is invalid")
                if action["lease_until"] is None or action["lease_until"] <= now_value:
                    self._mark_action_unknown_locked(
                        connection,
                        run,
                        action,
                        tenant_id,
                        worker_id,
                        "lease_expired",
                        now_value,
                    )
                    connection.execute("COMMIT")
                    raise ConflictError("action lease has expired")
                effective_status = status
                effective_unknown_reason = unknown_reason
                if action["cancel_requested"] or run["cancel_requested"] or run["status"] == "cancel_requested":
                    if status != "cancelled":
                        effective_status = "unknown"
                        effective_unknown_reason = "cancel_requested_during_execution"
                if effective_status == "failed" and action["retry_policy"] == "bounded" and int(action["attempt_count"]) < int(action["max_attempts"]):
                    error_code = self._action_error_code(error)
                    next_attempt_at = _timestamp(
                        now_dt + timedelta(seconds=min(60, 2 ** max(0, int(action["attempt_count"]) - 1)))
                    )
                    connection.execute(
                        "UPDATE actions SET status = 'retry', next_attempt_at = ?, worker_id = NULL, "
                        "lease_token = NULL, lease_until = NULL, last_error = ?, "
                        "cancel_requested = 0, unknown_reason = NULL WHERE id = ? AND tenant_id = ? "
                        "AND status IN ('running', 'cancel_requested')",
                        (next_attempt_at, error_code, action["id"], tenant_id),
                    )
                    connection.execute(
                        "UPDATE runs SET status = 'queued', finished_at = NULL, cancel_requested = 0, "
                        "unknown_reason = NULL WHERE id = ? AND tenant_id = ? "
                        "AND status IN ('running', 'cancel_requested')",
                        (run_id, tenant_id),
                    )
                    payload = {
                        "run_id": run_id,
                        "action_id": action["id"],
                        "status": "retry",
                        "attempt_count": int(action["attempt_count"]),
                        "next_attempt_at": next_attempt_at,
                        "error_code": error_code,
                    }
                    event_id = "evt_" + hash_token(
                        f"{tenant_id}:{run_id}:retry:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="worker",
                        actor_id=worker_id,
                        action="run.retry_scheduled",
                        target=run_id,
                        outcome="retry",
                        event_type="run.retry_scheduled",
                        aggregate_kind="run",
                        aggregate_id=run_id,
                        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        payload=payload,
                        now=now_value,
                        event_id=event_id,
                    )
                    connection.execute("COMMIT")
                    return self.get_run(run_id, tenant_id)
                if effective_status == "unknown" and effective_unknown_reason is None:
                    effective_unknown_reason = "side_effect_uncertain"
                self._finalize_action_locked(
                    connection=connection,
                    run=run,
                    action=action,
                    tenant_id=tenant_id,
                    final_status=effective_status,
                    evidence_status="unknown" if effective_status == "unknown" else evidence_status,
                    result=result if effective_status != "unknown" else {"error_code": effective_unknown_reason.upper()},
                    provenance=provenance,
                    disclosure=disclosure if effective_status != "unknown" else "Action outcome is uncertain; reconciliation is required before retry.",
                    actor_kind="worker",
                    actor_id=worker_id,
                    now=now_value,
                    unknown_reason=effective_unknown_reason,
                )
                connection.execute("COMMIT")
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return self.get_run(run_id, tenant_id)

    def reconcile_action(
        self,
        run_id: str,
        tenant_id: str,
        principal_id: str,
        outcome: str,
        reason: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if outcome not in {"retry", "succeeded", "failed", "cancelled"}:
            raise ValueError("invalid reconciliation outcome")
        if (
            not isinstance(reason, str)
            or not 1 <= len(reason) <= 2000
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in reason)
        ):
            raise ValueError("reconciliation reason is invalid")
        result = {} if result is None else result
        if not isinstance(result, dict):
            raise ValueError("reconciliation result must be an object")
        now = _timestamp(_utcnow())
        reason_digest = "sha256:" + hash_token(reason)
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                run, action = self._action_and_run_locked(connection, run_id, tenant_id)
                if action["status"] != "unknown" or run["status"] != "unknown":
                    raise ConflictError("only an unknown action can be reconciled")
                if outcome == "retry":
                    connection.execute(
                        "UPDATE actions SET status = 'queued', next_attempt_at = ?, finished_at = NULL, "
                        "worker_id = NULL, lease_token = NULL, lease_until = NULL, last_error = NULL, "
                        "cancel_requested = 0, unknown_reason = NULL WHERE id = ? AND tenant_id = ? "
                        "AND status = 'unknown'",
                        (now, action["id"], tenant_id),
                    )
                    connection.execute(
                        "UPDATE runs SET status = 'queued', finished_at = NULL, cancel_requested = 0, "
                        "unknown_reason = NULL WHERE id = ? AND tenant_id = ? AND status = 'unknown'",
                        (run_id, tenant_id),
                    )
                    payload = {
                        "run_id": run_id,
                        "action_id": action["id"],
                        "status": "queued",
                        "reconciliation_reason_digest": reason_digest,
                    }
                    event_type = "run.reconciled"
                    event_id = "evt_" + hash_token(
                        f"{tenant_id}:{run_id}:reconcile:retry:{os.urandom(16).hex()}"
                    )[:26]
                    self._append_audited_event_locked(
                        connection=connection,
                        tenant_id=tenant_id,
                        actor_kind="principal",
                        actor_id=principal_id,
                        action="run.reconciled",
                        target=run_id,
                        outcome="retry",
                        event_type=event_type,
                        aggregate_kind="run",
                        aggregate_id=run_id,
                        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        payload=payload,
                        now=now,
                        event_id=event_id,
                    )
                else:
                    self._finalize_action_locked(
                        connection=connection,
                        run=run,
                        action=action,
                        tenant_id=tenant_id,
                        final_status=outcome,
                        evidence_status="unknown",
                        result=result,
                        provenance={
                            "adapter_id": "operator-reconciliation",
                            "adapter_version": "1.0.0",
                            "origin": "control-plane",
                            "method_ref": "procedure.action.operator-reconciliation.v1",
                            "reconciliation_reason_digest": reason_digest,
                        },
                        disclosure="The operator reconciled an uncertain outcome; independent side-effect proof is not implied.",
                        actor_kind="principal",
                        actor_id=principal_id,
                        now=now,
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_run(run_id, tenant_id)

    def start_run(
        self,
        run_id: str,
        action_id: str,
        tenant_id: str,
        principal_id: str,
        tool_id: str,
        idempotency_key: str,
        status: str,
        plan_id: Optional[str] = None,
        request_digest: str = "",
        payload: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 2000,
        max_attempts: int = 1,
        retry_policy: str = "none",
    ) -> Dict[str, Any]:
        self._validate_idempotency_key(idempotency_key)
        if status not in {"queued", "waiting_approval"}:
            raise ValueError("action runs must start queued or waiting for approval")
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or not 1 <= timeout_ms <= 86_400_000
        ):
            raise ValueError("timeout_ms must be between 1 and 86400000")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("max_attempts must be between 1 and 10")
        if retry_policy not in {"none", "bounded"}:
            raise ValueError("invalid retry policy")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError("action payload must be an object")
        try:
            action_payload_json = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("action payload must be JSON serializable") from exc
        if len(action_payload_json.encode("utf-8")) > 262_144:
            raise ValueError("action payload exceeds the configured limit")
        with self._lock:
            connection = self._conn()
            existing = connection.execute(
                "SELECT id FROM runs WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                existing_run = self.get_run(existing["id"], tenant_id)
                if existing_run.get("tool_id") != tool_id:
                    raise ConflictError("idempotency key is bound to another tool")
                if (existing_run.get("plan_id") or None) != (plan_id or None):
                    raise ConflictError("idempotency key is bound to another plan")
                if existing_run.get("request_digest", "") != request_digest:
                    raise ConflictError("idempotency key is bound to another request")
                return {
                    "created": False,
                    "run": existing_run,
                    "action_id": existing_run["action_id"],
                }
            now = _timestamp(_utcnow())
            self._validate_principal_locked(connection, tenant_id, principal_id)
            event_payload = {
                "run_id": run_id,
                "tool_id": tool_id,
                "status": status,
                "idempotency_key": idempotency_key,
            }
            event_payload_json = json.dumps(event_payload, sort_keys=True, separators=(",", ":"))
            event_id = "evt_" + hash_token(
                f"{tenant_id}:{run_id}:{os.urandom(16).hex()}"
            )[:26]
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO runs("
                    "id, tenant_id, principal_id, plan_id, idempotency_key, request_digest, status, "
                    "cancel_requested, unknown_reason, created_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
                    (
                        run_id,
                        tenant_id,
                        principal_id,
                        plan_id,
                        idempotency_key,
                        request_digest,
                        status,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO actions("
                    "id, tenant_id, run_id, step_id, tool_id, status, attempt_count, payload_json, "
                    "timeout_ms, max_attempts, retry_policy, next_attempt_at, created_at"
                    ") VALUES(?, ?, ?, NULL, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
                    (
                        action_id,
                        tenant_id,
                        run_id,
                        tool_id,
                        status,
                        action_payload_json,
                        timeout_ms,
                        max_attempts,
                        retry_policy,
                        now if status == "queued" else None,
                        now,
                    ),
                )
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action="run.created",
                    target=run_id,
                    outcome="success",
                    event_type="run.created",
                    aggregate_kind="run",
                    aggregate_id=run_id,
                    payload_json=event_payload_json,
                    payload=event_payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                if _is_unique_integrity_error(error):
                    raced = connection.execute(
                        "SELECT id FROM runs WHERE tenant_id = ? AND idempotency_key = ?",
                        (tenant_id, idempotency_key),
                    ).fetchone()
                    if raced is not None:
                        existing_run = self.get_run(raced["id"], tenant_id)
                        if existing_run.get("tool_id") != tool_id:
                            raise ConflictError(
                                "idempotency key is bound to another tool"
                            ) from error
                        if (existing_run.get("plan_id") or None) != (plan_id or None):
                            raise ConflictError(
                                "idempotency key is bound to another plan"
                            ) from error
                        if existing_run.get("request_digest", "") != request_digest:
                            raise ConflictError(
                                "idempotency key is bound to another request"
                            ) from error
                        return {
                            "created": False,
                            "run": existing_run,
                            "action_id": existing_run["action_id"],
                        }
                raise
            return {
                "created": True,
                "run": self.get_run(run_id, tenant_id),
                "action_id": action_id,
            }

    def complete_run(
        self,
        run_id: str,
        action_id: str,
        tenant_id: str,
        principal_id: str,
        result: Dict[str, Any],
        evidence_status: str,
        provenance: Dict[str, Any],
        disclosure: str,
        success: bool = True,
    ) -> Dict[str, Any]:
        if evidence_status not in {
            "verified",
            "rejected",
            "unknown",
            "unavailable",
            "simulated",
            "research_only",
        }:
            raise ValueError("invalid evidence status")
        if not isinstance(result, dict) or not isinstance(provenance, dict):
            raise ValueError("run result and provenance must be objects")
        now = _timestamp(_utcnow())
        result_json = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        provenance_payload = dict(provenance)
        observed_at = provenance_payload.setdefault("observed_at", now)
        observed_datetime = _parse_utc_timestamp(observed_at, "observed_at")
        try:
            freshness_seconds = int(provenance_payload.get("freshness_seconds", 60))
        except (TypeError, ValueError):
            freshness_seconds = 60
        freshness_seconds = max(0, min(freshness_seconds, 86_400))
        provenance_payload.setdefault(
            "fresh_until",
            _timestamp(
                observed_datetime
                + timedelta(seconds=freshness_seconds)
            ),
        )
        provenance_payload.setdefault(
            "output_digest", "sha256:" + hash_token(result_json)
        )
        provenance_payload.setdefault(
            "input_digest", "sha256:" + hash_token(f"run:{run_id}")
        )
        provenance_payload.setdefault(
            "method_ref",
            f"procedure.{provenance_payload.get('adapter_id', 'unknown')}.v1",
        )
        provenance_payload.setdefault("artifact_ref", None)
        provenance_payload.setdefault(
            "source",
            {
                "adapter_id": provenance_payload.get("adapter_id", "unknown"),
                "adapter_version": provenance_payload.get("adapter_version", "unknown"),
                "origin": provenance_payload.get("origin", "unknown"),
                "input_digest": provenance_payload.get("input_digest"),
            },
        )
        provenance_payload["disclosure"] = disclosure
        provenance_json = json.dumps(
            provenance_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        evidence_id = "ev_" + hash_token(
            f"{tenant_id}:{run_id}:{os.urandom(16).hex()}"
        )[:26]
        final_status = "succeeded" if success else "failed"
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                run_row = connection.execute(
                    "SELECT * FROM runs WHERE id = ? AND tenant_id = ?",
                    (run_id, tenant_id),
                ).fetchone()
                if run_row is None:
                    raise NotFoundError("run not found")
                action_row = connection.execute(
                    "SELECT * FROM actions WHERE id = ? AND run_id = ? AND tenant_id = ?",
                    (action_id, run_id, tenant_id),
                ).fetchone()
                if action_row is None:
                    raise ScopeViolation("action is not bound to this run")
                if run_row["status"] != "running":
                    existing_evidence = connection.execute(
                        "SELECT e.status, e.result_json FROM evidence e "
                        "JOIN action_evidence ae ON ae.evidence_id = e.id "
                        "WHERE ae.action_id = ? ORDER BY e.created_at DESC LIMIT 1",
                        (action_id,),
                    ).fetchone()
                    if (
                        run_row["status"] == final_status
                        and action_row["status"] == final_status
                        and existing_evidence is not None
                        and existing_evidence["status"] == evidence_status
                        and existing_evidence["result_json"] == result_json
                    ):
                        connection.execute("ROLLBACK")
                        return self.get_run(run_id, tenant_id)
                    raise ConflictError("run has already reached a terminal state")
                connection.execute(
                    "INSERT INTO evidence("
                    "id, tenant_id, kind, status, provenance_json, result_json, artifact_ref, created_at"
                    ") VALUES(?, ?, 'action_result', ?, ?, ?, ?, ?)",
                    (
                        evidence_id,
                        tenant_id,
                        evidence_status,
                        provenance_json,
                        result_json,
                        provenance_payload.get("artifact_ref"),
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO action_evidence(action_id, evidence_id) VALUES(?, ?)",
                    (action_id, evidence_id),
                )
                connection.execute(
                    "UPDATE actions SET status = ?, finished_at = ? WHERE id = ? AND tenant_id = ? AND status = 'running'",
                    (final_status, now, action_id, tenant_id),
                )
                connection.execute(
                    "UPDATE runs SET status = ?, finished_at = ? WHERE id = ? AND tenant_id = ? AND status = 'running'",
                    (final_status, now, run_id, tenant_id),
                )
                evidence_payload = {
                    "evidence_id": evidence_id,
                    "run_id": run_id,
                    "status": evidence_status,
                }
                evidence_event_id = "evt_" + hash_token(
                    f"{tenant_id}:{evidence_id}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="system",
                    actor_id=principal_id,
                    action="evidence.created",
                    target=evidence_id,
                    outcome="success",
                    event_type="evidence.created",
                    aggregate_kind="evidence",
                    aggregate_id=evidence_id,
                    payload_json=json.dumps(
                        evidence_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    payload=evidence_payload,
                    now=now,
                    event_id=evidence_event_id,
                )
                run_payload = {
                    "run_id": run_id,
                    "status": final_status,
                    "evidence_id": evidence_id,
                }
                run_event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:{final_status}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="system",
                    actor_id=principal_id,
                    action=f"run.{final_status}",
                    target=run_id,
                    outcome="success" if success else "failure",
                    event_type=f"run.{final_status}",
                    aggregate_kind="run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(
                        run_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    payload=run_payload,
                    now=now,
                    event_id=run_event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_run(run_id, tenant_id)

    def get_run(self, run_id: str, tenant_id: str) -> Dict[str, Any]:
        with self._lock:
            run = self._conn().execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise NotFoundError("run not found")
            if run["tenant_id"] != tenant_id:
                raise ScopeViolation("run is outside tenant scope")
            action = self._conn().execute(
                "SELECT * FROM actions WHERE run_id = ? AND tenant_id = ? ORDER BY created_at LIMIT 1",
                (run_id, tenant_id),
            ).fetchone()
            evidence = None
            if action is not None:
                evidence = self._conn().execute(
                    "SELECT e.* FROM evidence e JOIN action_evidence ae "
                    "ON ae.evidence_id = e.id WHERE ae.action_id = ?",
                    (action["id"],),
                ).fetchone()
        evidence_record = None
        if evidence is not None:
            evidence_record = {
                "evidence_id": evidence["id"],
                "kind": evidence["kind"],
                "status": evidence["status"],
                "provenance": json.loads(evidence["provenance_json"]),
                "result": json.loads(evidence["result_json"]),
                "artifact_ref": evidence["artifact_ref"],
                "supersedes": evidence["supersedes"],
                "created_at": evidence["created_at"],
            }
        return {
            "run_id": run["id"],
            "tenant_id": run["tenant_id"],
            "principal_id": run["principal_id"],
            "plan_id": run["plan_id"],
            "status": run["status"],
            "idempotency_key": run["idempotency_key"],
            "request_digest": run["request_digest"],
            "cancel_requested": bool(run["cancel_requested"]),
            "unknown_reason": run["unknown_reason"],
            "created_at": run["created_at"],
            "finished_at": run["finished_at"],
            "action_id": action["id"] if action is not None else None,
            "tool_id": action["tool_id"] if action is not None else None,
            "action_status": action["status"] if action is not None else None,
            "action_attempt_count": int(action["attempt_count"]) if action is not None else 0,
            "action_timeout_ms": int(action["timeout_ms"]) if action is not None else None,
            "action_max_attempts": int(action["max_attempts"]) if action is not None else None,
            "action_retry_policy": action["retry_policy"] if action is not None else None,
            "action_next_attempt_at": action["next_attempt_at"] if action is not None else None,
            "action_worker_id": action["worker_id"] if action is not None else None,
            "action_lease_until": action["lease_until"] if action is not None else None,
            "action_last_error": action["last_error"] if action is not None else None,
            "action_unknown_reason": action["unknown_reason"] if action is not None else None,
            "evidence": evidence_record,
        }

    def cancel_run(
        self, run_id: str, tenant_id: str, principal_id: str
    ) -> Dict[str, Any]:
        """Cancel before dispatch, or request cancellation for an active lease."""
        now = _timestamp(_utcnow())
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._validate_principal_locked(connection, tenant_id, principal_id)
                run, action = self._action_and_run_locked(connection, run_id, tenant_id)
                if run["status"] in {"succeeded", "failed", "cancelled", "unknown"}:
                    raise ConflictError("run is not cancellable in its current state")
                if run["status"] == "cancel_requested":
                    connection.execute("COMMIT")
                    return self.get_run(run_id, tenant_id)
                if action["status"] in {"queued", "retry", "waiting_approval"}:
                    connection.execute(
                        "UPDATE runs SET status = 'cancelled', finished_at = ?, cancel_requested = 0 "
                        "WHERE id = ? AND tenant_id = ?",
                        (now, run_id, tenant_id),
                    )
                    connection.execute(
                        "UPDATE actions SET status = 'cancelled', finished_at = ?, "
                        "next_attempt_at = NULL, worker_id = NULL, lease_token = NULL, "
                        "lease_until = NULL, cancel_requested = 0 WHERE id = ? AND tenant_id = ?",
                        (now, action["id"], tenant_id),
                    )
                    event_status = "cancelled"
                elif action["status"] == "running":
                    connection.execute(
                        "UPDATE runs SET status = 'cancel_requested', finished_at = NULL, "
                        "cancel_requested = 1 WHERE id = ? AND tenant_id = ?",
                        (run_id, tenant_id),
                    )
                    connection.execute(
                        "UPDATE actions SET status = 'cancel_requested', cancel_requested = 1 "
                        "WHERE id = ? AND tenant_id = ? AND status = 'running'",
                        (action["id"], tenant_id),
                    )
                    event_status = "cancel_requested"
                else:
                    raise ConflictError("run is not cancellable in its current state")
                payload = {
                    "run_id": run_id,
                    "action_id": action["id"],
                    "status": event_status,
                }
                event_id = "evt_" + hash_token(
                    f"{tenant_id}:{run_id}:cancel:{event_status}:{os.urandom(16).hex()}"
                )[:26]
                self._append_audited_event_locked(
                    connection=connection,
                    tenant_id=tenant_id,
                    actor_kind="principal",
                    actor_id=principal_id,
                    action=f"run.{event_status}",
                    target=run_id,
                    outcome="success",
                    event_type=f"run.{event_status}",
                    aggregate_kind="run",
                    aggregate_id=run_id,
                    payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    payload=payload,
                    now=now,
                    event_id=event_id,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_run(run_id, tenant_id)

    def get_run_by_idempotency(self, tenant_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn().execute(
                "SELECT id FROM runs WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return self.get_run(row["id"], tenant_id)

    def oldest_sequence(self, tenant_id: str) -> int:
        with self._lock:
            row = self._conn().execute(
                "SELECT COALESCE(MIN(sequence), 0) AS oldest FROM events WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        return int(row["oldest"])

    def cursor_requires_resync(self, tenant_id: str, after: int) -> bool:
        if after < 0:
            raise ValueError("invalid event cursor")
        oldest = self.oldest_sequence(tenant_id)
        return oldest > 0 and after < oldest - 1

    def prune_events(self, tenant_id: str, retain_latest: int) -> None:
        if retain_latest < 1:
            raise ValueError("retain_latest must be positive")
        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) AS latest FROM events WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
                latest = int(row["latest"])
                threshold = max(latest - retain_latest + 1, 1)
                pending = connection.execute(
                    "SELECT COUNT(*) AS count FROM outbox o JOIN events e ON e.id = o.event_id "
                    "WHERE o.tenant_id = ? AND e.sequence < ? AND o.status != 'delivered'",
                    (tenant_id, threshold),
                ).fetchone()
                if int(pending["count"]) > 0:
                    raise ConflictError("cannot prune events with undelivered outbox records")
                connection.execute(
                    "DELETE FROM outbox WHERE tenant_id = ? AND event_id IN "
                    "(SELECT id FROM events WHERE tenant_id = ? AND sequence < ?)",
                    (tenant_id, tenant_id, threshold),
                )
                connection.execute(
                    "DELETE FROM events WHERE tenant_id = ? AND sequence < ?",
                    (tenant_id, threshold),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
