import datetime as dt
import time
import unittest

from src.control_plane.execution import ActionBroker, ActionWorker, ToolDefinition, ToolRegistry
from src.control_plane.governance.policy import PolicyEngine
from src.control_plane.storage import ConflictError, ControlPlaneStore


class ActionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.registry = ToolRegistry()
        self.calls = []

        def observe(payload):
            self.calls.append(dict(payload))
            return {"observed": payload.get("value", "ok")}

        self.registry.register(
            ToolDefinition(
                tool_id="registry.worker.observe",
                version="1.0.0",
                risk_tier="R0",
                required_scopes=frozenset({"workspace:read"}),
                handler=observe,
                evidence_status="simulated",
                disclosure="Worker test observation has no external side effect.",
                max_attempts=2,
                retry_policy="bounded",
            )
        )
        self.broker = ActionBroker(
            store=self.store,
            registry=self.registry,
            policy=PolicyEngine(self.registry.capabilities()),
        )

    def tearDown(self):
        self.store.close()

    def _submit(self, key="action-1"):
        return self.broker.submit(
            tenant_id="tenant-a",
            principal_id="principal-a",
            tool_id="registry.worker.observe",
            payload={"value": "ok"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key=key,
        )

    def test_submit_durably_queues_and_worker_completes(self):
        submitted = self._submit()
        self.assertEqual(submitted.status, "queued")
        self.assertEqual(self.calls, [])
        queued = self.store.get_run(submitted.run_id, "tenant-a")
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["action_status"], "queued")

        completed = ActionWorker(
            self.store, self.registry, worker_id="action-worker-a"
        ).run_once("tenant-a", submitted.run_id)

        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(self.calls, [{"value": "ok"}])
        event_types = [event["type"] for event in self.store.list_events("tenant-a")]
        self.assertEqual(
            event_types,
            ["run.created", "run.claimed", "evidence.created", "run.succeeded"],
        )

    def test_expired_lease_becomes_unknown_until_explicit_reconciliation(self):
        submitted = self._submit()
        base = dt.datetime.now(dt.timezone.utc)
        claimed = self.store.claim_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-a",
            lease_seconds=10,
            now=base,
        )
        self.assertIsNotNone(claimed)
        with self.assertRaises(ConflictError):
            self.store.finish_action(
                submitted.run_id,
                "tenant-a",
                "action-worker-b",
                claimed["lease_token"],
                "succeeded",
                result={"must_not": "complete"},
                evidence_status="simulated",
                provenance={"adapter_id": "registry.worker.observe"},
                disclosure="test",
            )

        self.assertIsNone(
            self.store.claim_action(
                submitted.run_id,
                "tenant-a",
                "action-worker-b",
                lease_seconds=10,
                now=base + dt.timedelta(seconds=11),
            )
        )
        unknown = self.store.get_run(submitted.run_id, "tenant-a")
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(unknown["action_status"], "unknown")
        self.assertEqual(self.calls, [])

        reconciled = self.store.reconcile_action(
            submitted.run_id,
            "tenant-a",
            "principal-a",
            outcome="retry",
            reason="Operator confirmed the worker never invoked the local adapter.",
        )
        self.assertEqual(reconciled["status"], "queued")
        claimed_again = self.store.claim_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-b",
            lease_seconds=10,
            now=base + dt.timedelta(seconds=12),
        )
        self.assertIsNotNone(claimed_again)
        completed_again = self.store.finish_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-b",
            claimed_again["lease_token"],
            "succeeded",
            result={"observed": "after-reconcile"},
            evidence_status="simulated",
            provenance={"adapter_id": "registry.worker.observe"},
            disclosure="test",
            now=base + dt.timedelta(seconds=13),
        )
        self.assertEqual(completed_again["status"], "succeeded")
        self.assertEqual(completed_again["evidence"]["result"], {"observed": "after-reconcile"})

    def test_terminal_reconciliation_supersedes_uncertain_evidence(self):
        submitted = self._submit("reconcile-terminal")
        claimed = self.store.claim_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-a",
            lease_seconds=1,
            now=dt.datetime.now(dt.timezone.utc),
        )
        self.assertIsNotNone(claimed)
        with self.assertRaises(ConflictError):
            self.store.finish_action(
                submitted.run_id,
                "tenant-a",
                "action-worker-a",
                claimed["lease_token"],
                "succeeded",
                result={"late": True},
                evidence_status="simulated",
                provenance={"adapter_id": "registry.worker.observe"},
                disclosure="test",
                now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2),
            )
        unknown = self.store.get_run(submitted.run_id, "tenant-a")
        old_evidence_id = unknown["evidence"]["evidence_id"]
        reconciled = self.store.reconcile_action(
            submitted.run_id,
            "tenant-a",
            "principal-a",
            outcome="succeeded",
            reason="Operator verified the observation from an independent local record.",
            result={"observed": "verified-locally"},
        )
        self.assertEqual(reconciled["status"], "succeeded")
        self.assertEqual(reconciled["evidence"]["status"], "unknown")
        self.assertEqual(reconciled["evidence"]["result"], {"observed": "verified-locally"})
        evidence_row = self.store._conn().execute(
            "SELECT supersedes FROM evidence WHERE id = ?",
            (reconciled["evidence"]["evidence_id"],),
        ).fetchone()
        self.assertEqual(evidence_row["supersedes"], old_evidence_id)
        evidence_count = self.store._conn().execute(
            "SELECT COUNT(*) AS count FROM evidence WHERE tenant_id = ? AND kind = 'action_result'",
            ("tenant-a",),
        ).fetchone()
        self.assertEqual(evidence_count["count"], 2)

    def test_timeout_is_unknown_and_is_not_automatically_retried(self):
        def slow(_payload):
            time.sleep(0.05)
            return {"late": True}

        self.registry.register(
            ToolDefinition(
                tool_id="registry.worker.slow",
                version="1.0.0",
                risk_tier="R0",
                required_scopes=frozenset({"workspace:read"}),
                handler=slow,
                evidence_status="simulated",
                disclosure="Timeout test has no external side effect.",
                timeout_ms=5,
            )
        )
        slow_broker = ActionBroker(
            store=self.store,
            registry=self.registry,
            policy=PolicyEngine(self.registry.capabilities()),
        )
        submitted = slow_broker.submit(
            tenant_id="tenant-a",
            principal_id="principal-a",
            tool_id="registry.worker.slow",
            payload={},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="slow-1",
        )

        completed = ActionWorker(
            self.store, self.registry, worker_id="action-worker-timeout"
        ).run_once("tenant-a", submitted.run_id)

        self.assertEqual(completed["status"], "unknown")
        self.assertEqual(self.store.get_run(submitted.run_id, "tenant-a")["status"], "unknown")

    def test_bounded_local_failure_is_retried_without_creating_a_second_run(self):
        attempts = []

        def flaky(_payload):
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise RuntimeError("fixture failure")
            return {"attempt": len(attempts)}

        retry_registry = ToolRegistry()
        retry_registry.register(
            ToolDefinition(
                tool_id="registry.worker.flaky",
                version="1.0.0",
                risk_tier="R0",
                required_scopes=frozenset({"workspace:read"}),
                handler=flaky,
                evidence_status="simulated",
                disclosure="Bounded retry test has no external side effect.",
                max_attempts=2,
                retry_policy="bounded",
            )
        )
        retry_broker = ActionBroker(
            self.store, retry_registry, PolicyEngine(retry_registry.capabilities())
        )
        submitted = retry_broker.submit(
            "tenant-a",
            "principal-a",
            "registry.worker.flaky",
            {},
            "R0",
            frozenset({"workspace:read"}),
            "flaky-1",
        )
        worker = ActionWorker(self.store, retry_registry, worker_id="retry-worker")
        first = worker.run_once("tenant-a", submitted.run_id)
        self.assertEqual(first["status"], "queued")
        self.assertEqual(first["action_status"], "retry")
        self.assertEqual(attempts, [1])

        second = worker.run_once(
            "tenant-a",
            submitted.run_id,
            now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2),
        )
        self.assertEqual(second["status"], "succeeded")
        self.assertEqual(second["action_attempt_count"], 2)
        self.assertEqual(attempts, [1, 2])

    def test_running_cancellation_becomes_unknown_when_handler_returns(self):
        submitted = self._submit("cancel-running")
        claimed = self.store.claim_action(
            submitted.run_id, "tenant-a", "action-worker-a", lease_seconds=60
        )
        self.assertIsNotNone(claimed)
        requested = self.store.cancel_run(
            submitted.run_id, "tenant-a", "principal-a"
        )
        self.assertEqual(requested["status"], "cancel_requested")

        completed = self.store.finish_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-a",
            claimed["lease_token"],
            "succeeded",
            result={"observed": "late"},
            evidence_status="simulated",
            provenance={"adapter_id": "registry.worker.observe"},
            disclosure="test",
        )
        self.assertEqual(completed["status"], "unknown")

    def test_cancellation_idempotency_replays_without_duplicate_event(self):
        submitted = self._submit("cancel-idempotent")
        first = self.store.cancel_run(
            submitted.run_id,
            "tenant-a",
            "principal-a",
            idempotency_key="cancel-request-1",
        )
        second = self.store.cancel_run(
            submitted.run_id,
            "tenant-a",
            "principal-a",
            idempotency_key="cancel-request-1",
        )
        self.assertEqual(second, first)
        self.assertEqual(
            [event["type"] for event in self.store.list_events("tenant-a")].count(
                "run.cancelled"
            ),
            1,
        )

        another = self._submit("cancel-idempotent-another")
        with self.assertRaises(ConflictError):
            self.store.cancel_run(
                another.run_id,
                "tenant-a",
                "principal-a",
                idempotency_key="cancel-request-1",
            )

    def test_cancel_requested_lease_expiry_becomes_unknown(self):
        submitted = self._submit("cancel-expired")
        base = dt.datetime.now(dt.timezone.utc)
        claimed = self.store.claim_action(
            submitted.run_id,
            "tenant-a",
            "action-worker-a",
            lease_seconds=1,
            now=base,
        )
        self.assertIsNotNone(claimed)
        requested = self.store.cancel_run(
            submitted.run_id, "tenant-a", "principal-a"
        )
        self.assertEqual(requested["status"], "cancel_requested")

        self.assertIsNone(
            self.store.claim_action(
                submitted.run_id,
                "tenant-a",
                "action-worker-b",
                lease_seconds=1,
                now=base + dt.timedelta(seconds=2),
            )
        )
        expired = self.store.get_run(submitted.run_id, "tenant-a")
        self.assertEqual(expired["status"], "unknown")
        self.assertEqual(expired["unknown_reason"], "lease_expired")

    def test_inline_execute_uses_the_durable_worker_path(self):
        result = self.broker.execute(
            tenant_id="tenant-a",
            principal_id="principal-a",
            tool_id="registry.worker.observe",
            payload={"value": "inline"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="inline-1",
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(self.calls, [{"value": "inline"}])


if __name__ == "__main__":
    unittest.main()
