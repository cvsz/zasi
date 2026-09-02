"""PostgreSQL repository implementation for multi-process control-plane state.

The public repository contract lives in :mod:`storage`.  This module keeps the
same record/transaction semantics while using a real PostgreSQL connection,
server-side constraints, and an application-level connection lock for the
sync methods used by the FastAPI application.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from .storage import CURRENT_SCHEMA_VERSION, ControlPlaneStore


_POSTGRES_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        policy_version TEXT NOT NULL DEFAULT 'policy.v1',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS principals (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        label TEXT NOT NULL DEFAULT 'device',
        status TEXT NOT NULL,
        enrollment_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen_at TEXT,
        revoked_at TEXT
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capabilities (
        id TEXT PRIMARY KEY,
        tenant_id TEXT,
        tool_id TEXT NOT NULL,
        version TEXT NOT NULL,
        risk_tier TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_evidence (
        action_id TEXT PRIMARY KEY REFERENCES actions(id),
        evidence_id TEXT NOT NULL REFERENCES evidence(id)
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rate_limits (
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        subject TEXT NOT NULL,
        bucket BIGINT NOT NULL,
        count INTEGER NOT NULL,
        reset_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, subject, bucket)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        principal_id TEXT NOT NULL REFERENCES principals(id),
        digest TEXT NOT NULL,
        media_type TEXT NOT NULL,
        size_bytes BIGINT NOT NULL,
        status TEXT NOT NULL,
        storage_ref TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS briefings (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        principal_id TEXT NOT NULL REFERENCES principals(id),
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_dependencies (
        tenant_id TEXT NOT NULL REFERENCES tenants(id),
        task_id TEXT NOT NULL REFERENCES tasks(id),
        depends_on_task_id TEXT NOT NULL REFERENCES tasks(id),
        PRIMARY KEY (task_id, depends_on_task_id)
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS principal_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS cancel_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE runs ADD COLUMN IF NOT EXISTS unknown_reason TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS payload_json TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS timeout_ms INTEGER NOT NULL DEFAULT 2000",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS retry_policy TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS next_attempt_at TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS worker_id TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS lease_token TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS lease_until TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS last_error TEXT",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS cancel_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE actions ADD COLUMN IF NOT EXISTS unknown_reason TEXT",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS lease_owner TEXT",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS memory_type TEXT NOT NULL DEFAULT 'conversation'",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS project_id TEXT",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS source_ref TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS provenance_json TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS trust TEXT NOT NULL DEFAULT 'operator'",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS last_verified_at TEXT",
    "ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS fresh_until TEXT",
    "CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id, status, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_tenant_sequence ON events(tenant_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_runs_tenant_idempotency ON runs(tenant_id, idempotency_key)",
    "CREATE INDEX IF NOT EXISTS idx_actions_claimable ON actions(status, next_attempt_at, lease_until)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_tenant_plan ON approvals(tenant_id, plan_id, decision, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(status, next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS idx_devices_tenant ON devices(tenant_id, status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sequences_tenant ON sequences(tenant_id, status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_sequence_runs_tenant_idempotency ON sequence_runs(tenant_id, idempotency_key)",
    "CREATE INDEX IF NOT EXISTS idx_goals_tenant_status ON goals(tenant_id, status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_tenant_status_due ON tasks(tenant_id, status, not_before, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_task_dependencies_task ON task_dependencies(tenant_id, task_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_schedules_tenant_idempotency ON schedules(tenant_id, idempotency_key)",
    "CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(tenant_id, status, next_run_at)",
    "CREATE INDEX IF NOT EXISTS idx_task_runs_task_history ON task_runs(tenant_id, task_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_task_runs_claimable ON task_runs(tenant_id, status, lease_until, scheduled_for)",
    "CREATE INDEX IF NOT EXISTS idx_memory_project_scope ON memory_items(tenant_id, project_id, status, created_at)",
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pairing_tenant_idempotency "
        "ON device_pairing_challenges(tenant_id, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    ),
)


class _PostgresConnection:
    """Small DB-API surface compatible with the inherited repository methods."""

    _TABLE_INFO = re.compile(r"^PRAGMA\s+table_info\(([^)]+)\)$", re.IGNORECASE)

    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, statement: str, parameters: Any = None) -> Any:
        sql = statement.strip()
        table_info = self._TABLE_INFO.match(sql)
        if table_info:
            table_name = table_info.group(1).strip().strip('"')
            return self._connection.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
        if sql.upper() == "PRAGMA FOREIGN_KEYS = ON":
            return self._connection.execute("SELECT 1")
        if sql.upper() in {
            "PRAGMA JOURNAL_MODE = WAL",
            "PRAGMA SYNCHRONOUS = NORMAL",
            "PRAGMA BUSY_TIMEOUT = 5000",
        }:
            return self._connection.execute("SELECT 1")
        sql = sql.replace("BEGIN IMMEDIATE", "BEGIN")
        if sql.upper().startswith("INSERT OR IGNORE INTO "):
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO", 1)
            sql = f"{sql} ON CONFLICT DO NOTHING"
        if sql.upper().startswith("INSERT OR REPLACE INTO SCHEMA_META"):
            sql = sql.replace("INSERT OR REPLACE INTO", "INSERT INTO", 1)
            sql = f"{sql} ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        sql = sql.replace("?", "%s")
        if parameters is None:
            return self._connection.execute(sql)
        return self._connection.execute(sql, parameters)

    def close(self) -> None:
        self._connection.close()

    def lock_event_sequence(self, tenant_id: str) -> None:
        """Serialize per-tenant event sequence allocation across processes."""
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (tenant_id,),
        )


class PostgresControlPlaneStore(ControlPlaneStore):
    """Durable PostgreSQL implementation of the control-plane repository."""

    def __init__(self, database_url: str):
        if not database_url or not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("database_url must use a PostgreSQL scheme")
        super().__init__(database_url)
        self.database_url = database_url

    def initialize(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL profiles require the psycopg package"
                ) from exc
            raw_connection = psycopg.connect(
                self.database_url,
                autocommit=True,
                connect_timeout=5,
                application_name="zasi-control-plane",
                row_factory=dict_row,
            )
            connection = _PostgresConnection(raw_connection)
            try:
                for statement in _POSTGRES_SCHEMA_STATEMENTS:
                    connection.execute(statement)
                schema_row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                if schema_row is not None and int(schema_row["value"]) > CURRENT_SCHEMA_VERSION:
                    raise RuntimeError("database schema is newer than this application")
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (str(CURRENT_SCHEMA_VERSION),),
                )
            except Exception:
                connection.close()
                raise
            self._connection = connection

    def integrity_check(self) -> bool:
        with self._lock:
            row = self._conn().execute("SELECT 1 AS ok").fetchone()
        return bool(row and int(row["ok"]) == 1)

    def backup_to(self, backup_path: str) -> None:
        """Create a non-destructive PostgreSQL custom-format backup."""
        if not backup_path:
            raise ValueError("backup path must be a filesystem path")
        dump_path = Path(backup_path).resolve()
        if dump_path.exists() and dump_path.is_dir():
            raise ValueError("backup path must be a file path")
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        pg_dump = shutil.which("pg_dump")
        if pg_dump is None:
            raise RuntimeError("pg_dump is required for PostgreSQL backups")

        parsed = urlsplit(self.database_url)
        password = unquote(parsed.password or "")
        if password:
            username = quote(unquote(parsed.username or ""), safe="")
            hostname = parsed.hostname or ""
            host_part = hostname
            if ":" in hostname and not hostname.startswith("["):
                host_part = f"[{hostname}]"
            if parsed.port is not None:
                host_part = f"{host_part}:{parsed.port}"
            safe_url = urlunsplit(
                (parsed.scheme, f"{username}@{host_part}", parsed.path, parsed.query, "")
            )
        else:
            safe_url = self.database_url
        environment = os.environ.copy()
        if password:
            environment["PGPASSWORD"] = password
        try:
            subprocess.run(
                [pg_dump, "--format=custom", "--file", str(dump_path), safe_url],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("PostgreSQL backup failed") from exc
