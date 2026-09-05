"""Strict API request/response contracts for the agent platform."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BudgetRequest(StrictModel):
    max_steps: int = Field(default=4, ge=1, le=64)
    max_tool_calls: int = Field(default=4, ge=1, le=64)
    max_runtime_seconds: int = Field(default=30, ge=1, le=600)


class AgentCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=4096)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    system_prompt: str = Field(default="", max_length=16_384)
    allowed_tools: List[str] = Field(
        default_factory=lambda: ["knowledge.search", "ticket.update"],
        max_length=16,
    )
    model_policy: Dict[str, Any] = Field(default_factory=dict)
    budget: BudgetRequest = Field(default_factory=BudgetRequest)


class AgentVersionCreateRequest(StrictModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    system_prompt: str = Field(default="", max_length=16_384)
    allowed_tools: List[str] = Field(min_length=1, max_length=16)
    model_policy: Dict[str, Any] = Field(default_factory=dict)
    budget: BudgetRequest = Field(default_factory=BudgetRequest)


class AgentSandboxRequest(StrictModel):
    task: str = Field(min_length=1, max_length=4096)
    ticket_id: str = Field(default="DEMO-1", min_length=1, max_length=128)
    ticket_fields: Dict[str, Any] = Field(default_factory=dict)


class AgentExecutionRequest(AgentSandboxRequest):
    pass


class AgentApprovalDecisionRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)


__all__ = [
    "AgentApprovalDecisionRequest",
    "AgentCreateRequest",
    "AgentExecutionRequest",
    "AgentSandboxRequest",
    "AgentVersionCreateRequest",
    "BudgetRequest",
    "StrictModel",
]
