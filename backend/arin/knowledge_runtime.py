"""Server-side ARIN runtime consumer for the bounded zknowbase read adapter.

This module is intentionally transport-neutral at the ARIN edge: callers provide
only authenticated session/tenant context and a query. The zknowbase service
credential remains encapsulated by the server-created ``ZKnowbaseReadClient``.
No write or physical-actuation authority is exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .knowledge import (
    KnowledgeContractError,
    KnowledgeEvidence,
    KnowledgeReadOutcome,
    KnowledgeRequirement,
    ZKnowbaseReadClient,
)


@dataclass(frozen=True)
class KnowledgeRuntimeContext:
    """Authenticated ARIN context propagated by the server runtime."""

    tenant_id: str
    session_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise KnowledgeContractError("runtime tenant context is required")
        if not self.session_id.strip():
            raise KnowledgeContractError("runtime session context is required")


@dataclass(frozen=True)
class KnowledgeRuntimeResult:
    """Runtime-safe knowledge result with verified provenance."""

    session_id: str
    tenant_id: str
    payload: dict[str, Any] | None
    evidence: tuple[KnowledgeEvidence, ...]
    degraded: bool = False
    reason: str | None = None


@dataclass
class KnowledgeRuntimeConsumer:
    """One bounded production runtime consumer of the accepted adapter.

    The client must be constructed by trusted server configuration. Tenant
    mismatch is rejected before network I/O, preventing a caller from selecting
    another tenant while reusing a server-held service credential.
    """

    client: ZKnowbaseReadClient

    def query(
        self,
        context: KnowledgeRuntimeContext,
        question: str,
        *,
        requirement: KnowledgeRequirement,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> KnowledgeRuntimeResult:
        if context.tenant_id != self.client.contract.tenant_id:
            raise KnowledgeContractError("runtime tenant does not match knowledge credential scope")

        outcome: KnowledgeReadOutcome = self.client.query_with_requirement(
            question,
            requirement=requirement,
            top_k=top_k,
            filters=filters,
        )
        if outcome.payload is None:
            return KnowledgeRuntimeResult(
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                payload=None,
                evidence=(),
                degraded=outcome.degraded,
                reason=outcome.reason,
            )

        evidence = self.client.evidence(outcome.payload)
        return KnowledgeRuntimeResult(
            session_id=context.session_id,
            tenant_id=context.tenant_id,
            payload=outcome.payload,
            evidence=evidence,
        )
