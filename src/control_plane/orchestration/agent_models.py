"""Immutable domain values for the agent platform.

The values defined here are produced by the deterministic planner and the
model gateway, and are later canonicalized for digesting. They are deliberately
not Pydantic models because the agent runtime is a service that operates
between the HTTP contracts and the durable repository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Tuple


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class BudgetPolicy:
    max_steps: int = 4
    max_tool_calls: int = 4
    max_runtime_seconds: int = 30

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "max_steps": int(self.max_steps),
            "max_tool_calls": int(self.max_tool_calls),
            "max_runtime_seconds": int(self.max_runtime_seconds),
        }

    def digest(self) -> str:
        return _canonical_json(self.to_jsonable())

    @classmethod
    def from_jsonable(cls, value: Any) -> "BudgetPolicy":
        if not isinstance(value, dict):
            raise ValueError("budget must be an object")
        unknown = set(value.keys()) - {"max_steps", "max_tool_calls", "max_runtime_seconds"}
        if unknown:
            raise ValueError(f"unknown budget keys: {sorted(unknown)}")
        defaults = cls()
        max_steps = int(value.get("max_steps", defaults.max_steps))
        max_tool_calls = int(value.get("max_tool_calls", defaults.max_tool_calls))
        max_runtime_seconds = int(value.get("max_runtime_seconds", defaults.max_runtime_seconds))
        if max_steps < 1 or max_steps > 64:
            raise ValueError("max_steps must be between 1 and 64")
        if max_tool_calls < 1 or max_tool_calls > 64:
            raise ValueError("max_tool_calls must be between 1 and 64")
        if max_runtime_seconds < 1 or max_runtime_seconds > 600:
            raise ValueError("max_runtime_seconds must be between 1 and 600")
        return cls(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_runtime_seconds=max_runtime_seconds,
        )


@dataclass(frozen=True)
class AgentVersionSpec:
    version: str
    system_prompt: str
    allowed_tools: Tuple[str, ...]
    model_policy: Dict[str, Any] = field(default_factory=dict)
    budget: BudgetPolicy = field(default_factory=BudgetPolicy)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "system_prompt": self.system_prompt,
            "allowed_tools": list(self.allowed_tools),
            "model_policy": dict(self.model_policy),
            "budget": self.budget.to_jsonable(),
        }

    def digest(self) -> str:
        return _canonical_json(self.to_jsonable())

    @classmethod
    def from_jsonable(cls, value: Any) -> "AgentVersionSpec":
        if not isinstance(value, dict):
            raise ValueError("version spec must be an object")
        version = value.get("version")
        if not isinstance(version, str):
            raise ValueError("version must be a string")
        system_prompt = value.get("system_prompt", "")
        if not isinstance(system_prompt, str):
            raise ValueError("system_prompt must be a string")
        allowed_tools = value.get("allowed_tools", [])
        if not isinstance(allowed_tools, list) or not all(
            isinstance(t, str) and t for t in allowed_tools
        ):
            raise ValueError("allowed_tools must be a list of non-empty strings")
        model_policy = value.get("model_policy", {})
        if not isinstance(model_policy, dict):
            raise ValueError("model_policy must be an object")
        budget = BudgetPolicy.from_jsonable(value.get("budget", {}))
        return cls(
            version=version,
            system_prompt=system_prompt,
            allowed_tools=tuple(allowed_tools),
            model_policy=dict(model_policy),
            budget=budget,
        )


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool_id: str
    tool_version: str
    risk_tier: str
    input: Dict[str, Any]
    preconditions: Tuple[str, ...] = ()
    expected_effects: Tuple[str, ...] = ()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "risk_tier": self.risk_tier,
            "input": dict(self.input),
            "preconditions": list(self.preconditions),
            "expected_effects": list(self.expected_effects),
        }

    def digest(self) -> str:
        return _canonical_json(self.to_jsonable())


@dataclass(frozen=True)
class TypedAgentPlan:
    steps: Tuple[PlanStep, ...]
    disclosures: Tuple[str, ...] = ()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "steps": [step.to_jsonable() for step in self.steps],
            "disclosures": list(self.disclosures),
        }

    def digest(self) -> str:
        return _canonical_json(self.to_jsonable())


@dataclass(frozen=True)
class ModelSelection:
    mode: str
    model: str
    status: str
    proposal_digest: str
    disclosures: Tuple[str, ...] = ()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "model": self.model,
            "status": self.status,
            "proposal_digest": self.proposal_digest,
            "disclosures": list(self.disclosures),
        }


@dataclass(frozen=True)
class AgentEventContext:
    execution_id: str
    agent_version: str
    correlation_id: str
    causation_id: str = ""
    sensitivity: str = "tenant"
    idempotency_key: str = ""
    schema_version: int = 2

    def to_envelope(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "agent_version": self.agent_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "sensitivity": self.sensitivity,
            "idempotency_key": self.idempotency_key,
            "schema_version": int(self.schema_version),
        }


def canonicalize_action_payload(payload: Any) -> Any:
    """Recursively canonicalize an action payload before computing digests.

    The runtime must produce the same action digest for semantically identical
    payloads, regardless of key ordering or trivial whitespace differences.
    """

    if isinstance(payload, dict):
        return {str(key): canonicalize_action_payload(value) for key, value in sorted(payload.items())}
    if isinstance(payload, list):
        return [canonicalize_action_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(canonicalize_action_payload(item) for item in payload)
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    raise ValueError(f"unsupported action payload type: {type(payload).__name__}")


def action_digest(
    *,
    tenant_id: str,
    execution_id: str,
    agent_version: str,
    tool_id: str,
    tool_version: str,
    payload: Any,
) -> str:
    """Compute the exact action digest bound to tenant, execution, and tool.

    The digest is used as the binding key for pending approvals. Replays or
    mutated requests must not match.
    """

    canonical = canonicalize_action_payload(
        {
            "tenant_id": tenant_id,
            "execution_id": execution_id,
            "agent_version": agent_version,
            "tool_id": tool_id,
            "tool_version": tool_version,
            "payload": payload,
        }
    )
    return _canonical_json(canonical)


__all__ = [
    "AgentEventContext",
    "AgentVersionSpec",
    "BudgetPolicy",
    "ModelSelection",
    "PlanStep",
    "TypedAgentPlan",
    "action_digest",
    "canonicalize_action_payload",
]


def required_scopes_for(tool_id: str) -> FrozenSet[str]:
    """Return the principal scopes required to invoke a known agent tool."""
    scopes = {
        "knowledge.search": frozenset({"workspace:read"}),
        "ticket.update": frozenset({"workspace:write", "plan:create"}),
    }
    return scopes.get(tool_id, frozenset())
