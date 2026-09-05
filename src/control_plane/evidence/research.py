"""Typed, research-only capability status projections.

Each entry reports an immutable state, disclosure, and evidence state.
None of these entries expose an executable mutation hook; they are
read-only status projections for the operator console and audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ResearchCapabilityStatus:
    name: str
    state: str
    evidence_state: str
    disclosure: str

    def to_jsonable(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "state": self.state,
            "evidence_state": self.evidence_state,
            "disclosure": self.disclosure,
        }


RESEARCH_CAPABILITIES: List[ResearchCapabilityStatus] = [
    ResearchCapabilityStatus(
        name="recursive_self_improvement",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "The RSI engine is a research extension. Candidates are generated only "
            "inside an isolated improvement plane and require operator authorization, "
            "signed artifacts, an immutable provenance record, and a tested rollback "
            "path before reaching any gatekeeper. No component in the reference "
            "control plane can modify or replace itself."
        ),
    ),
    ResearchCapabilityStatus(
        name="neural_symbolic_verification",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "Neural-symbolic verification is a future evidence-producing component. "
            "Counterexamples become structured evidence for the next proposal rather "
            "than hidden chain-of-thought. Retrieval evidence is never treated as "
            "proof by itself in the reference profile."
        ),
    ),
    ResearchCapabilityStatus(
        name="architecture_search",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "Architecture search is a research-only extension. The reference profile "
            "cannot search, evaluate, or deploy alternative architectures without an "
            "explicit operator gate and independent verification."
        ),
    ),
    ResearchCapabilityStatus(
        name="kernel_generation",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "Kernel generation is a research-only extension. The reference profile "
            "cannot generate, compile, or load new kernel code or accelerator "
            "binaries. Any generated artifact must be independently verified and "
            "signed before deployment."
        ),
    ),
    ResearchCapabilityStatus(
        name="self_deployment",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "Self-deployment is a research-only extension. The reference profile "
            "cannot modify or replace its own deployed code. Deployment requires "
            "explicit operator authorization and an independently signed artifact."
        ),
    ),
    ResearchCapabilityStatus(
        name="distributed_memory_topology",
        state="research_only",
        evidence_state="disabled",
        disclosure=(
            "Distributed memory topology is a research extension. The local "
            "reference profile maps all tiers to process memory, SQLite projections, "
            "and the filesystem so the same workload contracts can be tested without "
            "hyperscale hardware."
        ),
    ),
]


def list_research_capabilities() -> List[Dict[str, str]]:
    return [entry.to_jsonable() for entry in RESEARCH_CAPABILITIES]


__all__ = ["RESEARCH_CAPABILITIES", "ResearchCapabilityStatus", "list_research_capabilities"]
