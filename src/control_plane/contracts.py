"""Typed request contracts for the governed control plane."""

from typing import Any, Dict, Literal

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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Goal(StrictModel):
    verb: GoalVerb
    object: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_.-]+$")
    parameters: Dict[str, Any] = Field(default_factory=dict)


class IntentCreateRequest(StrictModel):
    source_kind: SourceKind
    source_text: str = Field(min_length=1, max_length=4096)
    goal: Goal
    requested_mode: Mode
    requested_risk_tier: RiskTier
