import pytest

from backend.app.arin.knowledge import KnowledgeContractError, ZKnowbaseReadContract


def contract(**overrides):
    values = {
        "base_url": "http://zknowbase.local/",
        "api_key": "scoped-read-key",
        "tenant_id": "tenant-a",
        "timeout_seconds": 5,
    }
    values.update(overrides)
    return ZKnowbaseReadContract(**values)


def test_search_contract_is_read_only_and_tenant_scoped():
    adapter = contract()
    url, headers, body = adapter.search_request("  safety manual  ", top_k=3)

    assert url == "http://zknowbase.local/api/v1/search"
    assert headers["X-API-Key"] == "scoped-read-key"
    assert headers["X-ZWorkforce-Tenant-ID"] == "tenant-a"
    assert body == {"query": "safety manual", "top_k": 3}
    assert "ingest" not in url


def test_query_contract_forces_non_streaming_bounded_request():
    adapter = contract()
    url, _, body = adapter.query_request("what is the safe state?", top_k=5)

    assert url.endswith("/api/v1/query")
    assert body["stream"] is False
    assert body["top_k"] == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "file:///tmp/zknowbase"},
        {"api_key": "   "},
        {"tenant_id": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": 31},
    ],
)
def test_unsafe_configuration_fails_before_request(overrides):
    with pytest.raises(KnowledgeContractError):
        contract(**overrides)


def test_empty_query_and_unbounded_top_k_are_rejected():
    adapter = contract()
    with pytest.raises(KnowledgeContractError):
        adapter.search_request(" ")
    with pytest.raises(KnowledgeContractError):
        adapter.search_request("ok", top_k=101)
