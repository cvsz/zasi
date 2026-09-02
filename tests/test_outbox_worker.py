import threading
import unittest
from datetime import datetime, timezone

from src.control_plane.storage import ControlPlaneStore
from src.control_plane.worker import OutboxWorker


class OutboxWorkerTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")

    def tearDown(self):
        self.store.close()

    def _append_event(self):
        self.store.append_audited_event(
            tenant_id="tenant-a",
            actor_kind="system",
            actor_id="worker-test",
            action="worker.test",
            target="worker-test",
            outcome="success",
            event_type="worker.test",
            aggregate_kind="worker-test",
            aggregate_id="worker-test",
            payload={"safe": True},
        )

    def test_run_once_drains_the_durable_event_stream_outbox(self):
        self._append_event()

        report = OutboxWorker(self.store, poll_interval_seconds=0.01).run_once()

        self.assertEqual(report.claimed, 1)
        self.assertEqual(report.delivered, 1)
        self.assertEqual(report.retried, 0)
        self.assertEqual(self.store.list_outbox(status="pending"), [])
        self.assertEqual(len(self.store.list_outbox(status="delivered")), 1)

    def test_run_forever_stops_after_a_handler_requests_shutdown(self):
        self._append_event()
        stop_event = threading.Event()
        delivered = []

        def handler(item):
            delivered.append(item["event_id"])
            stop_event.set()

        report = OutboxWorker(
            self.store,
            handler=handler,
            stop_event=stop_event,
            poll_interval_seconds=0.01,
        ).run_forever()

        self.assertEqual(report.iterations, 1)
        self.assertEqual(report.delivered, 1)
        self.assertEqual(report.retried, 0)
        self.assertEqual(len(delivered), 1)

    def test_handler_receives_the_bounded_worker_identifier(self):
        self._append_event()
        stop_event = threading.Event()
        observed = []

        def handler(item):
            observed.append(item["worker_id"])
            stop_event.set()

        report = OutboxWorker(
            self.store,
            handler=handler,
            stop_event=stop_event,
            worker_id="worker-observability",
        ).run_forever()

        self.assertEqual(report.delivered, 1)
        self.assertEqual(observed, ["worker-observability"])

    def test_unknown_destination_without_a_handler_is_retried_not_acknowledged(self):
        self._append_event()
        outbox_id = self.store.list_outbox()[0]["id"]
        self.store._conn().execute(
            "UPDATE outbox SET destination = 'external_sink' WHERE id = ?",
            (outbox_id,),
        )

        report = OutboxWorker(self.store, poll_interval_seconds=0.01).run_once()

        self.assertEqual(report.claimed, 1)
        self.assertEqual(report.delivered, 0)
        self.assertEqual(report.retried, 1)
        pending = self.store.list_outbox(status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["last_error"], "outbox handler is not configured")

    def test_dispatcher_reclaims_an_expired_processing_lease(self):
        self._append_event()
        outbox_id = self.store.list_outbox()[0]["id"]
        claimed = self.store.claim_outbox(outbox_id)
        self.assertIsNotNone(claimed)
        self.store._conn().execute(
            "UPDATE outbox SET lease_until = ?, status = 'processing' WHERE id = ?",
            (datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(), outbox_id),
        )

        report = OutboxWorker(self.store, poll_interval_seconds=0.01).run_once()

        self.assertEqual(report.claimed, 1)
        self.assertEqual(report.delivered, 1)
        self.assertEqual(self.store.list_outbox(status="delivered")[0]["id"], outbox_id)

    def test_claim_outbox_returns_none_when_conditional_update_changes_no_row(self):
        self._append_event()
        outbox_id = self.store.list_outbox()[0]["id"]
        self.store._conn().execute(
            """
            CREATE TRIGGER ignore_outbox_claim
            BEFORE UPDATE OF status ON outbox
            WHEN NEW.status = 'processing'
            BEGIN
                SELECT RAISE(IGNORE);
            END
            """
        )

        self.assertIsNone(self.store.claim_outbox(outbox_id))
        self.assertEqual(len(self.store.list_outbox(status="pending")), 1)

    def test_max_iterations_bounds_a_worker_run_without_sleeping_forever(self):
        report = OutboxWorker(
            self.store, poll_interval_seconds=0.01
        ).run_forever(max_iterations=2)

        self.assertEqual(report.iterations, 2)
        self.assertEqual(report.claimed, 0)
        self.assertEqual(report.delivered, 0)
        self.assertEqual(report.retried, 0)

    def test_worker_id_is_bounded_and_cannot_contain_control_characters(self):
        with self.assertRaises(ValueError):
            OutboxWorker(self.store, worker_id="")
        with self.assertRaises(ValueError):
            OutboxWorker(self.store, worker_id="worker\nlog-injection")


if __name__ == "__main__":
    unittest.main()
