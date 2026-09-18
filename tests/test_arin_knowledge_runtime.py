import httpx
import pytest

from backend.arin.knowledge import (
    KnowledgeContractError,
    KnowledgeRequirement,
    KnowledgeTransportError,
    ZKnowbaseReadClient,
    ZKnowbaseReadContract,
)
from backend.arin.knowledge_runtime import KnowledgeRuntimeConsumer, KnowledgeRuntimeContext


def _client(handler, *, tenant="tenant-a"):
    return ZKnowbaseReadClient(
        ZKnowbaseReadContract(
            base_url="https://knowledge.internal",
            api_key="server-only-key",
            tenant_id=tenant,
        ),
        transport=httpx.MockTransport(handler),
    )


def _ok_payload(tenant="tenant-a"):
    return {
        "answer": "grounded",
        "sources": [{
            "document_id": "doc-1",
            "document_name": "manual.md",
            "tenant_id": tenant,
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "score": 0.99,
            "text": "verified source",
        }],
    }


def test_runtime_propagates_server_scoped_tenant_and_preserves_session_and_provenance():
    seen = {}

    def handler(request):
        seen["tenant"] = request.headers["X-ZWorkforce-Tenant-ID"]
        seen["key"] = request.headers["X-API-Key"]
        return httpx.Response(200, json=_ok_payload(), request=request)

    consumer = KnowledgeRuntimeConsumer(_client(handler))
    result = consumer.query(
        KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="session-1"),
        "What is the safe procedure?",
        requirement=KnowledgeRequirement.REQUIRED,
    )

    assert result.tenant_id == "tenant-a"
    assert result.session_id == "session-1"
    assert result.degraded is False
    assert result.evidence[0].document_id == "doc-1"
    assert result.evidence[0].tenant_id == "tenant-a"
    assert seen == {"tenant": "tenant-a", "key": "server-only-key"}
    assert "server-only-key" not in repr(consumer.client.contract)
    assert "server-only-key" not in repr(result)


def test_runtime_rejects_cross_tenant_context_before_network_io():
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json=_ok_payload(), request=request)

    consumer = KnowledgeRuntimeConsumer(_client(handler, tenant="tenant-a"))
    with pytest.raises(KnowledgeContractError, match="tenant does not match"):
        consumer.query(
            KnowledgeRuntimeContext(tenant_id="tenant-b", session_id="session-2"),
            "query",
            requirement=KnowledgeRequirement.REQUIRED,
        )
    assert called is False


def test_required_runtime_knowledge_fails_closed_when_service_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    consumer = KnowledgeRuntimeConsumer(_client(handler))
    with pytest.raises(KnowledgeTransportError, match="read unavailable"):
        consumer.query(
            KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="session-3"),
            "query",
            requirement=KnowledgeRequirement.REQUIRED,
        )


def test_optional_runtime_knowledge_degrades_only_for_normalized_unavailability():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    consumer = KnowledgeRuntimeConsumer(_client(handler))
    result = consumer.query(
        KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="session-4"),
        "query",
        requirement=KnowledgeRequirement.OPTIONAL,
    )
    assert result.payload is None
    assert result.evidence == ()
    assert result.degraded is True
    assert result.reason == "zknowbase unavailable"


def test_optional_runtime_knowledge_does_not_hide_cross_tenant_provenance():
    def handler(request):
        return httpx.Response(200, json=_ok_payload("tenant-b"), request=request)

    consumer = KnowledgeRuntimeConsumer(_client(handler))
    with pytest.raises(KnowledgeTransportError, match="citation tenant mismatch"):
        consumer.query(
            KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="session-5"),
            "query",
            requirement=KnowledgeRequirement.OPTIONAL,
        )


def test_runtime_context_requires_authenticated_tenant_and_session():
    with pytest.raises(KnowledgeContractError, match="tenant context"):
        KnowledgeRuntimeContext(tenant_id=" ", session_id="session")
    with pytest.raises(KnowledgeContractError, match="session context"):
        KnowledgeRuntimeContext(tenant_id="tenant-a", session_id=" ")


def test_runtime_consumer_is_compatible_with_existing_read_contract():
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path, request.headers["X-ZWorkforce-Tenant-ID"]))
        return httpx.Response(200, json=_ok_payload(), request=request)

    direct_client = _client(handler)
    direct_payload = direct_client.query("compatibility query")
    runtime_result = KnowledgeRuntimeConsumer(_client(handler)).query(
        KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="compat-session"),
        "compatibility query",
        requirement=KnowledgeRequirement.REQUIRED,
    )

    assert direct_payload == runtime_result.payload
    assert runtime_result.evidence == direct_client.evidence(direct_payload)
    assert requests[0] == requests[1]


def test_runtime_consumer_rollback_requires_no_data_or_transport_migration():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_ok_payload(), request=request)

    client = _client(handler)
    consumer = KnowledgeRuntimeConsumer(client)
    runtime_result = consumer.query(
        KnowledgeRuntimeContext(tenant_id="tenant-a", session_id="rollback-session"),
        "rollback query",
        requirement=KnowledgeRequirement.REQUIRED,
    )

    # Rollback is removal of the additive runtime wrapper: the pre-existing read
    # contract remains usable with the same server-held credential, tenant scope,
    # endpoint and response schema. No data/schema/write migration is involved.
    direct_payload = client.query("rollback query")

    assert direct_payload == runtime_result.payload
    assert client.evidence(direct_payload) == runtime_result.evidence
    assert len(requests) == 2
    assert all(request.method == "POST" for request in requests)
    assert all(request.url.path == "/api/v1/rag/query" for request in requests)
    assert all(request.headers["X-ZWorkforce-Tenant-ID"] == "tenant-a" for request in requests)
