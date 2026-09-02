"""Typed, policy-gated action broker."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Tuple

from .contracts import RiskTier
from .identity import issue_id
from .policy import Capability, PolicyDecision, PolicyEngine
from .storage import ControlPlaneStore


ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    version: str
    risk_tier: RiskTier
    required_scopes: FrozenSet[str]
    handler: ToolHandler
    evidence_status: str
    disclosure: str
    availability: str = "enabled"
    input_schema_ref: str = "schema.tool.input.v1"
    output_schema_ref: str = "schema.tool.output.v1"
    side_effects: Tuple[str, ...] = ()
    network_egress: str = "none"
    data_classes: Tuple[str, ...] = ()
    timeout_ms: int = 2000
    retry_policy: str = "none"
    approval_policy: str = "never"
    evidence_method_ref: str = "procedure.tool.v1"
    freshness_seconds: int = 60

    def capability(self) -> Capability:
        return Capability(
            capability_id=self.tool_id,
            risk_tier=self.risk_tier,
            required_scopes=self.required_scopes,
            availability=self.availability,
        )

    def manifest(self) -> Dict[str, Any]:
        side_effects = list(self.side_effects)
        if not side_effects and self.risk_tier not in {"R0", "R1"}:
            side_effects = ["local"] if self.risk_tier == "R2" else ["external"] if self.risk_tier in {"R3", "R4"} else ["physical"]
        approval_policy = self.approval_policy
        if approval_policy == "never" and self.risk_tier not in {"R0", "R1"}:
            approval_policy = "operator"
        return {
            "capability_id": self.tool_id,
            "tool_id": self.tool_id,
            "version": self.version,
            "risk_tier": self.risk_tier,
            "input_schema_ref": self.input_schema_ref,
            "output_schema_ref": self.output_schema_ref,
            "required_scopes": sorted(self.required_scopes),
            "side_effects": side_effects,
            "network_egress": self.network_egress,
            "data_classes": list(self.data_classes),
            "timeout_ms": self.timeout_ms,
            "retry_policy": self.retry_policy,
            "approval_policy": approval_policy,
            "evidence_method_ref": self.evidence_method_ref,
            "availability": self.availability,
            "evidence_status": self.evidence_status,
            "disclosure": self.disclosure,
        }


class ToolRegistry:
    """Registry of trusted, code-owned handlers addressed by stable IDs."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if not definition.tool_id or "/" in definition.tool_id or " " in definition.tool_id:
            raise ValueError("tool_id must be a stable registry identifier")
        if definition.tool_id in self._tools:
            raise ValueError("tool_id is already registered")
        if not callable(definition.handler):
            raise TypeError("tool handler must be callable at registration time")
        self._tools[definition.tool_id] = definition

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_id)

    def definitions(self) -> Tuple[ToolDefinition, ...]:
        """Return an immutable snapshot for capability presentation."""
        return tuple(self._tools.values())

    def capabilities(self) -> Mapping[str, Capability]:
        return {tool_id: tool.capability() for tool_id, tool in self._tools.items()}


@dataclass(frozen=True)
class BrokerResult:
    status: str
    decision: str
    run_id: Optional[str]
    action_id: Optional[str]
    evidence: Optional[Dict[str, Any]]
    reasons: Tuple[str, ...]


class ActionBroker:
    def __init__(
        self,
        store: ControlPlaneStore,
        registry: ToolRegistry,
        policy: PolicyEngine,
    ):
        self.store = store
        self.registry = registry
        self.policy = policy

    def preview(
        self,
        tool_id: str,
        requested_risk_tier: RiskTier,
        principal_scopes: FrozenSet[str],
        approved: bool = False,
    ) -> PolicyDecision:
        return self.policy.evaluate(
            capability_id=tool_id,
            requested_risk_tier=requested_risk_tier,
            principal_scopes=principal_scopes,
            approved=approved,
        )

    def execute(
        self,
        tenant_id: str,
        principal_id: str,
        tool_id: str,
        payload: Dict[str, Any],
        requested_risk_tier: RiskTier,
        principal_scopes: FrozenSet[str],
        idempotency_key: str,
        approved: bool = False,
        plan_id: Optional[str] = None,
    ) -> BrokerResult:
        decision = self.preview(
            tool_id=tool_id,
            requested_risk_tier=requested_risk_tier,
            principal_scopes=principal_scopes,
            approved=approved,
        )
        if decision.decision == "deny":
            return BrokerResult(
                status="denied",
                decision=decision.decision,
                run_id=None,
                action_id=None,
                evidence=None,
                reasons=decision.reasons,
            )

        tool = self.registry.get(tool_id)
        if tool is None:
            return BrokerResult(
                status="denied",
                decision="deny",
                run_id=None,
                action_id=None,
                evidence=None,
                reasons=("capability.unavailable",),
            )

        try:
            request_digest = "sha256:" + hashlib.sha256(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        except (TypeError, ValueError):
            return BrokerResult(
                status="denied",
                decision="deny",
                run_id=None,
                action_id=None,
                evidence=None,
                reasons=("payload.invalid",),
            )

        run_id = issue_id("run")
        action_id = issue_id("act")
        initial_status = (
            "waiting_approval" if decision.decision == "allow_with_approval" else "running"
        )
        started = self.store.start_run(
            run_id=run_id,
            action_id=action_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_id=tool_id,
            idempotency_key=idempotency_key,
            status=initial_status,
            plan_id=plan_id,
            request_digest=request_digest,
        )
        run = started["run"]
        if not started["created"]:
            return BrokerResult(
                status=run["status"],
                decision="allow",
                run_id=run["run_id"],
                action_id=run["action_id"],
                evidence=run["evidence"],
                reasons=("idempotency.replay",),
            )
        if initial_status == "waiting_approval":
            return BrokerResult(
                status=initial_status,
                decision=decision.decision,
                run_id=run_id,
                action_id=action_id,
                evidence=None,
                reasons=decision.reasons,
            )

        try:
            result = tool.handler(dict(payload))
            if not isinstance(result, dict):
                raise TypeError("tool result must be an object")
            completed = self.store.complete_run(
                run_id=run_id,
                action_id=action_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                result=result,
                evidence_status=tool.evidence_status,
                provenance={
                    "adapter_id": tool.tool_id,
                    "adapter_version": tool.version,
                    "origin": "local",
                    "input_digest": request_digest,
                    "method_ref": tool.evidence_method_ref,
                    "freshness_seconds": tool.freshness_seconds,
                },
                disclosure=tool.disclosure,
                success=True,
            )
        except Exception:
            completed = self.store.complete_run(
                run_id=run_id,
                action_id=action_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                result={"error_code": "TOOL_FAILED"},
                evidence_status="unknown",
                provenance={
                    "adapter_id": tool.tool_id,
                    "adapter_version": tool.version,
                    "origin": "local",
                    "input_digest": request_digest,
                    "method_ref": tool.evidence_method_ref,
                    "freshness_seconds": tool.freshness_seconds,
                },
                disclosure="Tool execution failed; exception details are not exposed.",
                success=False,
            )
        return BrokerResult(
            status=completed["status"],
            decision=decision.decision,
            run_id=completed["run_id"],
            action_id=completed["action_id"],
            evidence=completed["evidence"],
            reasons=decision.reasons,
        )
