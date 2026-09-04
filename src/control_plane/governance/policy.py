"""Deterministic capability and risk policy evaluation."""

from dataclasses import dataclass
from typing import FrozenSet, Mapping, Tuple

from ..contracts import RiskTier


_RISK_ORDER = {f"R{index}": index for index in range(6)}


@dataclass(frozen=True)
class Capability:
    capability_id: str
    risk_tier: RiskTier
    required_scopes: FrozenSet[str]
    availability: str


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    risk_tier: RiskTier
    reasons: Tuple[str, ...]
    required_approvals: int
    policy_version: str = "policy.v1"


class PolicyEngine:
    """Allow only registered capabilities with sufficient scope and evidence."""

    def __init__(self, capabilities: Mapping[str, Capability] = None):
        self._capabilities = dict(
            capabilities
            or {
                "registry.system.status": Capability(
                    capability_id="registry.system.status",
                    risk_tier="R0",
                    required_scopes=frozenset({"workspace:read"}),
                    availability="enabled",
                ),
            }
        )

    def evaluate(
        self,
        capability_id: str,
        requested_risk_tier: RiskTier,
        principal_scopes: FrozenSet[str],
        approved: bool = False,
    ) -> PolicyDecision:
        capability = self._capabilities.get(capability_id)
        if capability is None:
            return PolicyDecision(
                decision="deny",
                risk_tier=requested_risk_tier,
                reasons=("capability.unavailable",),
                required_approvals=0,
            )
        if capability.availability != "enabled":
            return PolicyDecision(
                decision="deny",
                risk_tier=requested_risk_tier,
                reasons=("capability.disabled",),
                required_approvals=0,
            )
        if _RISK_ORDER[requested_risk_tier] > _RISK_ORDER[capability.risk_tier]:
            return PolicyDecision(
                decision="deny",
                risk_tier=requested_risk_tier,
                reasons=("risk.exceeds_capability",),
                required_approvals=0,
            )
        if _RISK_ORDER[requested_risk_tier] < _RISK_ORDER[capability.risk_tier]:
            return PolicyDecision(
                decision="deny",
                risk_tier=requested_risk_tier,
                reasons=("risk.underdeclared",),
                required_approvals=0,
            )
        missing = sorted(capability.required_scopes - set(principal_scopes))
        if missing:
            return PolicyDecision(
                decision="deny",
                risk_tier=requested_risk_tier,
                reasons=tuple(["scope.missing"] + [f"scope.{item}" for item in missing]),
                required_approvals=0,
            )
        required_approvals = 0 if _RISK_ORDER[requested_risk_tier] <= 1 else 1
        if required_approvals and not approved:
            return PolicyDecision(
                decision="allow_with_approval",
                risk_tier=requested_risk_tier,
                reasons=("scope.valid", "approval.required"),
                required_approvals=required_approvals,
            )
        return PolicyDecision(
            decision="allow",
            risk_tier=requested_risk_tier,
            reasons=("scope.valid", "capability.enabled"),
            required_approvals=required_approvals,
        )
