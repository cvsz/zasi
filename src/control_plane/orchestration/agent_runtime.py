"""Supervised agent orchestration service.

The runtime is constructed by :func:`create_app` and bound to
``app.state.agent_service``. It is the only path that can submit a
simulator-gated R2 action. Approvals, replays, and rejections are all
verified against the exact tenant, execution, agent version, tool, and
action digest before the simulator handler is invoked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, Dict, FrozenSet, Optional, Tuple

from .agent_contracts import (
    AgentApprovalDecisionRequest,
    AgentCreateRequest,
    AgentExecutionRequest,
    AgentSandboxRequest,
    AgentVersionCreateRequest,
)
from .agent_models import (
    AgentVersionSpec,
    BudgetPolicy,
    ModelSelection,
    action_digest,
)
from .agent_planner import AgentPlanner
from .agent_tools import register_agent_tools
from ..execution import ActionBroker, ActionWorker, ToolRegistry
from ..identity import issue_id
from ..connectors.model_gateway import ModelGateway
from ..governance.policy import PolicyEngine
from ..storage import ConflictError, ControlPlaneStore, NotFoundError


class AgentServiceError(Exception):
    """Base class for agent runtime errors."""


class ApprovalExpiredError(AgentServiceError):
    pass


class ApprovalMismatchError(AgentServiceError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


class AgentService:
    def __init__(
        self,
        *,
        store: ControlPlaneStore,
        registry: ToolRegistry,
        policy: PolicyEngine,
        broker: ActionBroker,
        gateway: ModelGateway,
        worker_factory=None,
    ):
        self.store = store
        self.registry = registry
        self.policy = policy
        self.broker = broker
        self.gateway = gateway
        self.planner = AgentPlanner(registry=registry, policy=policy, store=store)
        self.worker_factory = worker_factory or (
            lambda: ActionWorker(store=store, registry=registry, worker_id="zasi-agent-worker")
        )

    # ---------- helpers ---------------------------------------------------
    def _spec_from_version_row(self, version: Dict[str, Any]) -> AgentVersionSpec:
        return AgentVersionSpec(
            version=version["version"],
            system_prompt=version["system_prompt"],
            allowed_tools=tuple(version["allowed_tools"]),
            model_policy=dict(version["model_policy"]),
            budget=BudgetPolicy.from_jsonable(version["budget"]),
        )

    def _append_event(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        event_type: str,
        aggregate_kind: str,
        aggregate_id: str,
        payload: Dict[str, Any],
        execution_id: str = "",
        agent_version: str = "",
        correlation_id: str = "",
        causation_id: str = "",
        sensitivity: str = "tenant",
        idempotency_key: str = "",
        schema_version: int = 2,
    ) -> Dict[str, Any]:
        return self.store.append_audited_event(
            tenant_id=tenant_id,
            actor_kind="principal",
            actor_id=actor_id,
            action=action,
            target=aggregate_id,
            outcome="success",
            event_type=event_type,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            payload=payload,
            execution_id=execution_id or None,
            agent_version=agent_version or None,
            correlation_id=correlation_id or None,
            causation_id=causation_id or None,
            sensitivity=sensitivity,
            idempotency_key=idempotency_key or None,
            schema_version=schema_version,
        )

    # ---------- public API ------------------------------------------------
    def create_agent(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        request: AgentCreateRequest,
    ) -> Dict[str, Any]:
        spec = AgentVersionSpec(
            version=request.version,
            system_prompt=request.system_prompt,
            allowed_tools=tuple(request.allowed_tools),
            model_policy=dict(request.model_policy),
            budget=BudgetPolicy.from_jsonable(request.budget.model_dump()),
        )
        agent = self.store.create_agent(
            agent_id=issue_id("agent"),
            tenant_id=tenant_id,
            principal_id=principal_id,
            name=request.name,
            description=request.description,
        )
        version = self.store.create_agent_version(
            version_id=issue_id("aver"),
            agent_id=agent["agent_id"],
            tenant_id=tenant_id,
            version=spec.version,
            system_prompt=spec.system_prompt,
            allowed_tools=list(spec.allowed_tools),
            model_policy=spec.model_policy,
            budget=spec.budget.to_jsonable(),
            digest=spec.digest(),
        )
        return {"agent": agent, "version": version}

    def create_version(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        agent_id: str,
        request: AgentVersionCreateRequest,
    ) -> Dict[str, Any]:
        spec = AgentVersionSpec(
            version=request.version,
            system_prompt=request.system_prompt,
            allowed_tools=tuple(request.allowed_tools),
            model_policy=dict(request.model_policy),
            budget=BudgetPolicy.from_jsonable(request.budget.model_dump()),
        )
        return self.store.create_agent_version(
            version_id=issue_id("aver"),
            agent_id=agent_id,
            tenant_id=tenant_id,
            version=spec.version,
            system_prompt=spec.system_prompt,
            allowed_tools=list(spec.allowed_tools),
            model_policy=spec.model_policy,
            budget=spec.budget.to_jsonable(),
            digest=spec.digest(),
        )

    def publish_version(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        agent_id: str,
        version_id: str,
    ) -> Dict[str, Any]:
        return self.store.publish_agent_version(
            agent_id=agent_id,
            version_id=version_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
        )

    def sandbox(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        agent_id: str,
        request: AgentSandboxRequest,
        scopes: FrozenSet[str],
    ) -> Dict[str, Any]:
        self.store.get_agent(agent_id, tenant_id)
        version = self.store.list_agent_versions(agent_id, tenant_id)
        if not version:
            raise AgentServiceError("agent has no versions")
        published = next((row for row in version if row["status"] == "published"), None)
        if published is None:
            raise AgentServiceError("agent has no published version")
        spec = self._spec_from_version_row(published)
        plan = self.planner.plan(
            version=spec,
            task=request.task,
            ticket_id=request.ticket_id,
            ticket_fields=request.ticket_fields,
            scopes=scopes,
        )
        ok, reasons = self.planner.verify(
            plan=plan,
            version=spec,
            scopes=scopes,
            tenant_id=tenant_id,
            execution_id="sandbox",
        )
        if not ok:
            raise AgentServiceError("sandbox plan rejected: " + ", ".join(reasons))
        selection = self.gateway.select(spec.model_policy)
        ticket_step = plan.steps[1]
        sandbox_digest = action_digest(
            tenant_id=tenant_id,
            execution_id="sandbox",
            agent_version=spec.version,
            tool_id=ticket_step.tool_id,
            tool_version=ticket_step.tool_version,
            payload=ticket_step.input,
        )
        return {
            "agent_id": agent_id,
            "version_id": published["version_id"],
            "version": published["version"],
            "plan": plan.to_jsonable(),
            "model": selection.to_jsonable(),
            "ticket_action_digest": sandbox_digest,
            "disclosures": list(plan.disclosures),
            "sandbox": True,
        }

    def start_execution(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        agent_id: str,
        request: AgentExecutionRequest,
        scopes: FrozenSet[str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        self.store.get_agent(agent_id, tenant_id)
        version = self.store.list_agent_versions(agent_id, tenant_id)
        if not version:
            raise AgentServiceError("agent has no versions")
        published = next((row for row in version if row["status"] == "published"), None)
        if published is None:
            raise AgentServiceError("agent has no published version")
        spec = self._spec_from_version_row(published)
        plan = self.planner.plan(
            version=spec,
            task=request.task,
            ticket_id=request.ticket_id,
            ticket_fields=request.ticket_fields,
            scopes=scopes,
        )
        existing = self.store.get_agent_execution_by_idempotency(tenant_id, idempotency_key)
        if existing is not None:
            return self._replay_execution(existing, scopes=scopes)
        execution_id = issue_id("aexec")
        plan_payload = plan.to_jsonable()
        selection = self.gateway.select(spec.model_policy)
        execution = self.store.create_agent_execution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            agent_id=agent_id,
            agent_version_id=published["version_id"],
            idempotency_key=idempotency_key,
            task=request.task,
            plan=plan_payload,
            model=selection.to_jsonable(),
        )
        correlation_id = execution_id
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="agent.execution.requested",
            event_type="agent.execution.requested",
            aggregate_kind="agent_execution",
            aggregate_id=execution_id,
            payload={"task": request.task, "status": "created"},
            execution_id=execution_id,
            agent_version=spec.version,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="model.selected",
            event_type="model.selected",
            aggregate_kind="model_selection",
            aggregate_id=execution_id,
            payload=selection.to_jsonable(),
            execution_id=execution_id,
            agent_version=spec.version,
            correlation_id=correlation_id,
            causation_id=execution_id,
        )
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="agent.plan.proposed",
            event_type="agent.plan.proposed",
            aggregate_kind="agent_plan",
            aggregate_id=execution_id,
            payload={"plan": plan_payload, "disclosures": list(plan.disclosures)},
            execution_id=execution_id,
            agent_version=spec.version,
            correlation_id=correlation_id,
            causation_id=execution_id,
        )
        ok, reasons = self.planner.verify(
            plan=plan,
            version=spec,
            scopes=scopes,
            tenant_id=tenant_id,
            execution_id=execution_id,
        )
        if not ok:
            self.store.update_agent_execution(
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="failed",
                error={"code": "PLAN_REJECTED", "reasons": list(reasons)},
            )
            self._append_event(
                tenant_id=tenant_id,
                actor_id=principal_id,
                action="policy.evaluated",
                event_type="policy.evaluated",
                aggregate_kind="agent_plan",
                aggregate_id=execution_id,
                payload={"decision": "deny", "reasons": list(reasons)},
                execution_id=execution_id,
                agent_version=spec.version,
                correlation_id=correlation_id,
                causation_id=execution_id,
            )
            raise AgentServiceError("plan rejected: " + ", ".join(reasons))
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="policy.evaluated",
            event_type="policy.evaluated",
            aggregate_kind="agent_plan",
            aggregate_id=execution_id,
            payload={"decision": "allow", "reasons": ["scope.valid", "capability.enabled"]},
            execution_id=execution_id,
            agent_version=spec.version,
            correlation_id=correlation_id,
            causation_id=execution_id,
        )
        self.store.update_agent_execution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            status="running",
        )
        knowledge_step = plan.steps[0]
        knowledge_idempotency = f"{idempotency_key}:knowledge"
        knowledge_result = self.broker.execute(
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_id=knowledge_step.tool_id,
            payload=dict(knowledge_step.input),
            requested_risk_tier=knowledge_step.risk_tier,
            principal_scopes=scopes,
            idempotency_key=knowledge_idempotency,
        )
        if knowledge_result.status not in {"succeeded", "queued"}:
            self.store.update_agent_execution(
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="failed",
                error={"code": "KNOWLEDGE_FAILED", "reasons": list(knowledge_result.reasons)},
            )
            raise AgentServiceError(
                "knowledge step rejected: " + ", ".join(knowledge_result.reasons)
            )
        if knowledge_result.evidence is not None:
            self._append_event(
                tenant_id=tenant_id,
                actor_id=principal_id,
                action="tool.completed",
                event_type="tool.completed",
                aggregate_kind="tool_invocation",
                aggregate_id=knowledge_result.run_id or "knowledge",
                payload={
                    "tool_id": knowledge_step.tool_id,
                    "status": knowledge_result.status,
                    "evidence_id": knowledge_result.evidence.get("evidence_id"),
                },
                execution_id=execution_id,
                agent_version=spec.version,
                correlation_id=correlation_id,
                causation_id=execution_id,
            )
        ticket_step = plan.steps[1]
        ticket_digest = action_digest(
            tenant_id=tenant_id,
            execution_id=execution_id,
            agent_version=spec.version,
            tool_id=ticket_step.tool_id,
            tool_version=ticket_step.tool_version,
            payload=ticket_step.input,
        )
        ticket_idempotency = f"{idempotency_key}:ticket"
        ticket_result = self.broker.submit(
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_id=ticket_step.tool_id,
            payload=dict(ticket_step.input),
            requested_risk_tier=ticket_step.risk_tier,
            principal_scopes=scopes,
            idempotency_key=ticket_idempotency,
        )
        if ticket_result.status == "denied":
            self.store.update_agent_execution(
                execution_id=execution_id,
                tenant_id=tenant_id,
                status="failed",
                error={"code": "TICKET_DENIED", "reasons": list(ticket_result.reasons)},
            )
            raise AgentServiceError(
                "ticket step denied: " + ", ".join(ticket_result.reasons)
            )
        approval = self.store.create_agent_approval(
            approval_id=issue_id("ap"),
            tenant_id=tenant_id,
            execution_id=execution_id,
            agent_version_id=published["version_id"],
            run_id=ticket_result.run_id,
            tool_id=ticket_step.tool_id,
            tool_version=ticket_step.tool_version,
            action_digest=ticket_digest,
            expires_at=_utcnow() + timedelta(minutes=10),
        )
        self.store.update_agent_execution(
            execution_id=execution_id,
            tenant_id=tenant_id,
            status="awaiting_approval",
            knowledge_run_id=knowledge_result.run_id,
            ticket_run_id=ticket_result.run_id,
        )
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="approval.requested",
            event_type="approval.requested",
            aggregate_kind="agent_approval",
            aggregate_id=approval["approval_id"],
            payload={
                "execution_id": execution_id,
                "tool_id": ticket_step.tool_id,
                "tool_version": ticket_step.tool_version,
                "action_digest": ticket_digest,
                "expires_at": approval["expires_at"],
            },
            execution_id=execution_id,
            agent_version=spec.version,
            correlation_id=correlation_id,
            causation_id=execution_id,
        )
        return {
            "execution": self.store.get_agent_execution(execution_id, tenant_id),
            "knowledge": {
                "run_id": knowledge_result.run_id,
                "status": knowledge_result.status,
                "evidence": knowledge_result.evidence,
            },
            "approval": approval,
            "plan": plan_payload,
            "model": selection.to_jsonable(),
            "ticket_action_digest": ticket_digest,
            "disclosures": list(plan.disclosures),
        }

    def resolve_approval(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        approval_id: str,
        request: AgentApprovalDecisionRequest,
        scopes: FrozenSet[str],
        decision: str = "approved",
    ) -> Dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise AgentServiceError("decision must be approved or rejected")
        approval = self.store.get_agent_approval(approval_id, tenant_id)
        if approval["decision"] != "pending":
            return {
                "approval": approval,
                "execution": self.store.get_agent_execution(approval["execution_id"], tenant_id),
                "replay": True,
            }
        if "approval:write" not in scopes:
            raise AgentServiceError("approver scope is required to resolve approvals")
        expires = datetime.fromisoformat(approval["expires_at"])
        if expires <= _utcnow():
            raise ApprovalExpiredError("approval has expired")
        execution = self.store.get_agent_execution(approval["execution_id"], tenant_id)
        if execution["status"] != "awaiting_approval":
            raise AgentServiceError("execution is not awaiting approval")
        resolved = self.store.resolve_agent_approval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            approver_id=principal_id,
            decision=decision,
            reason=request.reason,
        )
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="approval." + resolved["decision"],
            event_type="approval." + resolved["decision"],
            aggregate_kind="agent_approval",
            aggregate_id=approval_id,
            payload={
                "execution_id": approval["execution_id"],
                "decision": resolved["decision"],
                "reason": request.reason,
            },
            execution_id=approval["execution_id"],
            agent_version=resolved["tool_version"],
            correlation_id=approval["execution_id"],
            causation_id=approval_id,
        )
        if resolved["decision"] == "rejected":
            self.store.update_agent_execution(
                execution_id=approval["execution_id"],
                tenant_id=tenant_id,
                status="rejected",
            )
            self._append_event(
                tenant_id=tenant_id,
                actor_id=principal_id,
                action="execution.rejected",
                event_type="execution.rejected",
                aggregate_kind="agent_execution",
                aggregate_id=approval["execution_id"],
                payload={"approval_id": approval_id, "handler_invoked": False},
                execution_id=approval["execution_id"],
                agent_version=resolved["tool_version"],
                correlation_id=approval["execution_id"],
                causation_id=approval_id,
            )
            return {
                "approval": resolved,
                "execution": self.store.get_agent_execution(approval["execution_id"], tenant_id),
            }
        worker = self.worker_factory()
        completed = worker.run_simulated_once(
            tenant_id=tenant_id,
            run_id=approval["run_id"],
            approval_id=approval_id,
            action_digest=approval["action_digest"],
            agent_version=resolved["tool_version"],
            execution_id=approval["execution_id"],
            principal_id=principal_id,
        )
        if completed is None or completed.get("status") != "succeeded":
            self.store.update_agent_execution(
                execution_id=approval["execution_id"],
                tenant_id=tenant_id,
                status="failed",
                error={"code": "SIMULATOR_FAILED"},
            )
            raise AgentServiceError("simulator did not produce a successful result")
        self.store.update_agent_execution(
            execution_id=approval["execution_id"],
            tenant_id=tenant_id,
            status="completed",
            result=completed.get("result", {}),
        )
        self._append_event(
            tenant_id=tenant_id,
            actor_id=principal_id,
            action="execution.completed",
            event_type="execution.completed",
            aggregate_kind="agent_execution",
            aggregate_id=approval["execution_id"],
            payload={"status": "completed", "result": completed.get("result", {})},
            execution_id=approval["execution_id"],
            agent_version=resolved["tool_version"],
            correlation_id=approval["execution_id"],
            causation_id=approval_id,
        )
        return {
            "approval": resolved,
            "execution": self.store.get_agent_execution(approval["execution_id"], tenant_id),
            "simulator_evidence": completed.get("evidence"),
        }

    def get_execution(self, *, tenant_id: str, execution_id: str) -> Dict[str, Any]:
        return self.store.get_agent_execution(execution_id, tenant_id)

    def list_executions(self, *, tenant_id: str, agent_id: Optional[str] = None) -> list:
        return self.store.list_agent_executions(tenant_id, agent_id=agent_id)

    def list_approvals(self, *, tenant_id: str, decision: Optional[str] = "pending") -> list:
        return self.store.list_agent_approvals(tenant_id, decision=decision)

    def list_agents(self, *, tenant_id: str) -> list:
        return self.store.list_agents(tenant_id)

    def get_agent(self, *, tenant_id: str, agent_id: str) -> Dict[str, Any]:
        return self.store.get_agent(agent_id, tenant_id)

    def get_version(self, *, tenant_id: str, version_id: str) -> Dict[str, Any]:
        return self.store.get_agent_version(version_id, tenant_id)

    def list_versions(self, *, tenant_id: str, agent_id: str) -> list:
        return self.store.list_agent_versions(agent_id, tenant_id)

    def model_status(self) -> Dict[str, Any]:
        return self.gateway.status()

    def summary(self, *, tenant_id: str) -> Dict[str, Any]:
        return self.store.agent_summary(tenant_id)

    # ---------- internal helpers -----------------------------------------
    def _replay_execution(
        self,
        existing: Dict[str, Any],
        *,
        scopes: FrozenSet[str],
    ) -> Dict[str, Any]:
        approvals = self.store.list_agent_approvals(
            existing["tenant_id"], decision=None
        )
        approval = next(
            (row for row in approvals if row["execution_id"] == existing["execution_id"]),
            None,
        )
        return {
            "execution": existing,
            "knowledge": None,
            "approval": approval,
            "plan": existing["plan"],
            "model": existing["model"],
            "ticket_action_digest": approval["action_digest"] if approval else None,
            "disclosures": ["Replay returns the original durable record."],
            "replay": True,
        }


def register_agent_runtime(
    *,
    store: ControlPlaneStore,
    registry: ToolRegistry,
    settings=None,
) -> AgentService:
    from ..config import Settings

    if settings is None:
        settings = Settings.from_mapping()
    register_agent_tools(registry, store)
    policy = PolicyEngine(registry.capabilities())
    broker = ActionBroker(store=store, registry=registry, policy=policy)
    gateway = ModelGateway(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    return AgentService(
        store=store,
        registry=registry,
        policy=policy,
        broker=broker,
        gateway=gateway,
    )


__all__ = [
    "AgentService",
    "AgentServiceError",
    "ApprovalExpiredError",
    "ApprovalMismatchError",
    "register_agent_runtime",
]
