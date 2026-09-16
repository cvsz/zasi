"""Bounded read-only ARIN -> zknowbase contract, transport, and evidence mapping.

The adapter deliberately exposes only search/query reads. It never owns
zknowbase credentials, tenant selection, ingestion, or provider state. Callers
must provide a tenant-scoped ``knowledge:read`` service key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx


class KnowledgeContractError(ValueError):
    """Raised before any request when the knowledge contract is unsafe."""


class KnowledgeTransportError(RuntimeError):
    """Raised when zknowbase cannot provide a valid bounded read response."""


class KnowledgeRequirement(str, Enum):
    """Whether an ARIN operation may safely continue without knowledge."""

    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class KnowledgeEvidence:
    """Tenant-bound provenance copied from a verified zknowbase citation."""

    document_id: str
    document_name: str
    tenant_id: str
    chunk_id: str
    chunk_index: int
    score: float
    text: str
    source_uri: str | None = None


@dataclass(frozen=True)
class KnowledgeReadOutcome:
    """Explicit result for policy-aware knowledge reads.

    Optional reads may degrade to ``payload=None`` only for transport/service
    unavailability. Authorization, tenant, malformed-response, and provenance
    failures remain hard failures because degrading them could hide a security
    or integrity boundary violation.
    """

    payload: dict[str, Any] | None
    degraded: bool = False
    reason: str | None = None


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
        try:
            hostname = parsed.hostname
            parsed.port
        except ValueError as exc:
            raise KnowledgeContractError("zknowbase base_url has an invalid authority") from exc
        if not hostname:
            raise KnowledgeContractError("zknowbase base_url must include a hostname")
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

    def search_request(self, query: str, *, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> tuple[str, dict[str, str], dict[str, Any]]:
        return self._request("search", "query", query, top_k, filters)

    def query_request(self, question: str, *, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> tuple[str, dict[str, str], dict[str, Any]]:
        url, headers, body = self._request("query", "question", question, top_k, filters)
        body["stream"] = False
        return url, headers, body

    def _request(self, endpoint: str, text_field: str, text: str, top_k: int, filters: Mapping[str, Any] | None) -> tuple[str, dict[str, str], dict[str, Any]]:
        value = text.strip()
        if not value:
            raise KnowledgeContractError(f"zknowbase {text_field} is required")
        if not 1 <= top_k <= 100:
            raise KnowledgeContractError("zknowbase top_k must be within [1, 100]")
        body: dict[str, Any] = {text_field: value, "top_k": top_k}
        if filters:
            body["filters"] = dict(filters)
        return f"{self.base_url}/api/v1/{endpoint}", self.headers, body


@dataclass
class ZKnowbaseReadClient:
    """Read-only HTTP transport with bounded timeout and fail-closed errors."""

    contract: ZKnowbaseReadContract
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def search(self, query: str, *, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._send(self.contract.search_request(query, top_k=top_k, filters=filters))

    def query(self, question: str, *, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._send(self.contract.query_request(question, top_k=top_k, filters=filters))

    def search_with_requirement(self, query: str, *, requirement: KnowledgeRequirement, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> KnowledgeReadOutcome:
        return self._read_with_requirement(
            self.contract.search_request(query, top_k=top_k, filters=filters), requirement
        )

    def query_with_requirement(self, question: str, *, requirement: KnowledgeRequirement, top_k: int = 5, filters: Mapping[str, Any] | None = None) -> KnowledgeReadOutcome:
        return self._read_with_requirement(
            self.contract.query_request(question, top_k=top_k, filters=filters), requirement
        )

    def evidence(self, payload: Mapping[str, Any]) -> tuple[KnowledgeEvidence, ...]:
        """Map search/query citations into tenant-bound ZASI evidence.

        Evidence is accepted only when every citation has the zknowbase source
        contract and belongs to the authenticated tenant. Partial or malformed
        provenance fails closed rather than silently dropping fields.
        """
        raw_sources = payload.get("sources", payload.get("results"))
        if not isinstance(raw_sources, list):
            raise KnowledgeTransportError("zknowbase response is missing citation provenance")
        evidence: list[KnowledgeEvidence] = []
        for source in raw_sources:
            if not isinstance(source, dict):
                raise KnowledgeTransportError("zknowbase citation must be a JSON object")
            required = ("document_id", "document_name", "tenant_id", "chunk_id", "chunk_index", "score", "text")
            if any(key not in source for key in required):
                raise KnowledgeTransportError("zknowbase citation provenance is incomplete")
            if source["tenant_id"] != self.contract.tenant_id:
                raise KnowledgeTransportError("zknowbase citation tenant mismatch")
            if not isinstance(source["chunk_index"], int) or isinstance(source["chunk_index"], bool):
                raise KnowledgeTransportError("zknowbase citation chunk_index is invalid")
            if not isinstance(source["score"], (int, float)) or isinstance(source["score"], bool):
                raise KnowledgeTransportError("zknowbase citation score is invalid")
            text_fields = ("document_id", "document_name", "tenant_id", "chunk_id", "text")
            if any(not isinstance(source[key], str) or not source[key].strip() for key in text_fields):
                raise KnowledgeTransportError("zknowbase citation text provenance is invalid")
            source_uri = source.get("source_uri")
            if source_uri is not None and not isinstance(source_uri, str):
                raise KnowledgeTransportError("zknowbase citation source_uri is invalid")
            evidence.append(KnowledgeEvidence(
                document_id=source["document_id"], document_name=source["document_name"],
                tenant_id=source["tenant_id"], chunk_id=source["chunk_id"],
                chunk_index=source["chunk_index"], score=float(source["score"]),
                text=source["text"], source_uri=source_uri,
            ))
        return tuple(evidence)

    def _read_with_requirement(self, request: tuple[str, dict[str, str], dict[str, Any]], requirement: KnowledgeRequirement) -> KnowledgeReadOutcome:
        if not isinstance(requirement, KnowledgeRequirement):
            raise KnowledgeContractError("knowledge requirement must be explicit")
        try:
            payload = self._send(request)
            self.evidence(payload)
            return KnowledgeReadOutcome(payload=payload)
        except KnowledgeTransportError as exc:
            if requirement is KnowledgeRequirement.OPTIONAL and str(exc) == "zknowbase read unavailable":
                return KnowledgeReadOutcome(payload=None, degraded=True, reason="zknowbase unavailable")
            raise

    def _send(self, request: tuple[str, dict[str, str], dict[str, Any]]) -> dict[str, Any]:
        url, headers, body = request
        try:
            with httpx.Client(timeout=self.contract.timeout_seconds, transport=self.transport) as client:
                response = client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProxyError) as exc:
            raise KnowledgeTransportError("zknowbase read unavailable") from exc
        if response.status_code in {401, 403}:
            raise KnowledgeTransportError("zknowbase read authorization failed")
        if not response.is_success:
            raise KnowledgeTransportError(f"zknowbase read failed with status {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise KnowledgeTransportError("zknowbase returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise KnowledgeTransportError("zknowbase response must be a JSON object")
        return payload
