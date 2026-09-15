import unittest

from backend.arin.knowledge import KnowledgeContractError, ZKnowbaseReadContract


def contract(**overrides):
    values = {
        "base_url": "http://zknowbase.local/",
        "api_key": "scoped-read-key",
        "tenant_id": "tenant-a",
        "timeout_seconds": 5,
    }
    values.update(overrides)
    return ZKnowbaseReadContract(**values)


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
        unsafe_overrides = [
            {"base_url": "file:///tmp/zknowbase"},
            {"base_url": "https://?x=1"},
            {"base_url": "http://#fragment"},
            {"base_url": "https://user:pass@zknowbase.local"},
            {"base_url": "http://:8080"},
            {"base_url": "http://zknowbase.local:not-a-port"},
            {"api_key": "   "},
            {"tenant_id": ""},
            {"timeout_seconds": 0},
            {"timeout_seconds": 31},
        ]
        for overrides in unsafe_overrides:
            with self.subTest(overrides=overrides):
                with self.assertRaises(KnowledgeContractError):
                    contract(**overrides)

    def test_api_key_is_redacted_from_contract_representation(self):
        adapter = contract(api_key="do-not-log-this")
        self.assertNotIn("do-not-log-this", repr(adapter))

    def test_empty_query_and_unbounded_top_k_are_rejected(self):
        adapter = contract()
        with self.assertRaises(KnowledgeContractError):
            adapter.search_request(" ")
        with self.assertRaises(KnowledgeContractError):
            adapter.search_request("ok", top_k=101)


if __name__ == "__main__":
    unittest.main()
