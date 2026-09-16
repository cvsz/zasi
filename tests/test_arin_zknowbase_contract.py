import unittest

import httpx

from backend.arin.knowledge import (
    KnowledgeContractError,
    KnowledgeRequirement,
    KnowledgeTransportError,
    ZKnowbaseReadClient,
    ZKnowbaseReadContract,
)


def contract(**overrides):
    values = {"base_url": "http://zknowbase.local/", "api_key": "scoped-read-key", "tenant_id": "tenant-a", "timeout_seconds": 5}
    values.update(overrides)
    return ZKnowbaseReadContract(**values)


def citation(**overrides):
    value = {
        "document_id": "doc-1", "document_name": "Safety Manual", "tenant_id": "tenant-a",
        "chunk_id": "chunk-7", "chunk_index": 7, "score": 0.91,
        "text": "Enter the safe state.", "source_uri": "manuals/safety.md",
    }
    value.update(overrides)
    return value


class ZKnowbaseReadContractTests(unittest.TestCase):
    def test_search_contract_is_read_only_and_tenant_scoped(self):
        adapter = contract()
        url, headers, body = adapter.search_request("  safety manual  ", top_k=3)
        self.assertEqual(url, "http://zknowbase.local/api/v1/search")
        self.assertEqual(headers["X-API-Key"], "scoped-read-key")
        self.assertEqual(headers["X-ZWorkforce-Tenant-ID"], "tenant-a")
        self.assertEqual(body, {"query": "safety manual", "top_k": 3})
        self.assertNotIn("ingest", url)

    def test_query_contract_forces_non_streaming_bounded_request(self):
        adapter = contract()
        url, _, body = adapter.query_request("what is the safe state?", top_k=5)
        self.assertTrue(url.endswith("/api/v1/query"))
        self.assertIs(body["stream"], False)
        self.assertEqual(body["top_k"], 5)

    def test_unsafe_configuration_fails_before_request(self):
        unsafe_overrides = [{"base_url": "file:///tmp/zknowbase"}, {"base_url": "https://?x=1"}, {"base_url": "http://#fragment"}, {"base_url": "https://user:pass@zknowbase.local"}, {"base_url": "http://:8080"}, {"base_url": "http://zknowbase.local:not-a-port"}, {"api_key": "   "}, {"tenant_id": ""}, {"timeout_seconds": 0}, {"timeout_seconds": 31}]
        for overrides in unsafe_overrides:
            with self.subTest(overrides=overrides):
                with self.assertRaises(KnowledgeContractError):
                    contract(**overrides)

    def test_api_key_is_redacted_from_contract_representation(self):
        self.assertNotIn("do-not-log-this", repr(contract(api_key="do-not-log-this")))

    def test_empty_query_and_unbounded_top_k_are_rejected(self):
        adapter = contract()
        with self.assertRaises(KnowledgeContractError):
            adapter.search_request(" ")
        with self.assertRaises(KnowledgeContractError):
            adapter.search_request("ok", top_k=101)

    def test_read_transport_preserves_tenant_scope(self):
        def handler(request):
            self.assertEqual(request.headers["X-API-Key"], "scoped-read-key")
            self.assertEqual(request.headers["X-ZWorkforce-Tenant-ID"], "tenant-a")
            self.assertEqual(request.url.path, "/api/v1/search")
            return httpx.Response(200, json={"results": []})
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(handler))
        self.assertEqual(client.search("manual"), {"results": []})

    def test_read_transport_fails_closed_on_auth_and_malformed_response(self):
        for response in [httpx.Response(403, json={"detail": "denied"}), httpx.Response(200, text="not-json"), httpx.Response(200, json=[]), httpx.Response(503, json={})]:
            with self.subTest(status=response.status_code, body=response.text):
                client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(lambda request, r=response: r))
                with self.assertRaises(KnowledgeTransportError):
                    client.search("manual")

    def test_read_transport_fails_closed_on_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out", request=request)
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(handler))
        with self.assertRaises(KnowledgeTransportError):
            client.query("safe state")

    def test_required_knowledge_fails_closed_when_unavailable(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out", request=request)
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(KnowledgeTransportError, "read unavailable"):
            client.query_with_requirement("safe state", requirement=KnowledgeRequirement.REQUIRED)

    def test_optional_knowledge_degrades_only_on_unavailability(self):
        def handler(request):
            raise httpx.ConnectError("offline", request=request)
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(handler))
        outcome = client.search_with_requirement("manual", requirement=KnowledgeRequirement.OPTIONAL)
        self.assertTrue(outcome.degraded)
        self.assertIsNone(outcome.payload)
        self.assertEqual(outcome.reason, "zknowbase unavailable")

    def test_optional_knowledge_degrades_on_proxy_unavailability(self):
        def handler(request):
            raise httpx.ProxyError("proxy offline", request=request)
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(handler))
        outcome = client.search_with_requirement("manual", requirement=KnowledgeRequirement.OPTIONAL)
        self.assertTrue(outcome.degraded)
        self.assertIsNone(outcome.payload)

    def test_policy_aware_reads_validate_provenance_before_success(self):
        invalid_payloads = [
            {},
            {"results": [citation(tenant_id="tenant-b")]},
            {"sources": [{key: value for key, value in citation().items() if key != "document_id"}]},
        ]
        for payload in invalid_payloads:
            for requirement in (KnowledgeRequirement.REQUIRED, KnowledgeRequirement.OPTIONAL):
                with self.subTest(payload=payload, requirement=requirement):
                    client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(lambda request, p=payload: httpx.Response(200, json=p)))
                    with self.assertRaises(KnowledgeTransportError):
                        client.search_with_requirement("manual", requirement=requirement)

    def test_optional_knowledge_never_masks_security_or_integrity_failures(self):
        responses = [
            httpx.Response(403, json={"detail": "denied"}),
            httpx.Response(200, text="not-json"),
            httpx.Response(503, json={}),
        ]
        for response in responses:
            with self.subTest(status=response.status_code):
                client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(lambda request, r=response: r))
                with self.assertRaises(KnowledgeTransportError):
                    client.search_with_requirement("manual", requirement=KnowledgeRequirement.OPTIONAL)

    def test_knowledge_requirement_must_be_explicit_enum(self):
        client = ZKnowbaseReadClient(contract(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []})))
        with self.assertRaises(KnowledgeContractError):
            client.search_with_requirement("manual", requirement="optional")  # type: ignore[arg-type]

    def test_maps_search_and_query_citations_to_tenant_bound_evidence(self):
        client = ZKnowbaseReadClient(contract())
        source = citation()
        for payload in ({"results": [source]}, {"answer": "Stop [S1].", "sources": [source]}):
            with self.subTest(payload=payload):
                evidence = client.evidence(payload)
                self.assertEqual(len(evidence), 1)
                self.assertEqual(evidence[0].document_id, "doc-1")
                self.assertEqual(evidence[0].tenant_id, "tenant-a")
                self.assertEqual(evidence[0].chunk_id, "chunk-7")
                self.assertEqual(evidence[0].source_uri, "manuals/safety.md")

    def test_evidence_mapping_fails_closed_on_missing_or_cross_tenant_provenance(self):
        client = ZKnowbaseReadClient(contract())
        valid = citation(source_uri=None)
        invalid_payloads = [
            {},
            {"results": [{**valid, "tenant_id": "tenant-b"}]},
            {"sources": [{key: value for key, value in valid.items() if key != "document_id"}]},
            {"results": [{**valid, "chunk_index": "7"}]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(KnowledgeTransportError):
                    client.evidence(payload)


if __name__ == "__main__":
    unittest.main()
