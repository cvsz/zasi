"""Typed, policy-gated action broker."""

from dataclasses import dataclass
import hashlib
import inspect
import json
import threading
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Tuple

from .contracts import RiskTier
from .identity import issue_id
from .policy import Capability, PolicyDecision, PolicyEngine
from .storage import ControlPlaneStore


ToolHandler = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class ToolExecutionContext:
    """Authenticated, tenant-scoped execution context for context-aware tools.

    The runtime injects this context; reserved internal fields cannot be
    overridden by the user payload.
    """

    tenant_id: str
    principal_id: str
    run_id: str
    action_id: str
    execution_id: str = ""
    agent_version: str = ""
    approval_id: str = ""
    action_digest: str = ""


def _context_aware(handler: ToolHandler) -> bool:
    """Detect whether a handler was registered as context-aware."""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    return "context" in signature.parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


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
    max_attempts: int = 1
    retry_policy: str = "none"
    approval_policy: str = "never"
    evidence_method_ref: str = "procedure.tool.v1"
    freshness_seconds: int = 60
    context_aware: bool = False

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
            "max_attempts": self.max_attempts,
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
        if not 1 <= definition.timeout_ms <= 86_400_000:
            raise ValueError("tool timeout must be between 1 and 86400000 milliseconds")
        if not 1 <= definition.max_attempts <= 10:
            raise ValueError("tool max_attempts must be between 1 and 10")
        if definition.retry_policy not in {"none", "bounded"}:
            raise ValueError("tool retry_policy must be none or bounded")
        if definition.retry_policy == "none" and definition.max_attempts != 1:
            raise ValueError("retry_policy=none requires max_attempts=1")
        if definition.context_aware and not _context_aware(definition.handler):
            raise ValueError("context_aware=True requires a handler that accepts a context kwarg")
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

    def submit(
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
            "waiting_approval" if decision.decision == "allow_with_approval" else "queued"
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
            payload=payload,
            timeout_ms=tool.timeout_ms,
            max_attempts=tool.max_attempts,
            retry_policy=tool.retry_policy,
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

        return BrokerResult(
            status=run["status"],
            decision=decision.decision,
            run_id=run_id,
            action_id=action_id,
            evidence=run["evidence"],
            reasons=decision.reasons,
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
        """Submit durably, then drain one bounded action through the worker.

        The inline drain preserves the reference API's synchronous response for
        short local observations while retaining a durable queued state that a
        separately supervised worker can claim after a disconnect or restart.
        The broker never invokes a tool handler directly.
        """
        submitted = self.submit(
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_id=tool_id,
            payload=payload,
            requested_risk_tier=requested_risk_tier,
            principal_scopes=principal_scopes,
            idempotency_key=idempotency_key,
            approved=approved,
            plan_id=plan_id,
        )
        if submitted.status != "queued" or submitted.run_id is None:
            return submitted
        tool = self.registry.get(tool_id)
        if tool is None or tool.risk_tier not in {"R0", "R1"}:
            # Risk-bearing actions remain durable and queued for a separately
            # governed worker; the application process never drains them.
            return submitted
        ActionWorker(
            store=self.store,
            registry=self.registry,
            worker_id="zasi-inline-action-worker",
        ).run_once(tenant_id, submitted.run_id)
        run = self.store.get_run(submitted.run_id, tenant_id)
        return BrokerResult(
            status=run["status"],
            decision=submitted.decision,
            run_id=run["run_id"],
            action_id=run["action_id"],
            evidence=run["evidence"],
            reasons=submitted.reasons,
        )


class ActionWorker:
    """Claim and execute one durable action with fail-closed uncertainty.

    A timed-out handler is intentionally not retried: Python cannot revoke an
    arbitrary callable that may still be executing. The durable result becomes
    ``unknown`` and requires explicit reconciliation before another attempt.
    """

    def __init__(
        self,
        store: ControlPlaneStore,
        registry: ToolRegistry,
        worker_id: str = "zasi-action-worker",
        lease_seconds: int = 60,
        allowed_risk_tiers: FrozenSet[RiskTier] = frozenset({"R0", "R1"}),
    ):
        self.store = store
        self.registry = registry
        self.store._validate_worker_id(worker_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 3600
        ):
            raise ValueError("lease_seconds must be between 1 and 3600")
        if not allowed_risk_tiers or not set(allowed_risk_tiers).issubset(
            {"R0", "R1", "R2", "R3", "R4", "R5"}
        ):
            raise ValueError("allowed_risk_tiers must contain valid risk tiers")
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.allowed_risk_tiers = frozenset(allowed_risk_tiers)

    @staticmethod
    def _side_effect_may_be_uncertain(tool: ToolDefinition) -> bool:
        return (
            tool.risk_tier not in {"R0", "R1"}
            or tool.network_egress != "none"
            or "external" in tool.side_effects
            or "physical" in tool.side_effects
        )

    def run_simulated_once(
        self,
        tenant_id: str,
        run_id: str,
        *,
        approval_id: str,
        action_digest: str,
        agent_version: str = "",
        execution_id: str = "",
        principal_id: str = "",
        now: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a previously approved R2 simulated action once.

        The path refuses any tool that is not currently registered, is not
        enabled, is not at the approved risk tier (R2), is not network-egress
        ``none``, and does not declare ``simulated_local`` as a side effect.
        Replays with the same approval ID and action digest return the
        original durable result without invoking the handler twice.
        """
        current = self.store.get_run(run_id, tenant_id)
        tool = self.registry.get(current["tool_id"])
        if tool is None:
            return current
        if (
            tool.risk_tier != "R2"
            or tool.network_egress != "none"
            or "simulated_local" not in tool.side_effects
        ):
            return current
        if current["action_status"] == "succeeded":
            return current
        claim = self.store.claim_action(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            now=now,
        )
        if claim is None:
            return self.store.get_run(run_id, tenant_id)
        payload_json = json.dumps(
            claim["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        provenance = {
            "adapter_id": claim["tool_id"],
            "adapter_version": tool.version,
            "origin": "simulator-worker",
            "input_digest": "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            "method_ref": tool.evidence_method_ref,
            "freshness_seconds": tool.freshness_seconds,
            "approval_id": approval_id,
            "action_digest": action_digest,
            "execution_id": execution_id,
            "agent_version": agent_version,
        }
        outcome: Dict[str, Any] = {}

        def invoke() -> None:
            try:
                context = ToolExecutionContext(
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    run_id=claim["run_id"],
                    action_id=claim["action_id"],
                    execution_id=execution_id,
                    agent_version=agent_version,
                    approval_id=approval_id,
                    action_digest=action_digest,
                )
                result = tool.handler(dict(claim["payload"]), context=context)
                if not isinstance(result, dict):
                    raise TypeError("tool result must be an object")
                outcome["result"] = result
            except Exception:
                outcome["error"] = True

        thread = threading.Thread(
            target=invoke,
            name=f"zasi-simulator-{claim['action_id']}",
            daemon=True,
        )
        thread.start()
        thread.join(max(0.001, claim["timeout_ms"] / 1000.0))
        if thread.is_alive():
            return self.store.finish_action(
                run_id,
                tenant_id,
                self.worker_id,
                claim["lease_token"],
                "unknown",
                result={"error_code": "ACTION_TIMEOUT"},
                evidence_status="unknown",
                provenance=provenance,
                disclosure=(
                    "The simulator exceeded its deadline; the side-effect status is unknown and requires reconciliation."
                ),
                unknown_reason="action_timeout",
            )
        if "error" in outcome:
            return self.store.finish_action(
                run_id,
                tenant_id,
                self.worker_id,
                claim["lease_token"],
                "unknown",
                result={"error_code": "ACTION_OUTCOME_UNKNOWN"},
                evidence_status="unknown",
                provenance=provenance,
                disclosure=(
                    "The simulator failed and the side-effect status is unknown; reconciliation is required."
                ),
                unknown_reason="side_effect_uncertain",
            )
        return self.store.finish_action(
            run_id,
            tenant_id,
            self.worker_id,
            claim["lease_token"],
            "succeeded",
            result=outcome["result"],
            evidence_status=tool.evidence_status,
            provenance=provenance,
            disclosure=tool.disclosure,
        )

    def run_once(
        self,
        tenant_id: str,
        run_id: Optional[str] = None,
        now: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        if run_id is None:
            claimable = self.store.list_claimable_actions(tenant_id, limit=100, now=now)
            claimable = [
                item
                for item in claimable
                if (
                    self.registry.get(item["tool_id"]) is None
                    or self.registry.get(item["tool_id"]).risk_tier in self.allowed_risk_tiers
                )
            ]
            if not claimable:
                return None
            run_id = claimable[0]["run_id"]
        else:
            current = self.store.get_run(run_id, tenant_id)
            current_tool = self.registry.get(current["tool_id"])
            if current_tool is not None and current_tool.risk_tier not in self.allowed_risk_tiers:
                return current
        claim = self.store.claim_action(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            now=now,
        )
        if claim is None:
            return self.store.get_run(run_id, tenant_id)
        tool = self.registry.get(claim["tool_id"])
        payload_json = json.dumps(
            claim["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        provenance = {
            "adapter_id": claim["tool_id"],
            "adapter_version": tool.version if tool is not None else "unknown",
            "origin": "local-worker",
            "input_digest": "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            "method_ref": tool.evidence_method_ref if tool is not None else "procedure.action.unavailable.v1",
            "freshness_seconds": tool.freshness_seconds if tool is not None else 0,
        }
        if tool is None:
            return self.store.finish_action(
                run_id,
                tenant_id,
                self.worker_id,
                claim["lease_token"],
                "unknown",
                result={"error_code": "CAPABILITY_UNAVAILABLE"},
                evidence_status="unknown",
                provenance=provenance,
                disclosure="The registered tool was unavailable when the worker claimed the action.",
                unknown_reason="tool_unavailable",
            )

        outcome: Dict[str, Any] = {}

        def invoke() -> None:
            try:
                if tool.context_aware:
                    context = ToolExecutionContext(
                        tenant_id=tenant_id,
                        principal_id=self.store._principal_for_run(claim["run_id"])
                        if hasattr(self.store, "_principal_for_run")
                        else "",
                        run_id=claim["run_id"],
                        action_id=claim["action_id"],
                    )
                    result = tool.handler(dict(claim["payload"]), context=context, store=self.store)
                else:
                    result = tool.handler(dict(claim["payload"]))
                if not isinstance(result, dict):
                    raise TypeError("tool result must be an object")
                outcome["result"] = result
            except Exception:
                outcome["error"] = True

        thread = threading.Thread(
            target=invoke,
            name=f"zasi-action-{claim['action_id']}",
            daemon=True,
        )
        thread.start()
        thread.join(max(0.001, claim["timeout_ms"] / 1000.0))
        if thread.is_alive():
            return self.store.finish_action(
                run_id,
                tenant_id,
                self.worker_id,
                claim["lease_token"],
                "unknown",
                result={"error_code": "ACTION_TIMEOUT"},
                evidence_status="unknown",
                provenance=provenance,
                disclosure="The action exceeded its deadline; its side effect status is unknown and requires reconciliation.",
                unknown_reason="action_timeout",
            )
        if "error" in outcome:
            if self._side_effect_may_be_uncertain(tool):
                return self.store.finish_action(
                    run_id,
                    tenant_id,
                    self.worker_id,
                    claim["lease_token"],
                    "unknown",
                    result={"error_code": "ACTION_OUTCOME_UNKNOWN"},
                    error={"error_code": "ACTION_OUTCOME_UNKNOWN"},
                    evidence_status="unknown",
                    provenance=provenance,
                    disclosure="The tool failed after dispatch and its side-effect status is unknown; reconciliation is required.",
                    unknown_reason="side_effect_uncertain",
                )
            return self.store.finish_action(
                run_id,
                tenant_id,
                self.worker_id,
                claim["lease_token"],
                "failed",
                result={"error_code": "TOOL_FAILED"},
                error={"error_code": "TOOL_FAILED"},
                evidence_status="unknown",
                provenance=provenance,
                disclosure="Tool execution failed; exception details are not exposed.",
            )
        return self.store.finish_action(
            run_id,
            tenant_id,
            self.worker_id,
            claim["lease_token"],
            "succeeded",
            result=outcome["result"],
            evidence_status=tool.evidence_status,
            provenance=provenance,
            disclosure=tool.disclosure,
        )
