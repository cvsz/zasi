"""First-release tools for the AI Futures agent platform.

Two bounded, code-owned tools are registered:

- ``knowledge.search`` (R0, read-only, tenant-scoped, no egress)
- ``ticket.update`` (R2, approval-gated, simulated local write)

Both tools are context-aware: the runtime injects the authenticated tenant,
principal, and action context. The tools ignore any conflicting fields in
the payload. The handlers never call an external service.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agent_models import required_scopes_for
from ..execution import ToolDefinition, ToolExecutionContext, ToolRegistry
from ..storage import ControlPlaneStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _tenant_knowledge_search(
    payload: Dict[str, Any],
    *,
    context: Dict[str, Any],
    store: ControlPlaneStore,
) -> Dict[str, Any]:
    tenant_id = context.get("tenant_id", "")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("tenant_id is required for knowledge search")
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query is required for knowledge search")
    project_id = payload.get("project_id") or None
    limit = payload.get("limit", 5)
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        limit = 5
    try:
        rows = store._conn().execute(
            "SELECT id, content, memory_type, source_ref, provenance_json, "
            "last_verified_at, fresh_until FROM memory_items "
            "WHERE tenant_id = ? AND status = 'active' "
            "AND (fresh_until IS NULL OR fresh_until > ?) "
            "AND (project_id IS NULL OR project_id = ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant_id, _iso(_utcnow()), project_id, limit),
        ).fetchall()
    except Exception:
        rows = []
    snippets: List[Dict[str, Any]] = []
    for row in rows:
        provenance = {}
        try:
            provenance = json.loads(row["provenance_json"])
        except (TypeError, ValueError):
            provenance = {}
        snippets.append(
            {
                "memory_id": row["id"],
                "snippet": (row["content"] or "")[:280],
                "memory_type": row["memory_type"],
                "source_ref": row["source_ref"],
                "provenance": provenance,
                "last_verified_at": row["last_verified_at"],
                "fresh_until": row["fresh_until"],
            }
        )
    digest_input = {"query": query, "tenant_id": tenant_id, "count": len(snippets)}
    digest = "sha256:" + hashlib.sha256(
        _canonical(digest_input).encode("utf-8")
    ).hexdigest()
    return {
        "query": query,
        "tenant_id": tenant_id,
        "count": len(snippets),
        "snippets": snippets,
        "disclosure": "Local read-only search. No external services are contacted.",
        "evidence_status": "verified",
        "result_digest": digest,
    }


def _tenant_ticket_update(
    payload: Dict[str, Any],
    *,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    tenant_id = context.get("tenant_id", "")
    execution_id = context.get("execution_id", "")
    agent_version = context.get("agent_version", "")
    run_id = context.get("run_id", "")
    approval_id = context.get("approval_id", "")
    action_digest = context.get("action_digest", "")
    if not all(
        isinstance(value, str) and value
        for value in (tenant_id, execution_id, agent_version, run_id, approval_id, action_digest)
    ):
        raise ValueError("ticket.update requires a validated approval context")
    ticket_id = str(payload.get("ticket_id", "")).strip()
    fields = payload.get("fields", {})
    if not ticket_id:
        raise ValueError("ticket_id is required for ticket.update")
    if not isinstance(fields, dict) or not fields:
        raise ValueError("fields must be a non-empty object")
    before = {"ticket_id": ticket_id, "fields": {}}
    after = {"ticket_id": ticket_id, "fields": dict(fields)}
    return {
        "tenant_id": tenant_id,
        "execution_id": execution_id,
        "agent_version": agent_version,
        "run_id": run_id,
        "approval_id": approval_id,
        "action_digest": action_digest,
        "before": before,
        "after": after,
        "simulated": True,
        "external_write": False,
        "evidence_status": "simulated",
        "disclosure": (
            "This is a deterministic local simulation. No ticket system was contacted and no external write was attempted."
        ),
    }


def _knowledge_handler(
    payload: Dict[str, Any],
    *,
    context: Optional[Dict[str, Any]] = None,
    store: Optional[ControlPlaneStore] = None,
) -> Dict[str, Any]:
    if context is None or store is None:
        raise ValueError("knowledge.search requires a tenant context")
    return _tenant_knowledge_search(payload, context=context, store=store)


def _ticket_handler(
    payload: Dict[str, Any],
    *,
    context: Optional[Dict[str, Any]] = None,
    store: Optional[ControlPlaneStore] = None,
) -> Dict[str, Any]:
    if context is None:
        raise ValueError("ticket.update requires an approval context")
    return _tenant_ticket_update(payload, context=context)


def register_agent_tools(
    registry: ToolRegistry,
    store: ControlPlaneStore,
) -> None:
    """Register the safe agent tools on the given registry."""

    def knowledge_runner(
        payload: Dict[str, Any],
        *,
        context: ToolExecutionContext,
        store: Optional[ControlPlaneStore] = None,
    ) -> Dict[str, Any]:
        if store is None:
            store = _default_store()
        return _tenant_knowledge_search(
            payload,
            context={
                "tenant_id": context.tenant_id,
                "principal_id": context.principal_id,
                "run_id": context.run_id,
                "action_id": context.action_id,
            },
            store=store,
        )

    def ticket_runner(
        payload: Dict[str, Any],
        *,
        context: ToolExecutionContext,
    ) -> Dict[str, Any]:
        return _tenant_ticket_update(
            payload,
            context={
                "tenant_id": context.tenant_id,
                "principal_id": context.principal_id,
                "run_id": context.run_id,
                "action_id": context.action_id,
                "execution_id": context.execution_id,
                "agent_version": context.agent_version,
                "approval_id": context.approval_id,
                "action_digest": context.action_digest,
            },
        )

    knowledge = ToolDefinition(
        tool_id="knowledge.search",
        version="1.0.0",
        risk_tier="R0",
        required_scopes=required_scopes_for("knowledge.search"),
        handler=knowledge_runner,
        evidence_status="verified",
        disclosure=(
            "Local read-only tenant memory search. No external services are contacted."
        ),
        network_egress="none",
        side_effects=(),
        data_classes=("workspace",),
        timeout_ms=2000,
        max_attempts=1,
        retry_policy="none",
        approval_policy="never",
        context_aware=True,
    )
    ticket = ToolDefinition(
        tool_id="ticket.update",
        version="1.0.0",
        risk_tier="R2",
        required_scopes=required_scopes_for("ticket.update"),
        handler=ticket_runner,
        evidence_status="simulated",
        disclosure=(
            "Deterministic local simulator. No external ticket system is contacted."
        ),
        network_egress="none",
        side_effects=("simulated_local",),
        data_classes=("workspace",),
        timeout_ms=2000,
        max_attempts=1,
        retry_policy="none",
        approval_policy="operator",
        context_aware=True,
    )
    registry.register(knowledge)
    registry.register(ticket)


def is_agent_tool(tool_id: str) -> bool:
    return tool_id in {"knowledge.search", "ticket.update"}


__all__ = [
    "is_agent_tool",
    "register_agent_tools",
]


_RISK_BY_TOOL_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
