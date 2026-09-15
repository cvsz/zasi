import unittest

from backend.arin.knowledge import KnowledgeContractError
from backend.arin.knowledge_write import ZKnowbaseWriteAuthorization


class ZKnowbaseWriteAuthorizationTests(unittest.TestCase):
    def authorize(self, **overrides):
        values = {
            "api_key": "scoped-write-key",
            "tenant_id": "tenant-a",
            "granted_scopes": {"knowledge:write"},
            "policy_allowed": True,
            "approval_id": "approval-123",
        }
        values.update(overrides)
        return ZKnowbaseWriteAuthorization.authorize(**values)

    def test_requires_write_scope_policy_and_approval_evidence(self):
        denied = [
            {"granted_scopes": {"knowledge:read"}},
            {"policy_allowed": False},
            {"approval_id": "   "},
            {"api_key": "   "},
            {"tenant_id": "   "},
        ]
        for overrides in denied:
            with self.subTest(overrides=overrides):
                with self.assertRaises(KnowledgeContractError):
                    self.authorize(**overrides)

    def test_authorized_write_context_is_tenant_scoped_and_secret_redacted(self):
        auth = self.authorize()
        self.assertEqual(auth.headers["X-API-Key"], "scoped-write-key")
        self.assertEqual(auth.headers["X-ZWorkforce-Tenant-ID"], "tenant-a")
        self.assertEqual(auth.approval_id, "approval-123")
        self.assertNotIn("scoped-write-key", repr(auth))

    def test_gate_exposes_no_ingest_or_network_transport(self):
        auth = self.authorize()
        self.assertFalse(hasattr(auth, "ingest"))
        self.assertFalse(hasattr(auth, "send"))
        self.assertFalse(hasattr(auth, "transport"))


if __name__ == "__main__":
    unittest.main()
