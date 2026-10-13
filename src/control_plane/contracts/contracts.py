"""Typed request contracts for the governed control plane.

All contracts are versioned (v1.0.0) and use StrictModel
(extra="forbid") to reject incompatible payloads fail-closed.
"""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


RiskTier = Literal["R0", "R1", "R2", "R3", "R4", "R5"]
Mode = Literal[
    "observe",
    "assist",
    "do_this",
    "advanced",
    "engineering",
    "humanoid",
    "mobile_link",
]
SourceKind = Literal["text", "voice", "vision", "api", "sequence"]
GoalVerb = Literal["observe", "explain", "draft", "execute", "connect", "verify"]
SessionStatus = Literal["active", "revoked", "expired"]
PlanStatus = Literal["pending", "approved", "rejected", "executed", "cancelled"]
ApprovalDecision = Literal["approve", "reject"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VersionedModel(StrictModel):
    version: Literal["1.0.0"] = "1.0.0"


# ---------------------------------------------------------------------------
# Goal (v1.0.0)
# ---------------------------------------------------------------------------

class Goal(StrictModel):
    verb: GoalVerb
    object: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_.-]+$")
    parameters: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Intent (v1.0.0)
# ---------------------------------------------------------------------------

class IntentCreateRequest(StrictModel):
    source_kind: SourceKind
    source_text: str = Field(min_length=1, max_length=4096)
    goal: Goal
    requested_mode: Mode
    requested_risk_tier: RiskTier


# ---------------------------------------------------------------------------
# Session (v1.0.0)
# ---------------------------------------------------------------------------

class SessionCreateRequest(VersionedModel):
    api_key: str = Field(min_length=1, max_length=4096)


class SessionRenewRequest(VersionedModel):
    session_id: str = Field(min_length=1, max_length=256)
    new_expires_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


class SessionResponse(VersionedModel):
    session_id: str
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    tenant_id: str
    principal_id: str
    scopes: List[str]
    expires_at: str
    status: SessionStatus = "active"


# ---------------------------------------------------------------------------
# Plan (v1.0.0)
# ---------------------------------------------------------------------------

class PlanStep(VersionedModel):
    tool_id: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_.-]+$")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    risk_tier: RiskTier = "R0"


class PlanCreateRequest(VersionedModel):
    session_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=16_384)
    steps: List[PlanStep] = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Approval (v1.0.0)
# ---------------------------------------------------------------------------

class ApprovalSubmitRequest(VersionedModel):
    execution_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    decision: ApprovalDecision
    reason: str = Field(min_length=1, max_length=2000)


class ApprovalResponse(VersionedModel):
    approval_id: str
    execution_id: str
    decision: ApprovalDecision
    reason: str
    approver_id: str
    status: Literal["resolved"] = "resolved"
