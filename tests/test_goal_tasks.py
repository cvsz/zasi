import datetime as dt
import tempfile
import unittest
from pathlib import Path

from src.control_plane.storage import (
    CURRENT_SCHEMA_VERSION,
    ConflictError,
    ControlPlaneStore,
    ScopeViolation,
)


class GoalTaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_tenant("tenant-b")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_principal("principal-b", "tenant-b")

    def tearDown(self):
        self.store.close()

    def test_goal_task_dag_is_durable_and_completes_atomically(self):
        goal = self.store.create_goal(
            goal_id="goal-a",
            tenant_id="tenant-a",
            principal_id="principal-a",
            title="Prepare briefing",
            description="Collect the approved source material.",
            priority=10,
        )
        first = self.store.create_task(
            task_id="task-a1",
            goal_id=goal["goal_id"],
            tenant_id="tenant-a",
            principal_id="principal-a",
            title="Collect sources",
            instruction="Read the registered local sources.",
            idempotency_key="goal-a-collect",
        )
        second = self.store.create_task(
            task_id="task-a2",
            goal_id=goal["goal_id"],
            tenant_id="tenant-a",
            principal_id="principal-a",
            title="Draft briefing",
            instruction="Draft only from collected evidence.",
            idempotency_key="goal-a-draft",
            depends_on=[first["task_id"]],
        )

        self.assertEqual(first["status"], "queued")
        self.assertEqual(second["dependencies"], ["task-a1"])
        self.assertIsNone(self.store.claim_due_task("task-a2", "tenant-a", "worker-1"))

        claimed_first = self.store.claim_due_task("task-a1", "tenant-a", "worker-1")
        self.assertIsNotNone(claimed_first)
        self.assertEqual(claimed_first["status"], "running")
        self.assertTrue(claimed_first["lease_token"])
        completed_first = self.store.complete_task(
            "task-a1",
            "tenant-a",
            "worker-1",
            claimed_first["lease_token"],
            {"sources": 2},
        )
        self.assertEqual(completed_first["status"], "completed")

        claimed_second = self.store.claim_due_task("task-a2", "tenant-a", "worker-1")
        self.assertIsNotNone(claimed_second)
        self.store.complete_task(
            "task-a2",
            "tenant-a",
            "worker-1",
            claimed_second["lease_token"],
            {"status": "drafted"},
        )

        self.assertEqual(
            self.store.get_goal("goal-a", "tenant-a")["status"], "completed"
        )
        self.assertEqual(
            self.store.get_task("task-a2", "tenant-a")["result"], {"status": "drafted"}
        )
        event_types = [event["type"] for event in self.store.list_events("tenant-a")]
        self.assertIn("goal.created", event_types)
        self.assertIn("task.created", event_types)
        self.assertIn("task.claimed", event_types)
        self.assertIn("task.completed", event_types)
        self.assertIn("goal.completed", event_types)

    def test_task_idempotency_and_dependency_scope_are_enforced(self):
        goal = self.store.create_goal("goal-a", "tenant-a", "principal-a", "A")
        other_goal = self.store.create_goal("goal-b", "tenant-b", "principal-b", "B")
        other_task = self.store.create_task(
            "task-b1",
            other_goal["goal_id"],
            "tenant-b",
            "principal-b",
            "B1",
            "one",
            "other-key",
        )
        self.store.create_task(
            "task-a1",
            goal["goal_id"],
            "tenant-a",
            "principal-a",
            "A1",
            "one",
            "same-key",
        )
        with self.assertRaises(ConflictError):
            self.store.create_task(
                "task-a2",
                goal["goal_id"],
                "tenant-a",
                "principal-a",
                "A2",
                "two",
                "same-key",
            )
        with self.assertRaises(ScopeViolation):
            self.store.create_task(
                "task-a3",
                goal["goal_id"],
                "tenant-a",
                "principal-a",
                "A3",
                "three",
                "cross-goal",
                depends_on=[other_task["task_id"]],
            )
        with self.assertRaises(ValueError):
            self.store.create_task(
                "task-a4",
                goal["goal_id"],
                "tenant-a",
                "principal-a",
                "A4",
                "four",
                "self-cycle",
                depends_on=["task-a4"],
            )
        with self.assertRaises(ScopeViolation):
            self.store.get_goal(other_goal["goal_id"], "tenant-a")

    def test_expired_lease_is_recoverable_and_wrong_worker_cannot_complete(self):
        self.store.create_goal("goal-a", "tenant-a", "principal-a", "A")
        self.store.create_task(
            "task-a1", "goal-a", "tenant-a", "principal-a", "A1", "one", "lease-key"
        )
        base = dt.datetime.now(dt.timezone.utc)
        first = self.store.claim_due_task(
            "task-a1", "tenant-a", "worker-1", lease_seconds=30, now=base
        )
        self.assertIsNotNone(first)
        with self.assertRaises(ConflictError):
            self.store.complete_task(
                "task-a1", "tenant-a", "worker-2", first["lease_token"], {}
            )

        second = self.store.claim_due_task(
            "task-a1",
            "tenant-a",
            "worker-2",
            lease_seconds=30,
            now=base + dt.timedelta(seconds=31),
        )
        self.assertIsNotNone(second)
        self.assertNotEqual(first["lease_token"], second["lease_token"])
        self.store.complete_task(
            "task-a1", "tenant-a", "worker-2", second["lease_token"], {}
        )

    def test_restart_preserves_goal_and_task_state_with_schema_ten(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "goals.db")
            store = ControlPlaneStore(database)
            store.initialize()
            store.create_tenant("tenant-a")
            store.create_principal("principal-a", "tenant-a")
            store.create_goal("goal-a", "tenant-a", "principal-a", "Persistent goal")
            store.create_task(
                "task-a1",
                "goal-a",
                "tenant-a",
                "principal-a",
                "Persistent task",
                "work",
                "persist-key",
            )
            self.assertEqual(store.schema_version(), CURRENT_SCHEMA_VERSION)
            store.close()

            reopened = ControlPlaneStore(database)
            reopened.initialize()
            try:
                self.assertEqual(reopened.schema_version(), CURRENT_SCHEMA_VERSION)
                self.assertEqual(
                    reopened.get_goal("goal-a", "tenant-a")["title"], "Persistent goal"
                )
                self.assertEqual(
                    reopened.get_task("task-a1", "tenant-a")["status"], "queued"
                )
            finally:
                reopened.close()

    def test_schema_seven_database_receives_additive_goal_task_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "schema-seven.db")
            store = ControlPlaneStore(database)
            store.initialize()
            with store._lock:
                connection = store._conn()
                connection.execute("DROP TABLE task_dependencies")
                connection.execute("DROP TABLE tasks")
                connection.execute("DROP TABLE goals")
                connection.execute(
                    "UPDATE schema_meta SET value = '7' WHERE key = 'schema_version'"
                )
            store.close()

            reopened = ControlPlaneStore(database)
            reopened.initialize()
            try:
                self.assertEqual(reopened.schema_version(), CURRENT_SCHEMA_VERSION)
                columns = {
                    row["name"]
                    for row in reopened._conn()
                    .execute("PRAGMA table_info(tasks)")
                    .fetchall()
                }
                self.assertIn("lease_owner", columns)
                self.assertEqual(reopened.list_goals("tenant-a"), [])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
