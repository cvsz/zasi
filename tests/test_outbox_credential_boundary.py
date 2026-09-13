import unittest

from src.control_plane.events import OutboxDispatcher
from src.control_plane.storage import ControlPlaneStore


class OutboxCredentialBoundaryTests(unittest.TestCase):
    def test_external_handler_never_receives_internal_claim_token(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("tenant-a")
        try:
            store.append_audited_event(
                tenant_id="tenant-a",
                actor_kind="system",
                actor_id="test",
                action="delivery.requested",
                target="target-1",
                outcome="success",
                event_type="delivery.requested",
                aggregate_kind="test",
                aggregate_id="target-1",
                payload={"status": "ready"},
            )
            outbox_id = store.list_outbox()[0]["id"]
            store._conn().execute(
                "UPDATE outbox SET destination = 'external_sink' WHERE id = ?",
                (outbox_id,),
            )

            received = []
            report = OutboxDispatcher(store).dispatch_once(received.append)

            self.assertEqual(report.claimed, 1)
            self.assertEqual(report.delivered, 1)
            self.assertEqual(report.retried, 0)
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["id"], outbox_id)
            self.assertEqual(received[0]["destination"], "external_sink")
            self.assertNotIn("claim_token", received[0])
            self.assertEqual(store.list_outbox(status="delivered")[0]["id"], outbox_id)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
