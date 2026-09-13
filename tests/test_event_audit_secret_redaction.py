import unittest

from src.control_plane.redaction import REDACTED
from src.control_plane.storage import ControlPlaneStore


class EventAuditSecretRedactionTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")

    def tearDown(self):
        self.store.close()

    def test_event_and_audit_payloads_are_redacted_before_persistence(self):
        event = self.store.append_audited_event(
            tenant_id="tenant-a",
            actor_kind="system",
            actor_id="security-test",
            action="security.redaction.tested",
            target="credential-boundary",
            outcome="success",
            event_type="security.redaction.tested",
            aggregate_kind="security-test",
            aggregate_id="credential-boundary",
            payload={
                "authorization": "Bearer top-level-secret",
                "nested": {
                    "api_key": "nested-secret",
                    "message": "upstream failed: Authorization: Bearer embedded-secret",
                },
                "safe": "observable",
            },
        )

        self.assertEqual(event["payload"]["authorization"], REDACTED)
        self.assertEqual(event["payload"]["nested"]["api_key"], REDACTED)
        self.assertEqual(event["payload"]["safe"], "observable")

        events = self.store.list_events("tenant-a")
        audit = self.store.list_audit("tenant-a")
        durable = str({"events": events, "audit": audit})

        self.assertNotIn("top-level-secret", durable)
        self.assertNotIn("nested-secret", durable)
        self.assertNotIn("embedded-secret", durable)
        self.assertEqual(events[-1]["payload"]["authorization"], REDACTED)
        self.assertEqual(audit[0]["metadata"]["nested"]["api_key"], REDACTED)


if __name__ == "__main__":
    unittest.main()
