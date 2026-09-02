import datetime as dt
import tempfile
import unittest
from pathlib import Path

from src.control_plane.scheduler import DurableScheduler
from src.control_plane.storage import CURRENT_SCHEMA_VERSION, ConflictError, ControlPlaneStore


class DurableSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_goal("goal-a", "tenant-a", "principal-a", "Scheduled work")
        self.store.create_task(
            "task-a",
            "goal-a",
            "tenant-a",
            "principal-a",
            "Run source check",
            "Read only the registered source.",
            "task-template-a",
            max_attempts=2,
        )

    def tearDown(self):
        self.store.close()

    def test_once_schedule_deduplicates_occurrence_and_persists_run_history(self):
        scheduled_for = dt.datetime.now(dt.timezone.utc)
        self.store.create_schedule(
            schedule_id="schedule-a",
            tenant_id="tenant-a",
            principal_id="principal-a",
            task_id="task-a",
            kind="once",
            next_run_at=scheduled_for,
            idempotency_key="schedule-key-a",
        )

        claimed = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-1",
            lease_seconds=60,
            now=scheduled_for,
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["schedule"]["status"], "running")
        run = claimed["run"]
        self.assertEqual(run["status"], "running")
        self.assertTrue(run["lease_token"])

        duplicate = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-2",
            now=scheduled_for,
        )
        self.assertIsNone(duplicate)
        self.assertNotIn("lease_token", self.store.get_schedule("schedule-a", "tenant-a"))
        history = self.store.list_task_runs("task-a", "tenant-a")
        self.assertEqual(len(history), 1)
        self.assertNotIn("lease_token", history[0])

        completed = self.store.complete_task_run(
            run["run_id"],
            "tenant-a",
            "scheduler-1",
            run["lease_token"],
            status="succeeded",
            result={"source": "local"},
        )
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(
            self.store.get_schedule("schedule-a", "tenant-a")["status"], "completed"
        )

        events = self.store.list_events("tenant-a")
        self.assertIn("schedule.created", [event["type"] for event in events])
        self.assertIn("task_run.claimed", [event["type"] for event in events])
        self.assertIn("task_run.completed", [event["type"] for event in events])
        self.assertNotIn("lease_token", str(events))

    def test_interval_schedule_advances_without_duplicate_occurrences(self):
        scheduled_for = dt.datetime.now(dt.timezone.utc)
        self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "interval",
            scheduled_for,
            "schedule-key-a",
            interval_seconds=60,
        )
        self.assertIsNone(
            self.store.claim_due_task("task-a", "tenant-a", "manual-worker")
        )
        first = self.store.claim_due_schedule(
            "schedule-a", "tenant-a", "scheduler-1", now=scheduled_for
        )
        self.assertIsNotNone(first)
        self.store.complete_task_run(
            first["run"]["run_id"],
            "tenant-a",
            "scheduler-1",
            first["run"]["lease_token"],
            status="succeeded",
            result={},
        )
        self.assertEqual(self.store.get_task("task-a", "tenant-a")["status"], "queued")
        self.assertEqual(self.store.get_goal("goal-a", "tenant-a")["status"], "active")
        current = self.store.get_schedule("schedule-a", "tenant-a")
        self.assertEqual(
            current["next_run_at"],
            (scheduled_for + dt.timedelta(minutes=1)).isoformat(),
        )
        self.assertIsNone(
            self.store.claim_due_schedule(
                "schedule-a",
                "tenant-a",
                "scheduler-2",
                now=scheduled_for + dt.timedelta(seconds=59),
            )
        )
        second = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-2",
            now=scheduled_for + dt.timedelta(seconds=60),
        )
        self.assertIsNotNone(second)
        self.assertNotEqual(first["run"]["run_id"], second["run"]["run_id"])

    def test_interval_schedule_does_not_overlap_running_occurrences(self):
        scheduled_for = dt.datetime.now(dt.timezone.utc)
        self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "interval",
            scheduled_for,
            "schedule-key-a",
            interval_seconds=60,
        )
        first = self.store.claim_due_schedule(
            "schedule-a", "tenant-a", "scheduler-1", now=scheduled_for
        )
        self.assertIsNotNone(first)
        self.assertIsNone(
            self.store.claim_due_schedule(
                "schedule-a",
                "tenant-a",
                "scheduler-2",
                now=scheduled_for + dt.timedelta(minutes=1),
            )
        )
        self.assertEqual(len(self.store.list_task_runs("task-a", "tenant-a")), 1)

        self.store.complete_task_run(
            first["run"]["run_id"],
            "tenant-a",
            "scheduler-1",
            first["run"]["lease_token"],
            status="succeeded",
        )
        second = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-2",
            now=scheduled_for + dt.timedelta(minutes=1),
        )
        self.assertIsNotNone(second)

    def test_cancelling_direct_run_releases_task_lease(self):
        claimed = self.store.claim_due_task("task-a", "tenant-a", "worker-a")
        cancelled = self.store.complete_task_run(
            claimed["task_run_id"],
            "tenant-a",
            "worker-a",
            claimed["lease_token"],
            status="cancelled",
        )
        self.assertEqual(cancelled["status"], "cancelled")
        task = self.store.get_task("task-a", "tenant-a")
        self.assertEqual(task["status"], "queued")
        self.assertIsNone(task["lease_until"])
        self.assertIsNotNone(
            self.store.claim_due_task("task-a", "tenant-a", "worker-b")
        )

    def test_expired_run_is_dead_lettered_atomically_at_attempt_limit(self):
        self.store.create_task(
            "task-once",
            "goal-a",
            "tenant-a",
            "principal-a",
            "One attempt",
            "Fail after one lease.",
            "dead-letter-task",
            max_attempts=1,
        )
        scheduled_for = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        claimed = self.store.claim_due_task(
            "task-once",
            "tenant-a",
            "worker-a",
            lease_seconds=10,
            now=scheduled_for,
        )
        self.assertIsNone(
            self.store.claim_task_run(
                claimed["task_run_id"],
                "tenant-a",
                "worker-b",
                lease_seconds=10,
                now=scheduled_for + dt.timedelta(seconds=11),
            )
        )
        run = self.store.get_task_run(claimed["task_run_id"], "tenant-a")
        self.assertEqual(run["status"], "dead_lettered")
        self.assertIsNone(run["worker_id"])
        self.assertIsNone(run["lease_until"])
        self.assertEqual(self.store.get_task("task-once", "tenant-a")["status"], "failed")
        self.assertIn(
            "task_run.dead_lettered",
            [event["type"] for event in self.store.list_events("tenant-a")],
        )

    def test_expired_run_can_be_reclaimed_but_wrong_worker_cannot_complete(self):
        scheduled_for = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            scheduled_for,
            "schedule-key-a",
        )
        first = self.store.claim_due_schedule(
            "schedule-a",
            "tenant-a",
            "scheduler-1",
            lease_seconds=10,
            now=scheduled_for,
        )
        with self.assertRaises(ConflictError):
            self.store.complete_task_run(
                first["run"]["run_id"],
                "tenant-a",
                "scheduler-2",
                first["run"]["lease_token"],
                status="succeeded",
                result={},
            )
        reclaimed = self.store.claim_task_run(
            first["run"]["run_id"],
            "tenant-a",
            "scheduler-2",
            lease_seconds=10,
            now=scheduled_for + dt.timedelta(seconds=11),
        )
        self.assertIsNotNone(reclaimed)
        self.assertNotEqual(
            first["run"]["lease_token"], reclaimed["lease_token"]
        )

    def test_reclaimed_direct_run_restores_task_lease_and_can_complete(self):
        base = dt.datetime.now(dt.timezone.utc)
        first = self.store.claim_due_task(
            "task-a", "tenant-a", "worker-a", lease_seconds=1, now=base
        )
        reclaimed = self.store.claim_task_run(
            first["task_run_id"],
            "tenant-a",
            "worker-b",
            lease_seconds=30,
            now=base + dt.timedelta(seconds=2),
        )
        self.assertIsNotNone(reclaimed)
        completed = self.store.complete_task_run(
            first["task_run_id"],
            "tenant-a",
            "worker-b",
            reclaimed["lease_token"],
            status="succeeded",
            result={"recovered": True},
        )
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(self.store.get_task("task-a", "tenant-a")["status"], "completed")

    def test_scheduled_state_survives_restart(self):
        scheduled_for = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "scheduler.db")
            store = ControlPlaneStore(database)
            store.initialize()
            store.create_tenant("tenant-a")
            store.create_principal("principal-a", "tenant-a")
            store.create_goal("goal-a", "tenant-a", "principal-a", "Scheduled work")
            store.create_task(
                "task-a",
                "goal-a",
                "tenant-a",
                "principal-a",
                "Run source check",
                "Read only the registered source.",
                "task-template-a",
            )
            store.create_schedule(
                "schedule-a",
                "tenant-a",
                "principal-a",
                "task-a",
                "interval",
                scheduled_for,
                "schedule-key-a",
                interval_seconds=300,
            )
            store.close()

            reopened = ControlPlaneStore(database)
            reopened.initialize()
            try:
                self.assertEqual(reopened.schema_version(), CURRENT_SCHEMA_VERSION)
                self.assertEqual(
                    reopened.get_schedule("schedule-a", "tenant-a")["next_run_at"],
                    "2026-09-02T09:00:00+00:00",
                )
            finally:
                reopened.close()

    def test_direct_task_claim_also_creates_durable_run_history(self):
        claimed = self.store.claim_due_task("task-a", "tenant-a", "worker-a")
        self.assertIsNotNone(claimed)
        self.assertTrue(claimed["task_run_id"])
        history = self.store.list_task_runs("task-a", "tenant-a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["run_id"], claimed["task_run_id"])
        self.store.complete_task(
            "task-a",
            "tenant-a",
            "worker-a",
            claimed["lease_token"],
            {},
        )
        self.assertEqual(
            self.store.get_task_run(claimed["task_run_id"], "tenant-a")["status"],
            "succeeded",
        )

    def test_failed_direct_run_requeues_task_for_a_new_attempt(self):
        claimed = self.store.claim_due_task("task-a", "tenant-a", "worker-a")
        failed = self.store.complete_task_run(
            claimed["task_run_id"],
            "tenant-a",
            "worker-a",
            claimed["lease_token"],
            status="failed",
            error={"code": "temporary"},
        )
        self.assertEqual(failed["status"], "retry")
        self.assertEqual(self.store.get_task("task-a", "tenant-a")["status"], "retry")
        retried = self.store.claim_due_task("task-a", "tenant-a", "worker-b")
        self.assertIsNotNone(retried)
        self.assertEqual(retried["attempt_count"], 2)

    def test_schedule_cancellation_is_durable_and_stops_claims(self):
        schedule = self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
            "schedule-key-a",
        )
        cancelled = self.store.cancel_schedule(
            schedule["schedule_id"], "tenant-a", "principal-a"
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(
            self.store.claim_due_schedule(
                schedule["schedule_id"],
                "tenant-a",
                "worker-a",
                now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2),
            )
        )

    def test_schedule_cancellation_cancels_running_run_with_an_event(self):
        scheduled_for = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        schedule = self.store.create_schedule(
            "schedule-a",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            scheduled_for,
            "schedule-key-a",
        )
        claimed = self.store.claim_due_schedule(
            schedule["schedule_id"],
            "tenant-a",
            "worker-a",
            now=scheduled_for,
        )
        self.store.cancel_schedule(
            schedule["schedule_id"], "tenant-a", "principal-a"
        )
        run = self.store.get_task_run(claimed["run"]["run_id"], "tenant-a")
        self.assertEqual(run["status"], "cancelled")
        self.assertIsNone(run["worker_id"])
        self.assertIsNone(run["lease_until"])
        self.assertIn(
            "task_run.cancelled",
            [event["type"] for event in self.store.list_events("tenant-a")],
        )

    def test_scheduler_poller_claims_only_due_schedules(self):
        now = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        self.store.create_schedule(
            "schedule-due",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            now,
            "schedule-due-key",
        )
        self.store.create_schedule(
            "schedule-later",
            "tenant-a",
            "principal-a",
            "task-a",
            "once",
            now + dt.timedelta(minutes=5),
            "schedule-later-key",
        )
        claims = DurableScheduler(self.store, "scheduler-worker").poll(
            "tenant-a", now=now
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["run"]["schedule_id"], "schedule-due")
        self.assertEqual(self.store.list_task_runs("task-a", "tenant-a")[0]["schedule_id"], "schedule-due")
