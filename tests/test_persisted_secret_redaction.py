import datetime as dt
import unittest

from src.control_plane.redaction import REDACTED, TRUNCATED, sanitize_persisted_payload
from src.control_plane.storage import ControlPlaneStore


class PersistedSecretRedactionTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_goal("goal-a", "tenant-a", "principal-a", "Secret-safe work")
        self.store.create_task(
            "task-a",
            "goal-a",
            "tenant-a",
            "principal-a",
            "Complete safely",
            "Persist only sanitized worker output.",
            "secret-safe-task",
            max_attempts=2,
        )

    def tearDown(self):
        self.store.close()

    def test_redaction_is_recursive_and_bounded(self):
        payload = {
            "authorization": "Bearer top-secret",
            "nested": {
                "api-key": "key-value",
                "message": "request failed with Authorization: Bearer nested-secret",
            },
            "items": [{"refresh_token": "refresh-secret"}],
        }
        sanitized = sanitize_persisted_payload(payload)
        self.assertEqual(sanitized["authorization"], REDACTED)
        self.assertEqual(sanitized["nested"]["api-key"], REDACTED)
        self.assertNotIn("nested-secret", sanitized["nested"]["message"])
        self.assertEqual(sanitized["items"][0]["refresh_token"], REDACTED)

        too_deep = current = {}
        for index in range(20):
            current["next"] = {}
            current = current["next"]
            current["depth"] = index
        self.assertIn(TRUNCATED, str(sanitize_persisted_payload(too_deep)))

    def test_direct_task_completion_redacts_result_before_persistence(self):
        claimed = self.store.claim_due_task("task-a", "tenant-a", "worker-a")
        self.assertIsNotNone(claimed)
        secrets = {
            "access_token": "access-secret",
            "nested": {
                "password": "password-secret",
                "message": "Authorization: Bearer bearer-secret",
            },
            "safe": "observable-result",
        }
        completed = self.store.complete_task(
            "task-a",
            "tenant-a",
            "worker-a",
            claimed["lease_token"],
            secrets,
        )
        serialized = str(completed)
        self.assertEqual(completed["result"]["access_token"], REDACTED)
        self.assertEqual(completed["result"]["nested"]["password"], REDACTED)
        self.assertEqual(completed["result"]["safe"], "observable-result")
        self.assertNotIn("access-secret", serialized)
        self.assertNotIn("password-secret", serialized)
        self.assertNotIn("bearer-secret", serialized)

        history = self.store.list_task_runs("task-a", "tenant-a")
        self.assertNotIn("access-secret", str(history))
        self.assertNotIn("password-secret", str(history))
        self.assertNotIn("bearer-secret", str(history))

    def test_scheduled_task_run_redacts_result_and_error_before_persistence(self):
        scheduled_for = dt.datetime.now(dt.timezone.utc)
        self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            scheduled_for,
            "schedule-secret-safe",
        )
        claimed = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-a",
            now=scheduled_for,
        )
        self.assertIsNotNone(claimed)
        run = claimed["run"]
        completed = self.store.complete_task_run(
            run["run_id"],
            "tenant-a",
            "scheduler-a",
            run["lease_token"],
            status="failed",
            result={"client_secret": "client-secret", "safe": 7},
            error={
                "credential": "credential-secret",
                "message": "api_key=embedded-secret upstream failure",
            },
        )
        self.assertEqual(completed["result"]["client_secret"], REDACTED)
        self.assertEqual(completed["error"]["credential"], REDACTED)
        self.assertEqual(completed["result"]["safe"], 7)
        serialized = str(self.store.get_task_run(run["run_id"], "tenant-a"))
        self.assertNotIn("client-secret", serialized)
        self.assertNotIn("credential-secret", serialized)
        self.assertNotIn("embedded-secret", serialized)
