"""Bounded read-only ARIN -> zknowbase contract.

The adapter deliberately exposes only search/query request construction. It
never owns zknowbase credentials, tenant selection, ingestion, or provider
state. Callers must provide a tenant-scoped ``knowledge:read`` service key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


class KnowledgeContractError(ValueError):
    """Raised before any request when the knowledge contract is unsafe."""


@dataclass(frozen=True)
class ZKnowbaseReadContract:
    base_url: str
    api_key: str = field(repr=False)
    tenant_id: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        raw_base = self.base_url.strip().rstrip("/")
        parsed = urlsplit(raw_base)
        key = self.api_key.strip()
        tenant = self.tenant_id.strip()
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise KnowledgeContractError("zknowbase base_url must be an absolute http(s) URL")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise KnowledgeContractError(
                "zknowbase base_url must not contain credentials, query, or fragment"
            )
        base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        if not key:
            raise KnowledgeContractError("zknowbase knowledge:read service key is required")
        if not tenant:
            raise KnowledgeContractError("zknowbase tenant context is required")
        if not 0 < self.timeout_seconds <= 30:
            raise KnowledgeContractError("zknowbase timeout must be within (0, 30] seconds")
        object.__setattr__(self, "base_url", base)
        object.__setattr__(self, "api_key", key)
        object.__setattr__(self, "tenant_id", tenant)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "X-ZWorkforce-Tenant-ID": self.tenant_id,
            "Content-Type": "application/json",
        }

    def search_request(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        return self._request("search", "query", query, top_k, filters)

    def query_request(
        self,
        question: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url, headers, body = self._request("query", "question", question, top_k, filters)
        body["stream"] = False
        return url, headers, body

    def _request(
        self,
        endpoint: str,
        text_field: str,
        text: str,
        top_k: int,
        filters: Mapping[str, Any] | None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        value = text.strip()
        if not value:
            raise KnowledgeContractError(f"zknowbase {text_field} is required")
        if not 1 <= top_k <= 100:
            raise KnowledgeContractError("zknowbase top_k must be within [1, 100]")
        body: dict[str, Any] = {text_field: value, "top_k": top_k}
        if filters:
            body["filters"] = dict(filters)
        return f"{self.base_url}/api/v1/{endpoint}", self.headers, body
