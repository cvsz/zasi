"""Deterministic, fail-closed typed planner for the agent platform.

The reference planner produces exactly two ordered steps for the safe demo
workflow:

1. ``knowledge.search`` at risk tier R0 (read-only tenant memory).
2. ``ticket.update`` at risk tier R2 (approval-gated simulated local write).

The planner refuses to emit any plan whose tools are not registered, enabled,
and currently published. It also refuses to underdeclare or overdeclare the
risk tier and refuses to bypass scope requirements.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Mapping, Tuple

from ..agent_models import (
    AgentVersionSpec,
    PlanStep,
    TypedAgentPlan,
    action_digest,
    canonicalize_action_payload,
)
from ..execution import ToolDefinition, ToolRegistry
from ..governance.policy import PolicyEngine
from ..storage import ControlPlaneStore


_RISK_BY_TOOL = {
    "knowledge.search": "R0",
    "ticket.update": "R2",
}
_DEMO_PLAN_TOOLS: Tuple[str, ...] = ("knowledge.search", "ticket.update")
_DEMO_PLAN_DISCLOSURES: Tuple[str, ...] = (
    "Deterministic safe demo plan. No external services are contacted.",
    "The second step is a simulated local write; it must be approved before any action is invoked.",
)


class AgentPlanner:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyEngine,
        store: ControlPlaneStore = None,
    ):
        self.registry = registry
        self.policy = policy
        self.store = store

    def plan(
        self,
        *,
        version: AgentVersionSpec,
        task: str,
        ticket_id: str,
        ticket_fields: Mapping[str, Any],
        scopes: FrozenSet[str],
    ) -> TypedAgentPlan:
        if not isinstance(task, str) or not task:
            raise ValueError("task must be a non-empty string")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise ValueError("ticket_id must be a non-empty string")
        if not isinstance(ticket_fields, Mapping):
            raise ValueError("ticket_fields must be an object")

        canonical_fields = canonicalize_action_payload(dict(ticket_fields))
        steps: list[PlanStep] = []

        knowledge_input = canonicalize_action_payload(
            {"query": task, "scope": "tenant"}
        )
        steps.append(
            PlanStep(
                step_id="step-knowledge",
                tool_id="knowledge.search",
                tool_version="1.0.0",
                risk_tier="R0",
                input=knowledge_input,
                preconditions=("memory.tenant.active",),
                expected_effects=("knowledge.snippets",),
            )
        )
        steps.append(
            PlanStep(
                step_id="step-ticket",
                tool_id="ticket.update",
                tool_version="1.0.0",
                risk_tier="R2",
                input=canonicalize_action_payload(
                    {"ticket_id": ticket_id, "fields": canonical_fields}
                ),
                preconditions=("approval.required",),
                expected_effects=("ticket.simulated",),
            )
        )
        plan = TypedAgentPlan(steps=tuple(steps), disclosures=_DEMO_PLAN_DISCLOSURES)
        return plan

    def verify(
        self,
        *,
        plan: TypedAgentPlan,
        version: AgentVersionSpec,
        scopes: FrozenSet[str],
        tenant_id: str = "",
        execution_id: str = "",
    ) -> Tuple[bool, Tuple[str, ...]]:
        reasons: list[str] = []
        allowed = set(version.allowed_tools)
        if not allowed:
            reasons.append("version.allowed_tools.empty")
            return False, tuple(reasons)
        seen_tools: set[str] = set()
        if not plan.steps:
            reasons.append("plan.empty")
        for index, step in enumerate(plan.steps):
            if step.tool_id not in _DEMO_PLAN_TOOLS:
                reasons.append(f"step.{index}.tool_unrecognised")
            if step.tool_id not in allowed:
                reasons.append(f"step.{index}.tool_not_allowed")
            if step.tool_id in seen_tools:
                reasons.append(f"step.{index}.tool_duplicate")
            seen_tools.add(step.tool_id)
            tool = self.registry.get(step.tool_id)
            if tool is None:
                reasons.append(f"step.{index}.capability.unavailable")
                continue
            if tool.availability != "enabled":
                reasons.append(f"step.{index}.capability.disabled")
            if tool.version != step.tool_version:
                reasons.append(f"step.{index}.tool.version_mismatch")
            if step.risk_tier != tool.risk_tier:
                reasons.append(f"step.{index}.risk.mismatch")
            missing = sorted(set(tool.required_scopes) - set(scopes))
            if missing:
                reasons.append(f"step.{index}.scope.missing:" + ",".join(missing))
            if tool.network_egress != "none":
                reasons.append(f"step.{index}.egress.forbidden")
            if "external" in tool.side_effects or "physical" in tool.side_effects:
                reasons.append(f"step.{index}.side_effects.forbidden")
        if tenant_id and execution_id:
            for step in plan.steps:
                if step.tool_id == "ticket.update":
                    digest = action_digest(
                        tenant_id=tenant_id,
                        execution_id=execution_id,
                        agent_version=version.version,
                        tool_id=step.tool_id,
                        tool_version=step.tool_version,
                        payload=step.input,
                    )
                    if not digest:
                        reasons.append("step.ticket.action_digest.uncomputable")
        if reasons:
            return False, tuple(reasons)
        return True, ()


__all__ = ["AgentPlanner"]
