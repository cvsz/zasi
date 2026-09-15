"""Fail-closed authorization gate for future ARIN -> zknowbase writes.

This module does not perform ingestion or any network request. It exists so a
future write transport cannot be constructed unless the caller proves both an
explicit ``knowledge:write`` grant and an affirmative ARIN policy decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .knowledge import KnowledgeContractError


@dataclass(frozen=True)
class ZKnowbaseWriteAuthorization:
    """Explicit scope + policy evidence required before any knowledge mutation."""

    api_key: str = field(repr=False)
    tenant_id: str
    granted_scopes: frozenset[str]
    policy_allowed: bool
    approval_id: str

    @classmethod
    def authorize(
        cls,
        *,
        api_key: str,
        tenant_id: str,
        granted_scopes: Iterable[str],
        policy_allowed: bool,
        approval_id: str,
    ) -> "ZKnowbaseWriteAuthorization":
        key = api_key.strip()
        tenant = tenant_id.strip()
        approval = approval_id.strip()
        scopes = frozenset(scope.strip() for scope in granted_scopes if scope.strip())
        if not key:
            raise KnowledgeContractError("zknowbase knowledge:write service key is required")
        if not tenant:
            raise KnowledgeContractError("zknowbase write tenant context is required")
        if "knowledge:write" not in scopes:
            raise KnowledgeContractError("zknowbase write requires explicit knowledge:write scope")
        if not policy_allowed:
            raise KnowledgeContractError("ARIN policy denied zknowbase write")
        if not approval:
            raise KnowledgeContractError("ARIN approval evidence is required for zknowbase write")
        return cls(
            api_key=key,
            tenant_id=tenant,
            granted_scopes=scopes,
            policy_allowed=True,
            approval_id=approval,
        )

    @property
    def headers(self) -> dict[str, str]:
        """Server-side headers for a later bounded write transport."""
        return {
            "X-API-Key": self.api_key,
            "X-ZWorkforce-Tenant-ID": self.tenant_id,
        }
