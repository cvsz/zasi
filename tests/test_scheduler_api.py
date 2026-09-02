import datetime as dt
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


class DurableSchedulerAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "scheduler-api-secret",
                "ZASI_DATABASE_PATH": str(Path(self.tempdir.name) / "control-plane.db"),
            }
        )
        self.store = ControlPlaneStore(settings.database_path)
        self.app = create_app(settings=settings, store=self.store)

    async def asyncTearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    @asynccontextmanager
    async def client(self):
        async with self.app.router.lifespan_context(self.app):
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                yield client

    async def test_schedule_claim_completion_and_history_are_authenticated(self):
        async with self.client() as client:
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "scheduler-api-secret"}
            )
            self.assertEqual(session.status_code, 201)
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            goal = await client.post(
                "/api/v2/goals", json={"title": "Scheduled API goal"}, headers=headers
            )
            self.assertEqual(goal.status_code, 201)
            task = await client.post(
                f"/api/v2/goals/{goal.json()['goal_id']}/tasks",
                json={
                    "title": "Scheduled API task",
                    "instruction": "Observe the local source.",
                    "idempotency_key": "scheduler-api-task",
                },
                headers=headers,
            )
            self.assertEqual(task.status_code, 201)
            due = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
            schedule = await client.post(
                f"/api/v2/goals/{goal.json()['goal_id']}/schedules",
                json={
                    "task_id": task.json()["task_id"],
                    "kind": "once",
                    "next_run_at": due,
                    "idempotency_key": "scheduler-api-once",
                },
                headers=headers,
            )
            self.assertEqual(schedule.status_code, 201)
            schedule_id = schedule.json()["schedule_id"]

            schedule_replay = await client.post(
                f"/api/v2/goals/{goal.json()['goal_id']}/schedules",
                json={
                    "task_id": task.json()["task_id"],
                    "kind": "once",
                    "next_run_at": (
                        dt.datetime.fromisoformat(due) + dt.timedelta(hours=1)
                    ).isoformat().replace("+00:00", "+01:00"),
                    "idempotency_key": "scheduler-api-once",
                },
                headers=headers,
            )
            self.assertEqual(schedule_replay.status_code, 200)
            self.assertEqual(schedule_replay.json()["schedule_id"], schedule_id)

            other_goal = await client.post(
                "/api/v2/goals", json={"title": "Another schedule goal"}, headers=headers
            )
            self.assertEqual(other_goal.status_code, 201)
            wrong_goal_replay = await client.post(
                f"/api/v2/goals/{other_goal.json()['goal_id']}/schedules",
                json={
                    "task_id": task.json()["task_id"],
                    "kind": "once",
                    "next_run_at": due,
                    "idempotency_key": "scheduler-api-once",
                },
                headers=headers,
            )
            self.assertEqual(wrong_goal_replay.status_code, 409)
            self.assertEqual(
                wrong_goal_replay.json()["error"]["code"], "IDEMPOTENCY_CONFLICT"
            )

            claimed = await client.post(
                f"/api/v2/schedules/{schedule_id}/claim",
                json={"worker_id": "api-scheduler"},
                headers=headers,
            )
            self.assertEqual(claimed.status_code, 200)
            run = claimed.json()["run"]
            self.assertTrue(run["lease_token"])

            duplicate = await client.post(
                f"/api/v2/schedules/{schedule_id}/claim",
                json={"worker_id": "other-scheduler"},
                headers=headers,
            )
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.json()["error"]["code"], "SCHEDULE_NOT_CLAIMABLE")

            completed = await client.post(
                f"/api/v2/task-runs/{run['run_id']}/complete",
                json={
                    "worker_id": "api-scheduler",
                    "lease_token": run["lease_token"],
                    "status": "succeeded",
                    "result": {"observed": True},
                },
                headers=headers,
            )
            self.assertEqual(completed.status_code, 200)
            self.assertEqual(completed.json()["status"], "succeeded")

            history = await client.get(
                f"/api/v2/tasks/{task.json()['task_id']}/runs", headers=headers
            )
            self.assertEqual(history.status_code, 200)
            self.assertEqual(history.json()["runs"][0]["status"], "succeeded")
            self.assertNotIn("lease_token", history.text)

            future = await client.post(
                f"/api/v2/goals/{goal.json()['goal_id']}/schedules",
                json={
                    "task_id": task.json()["task_id"],
                    "kind": "once",
                    "next_run_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat(),
                    "idempotency_key": "scheduler-api-cancel",
                },
                headers=headers,
            )
            self.assertEqual(future.status_code, 201)
            cancel_headers = {**headers, "Idempotency-Key": "scheduler-cancel-1"}
            missing_cancel_key = await client.post(
                f"/api/v2/schedules/{future.json()['schedule_id']}/cancel",
                headers=headers,
            )
            self.assertEqual(missing_cancel_key.status_code, 400)
            self.assertEqual(
                missing_cancel_key.json()["error"]["code"], "IDEMPOTENCY_REQUIRED"
            )
            cancelled = await client.post(
                f"/api/v2/schedules/{future.json()['schedule_id']}/cancel",
                headers=cancel_headers,
            )
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["status"], "cancelled")
            cancel_replay = await client.post(
                f"/api/v2/schedules/{future.json()['schedule_id']}/cancel",
                headers=cancel_headers,
            )
            self.assertEqual(cancel_replay.status_code, 200)
            self.assertEqual(
                cancel_replay.json()["schedule_id"], future.json()["schedule_id"]
            )
            conflicting_cancel = await client.post(
                "/api/v2/schedules/schedule-from-another-request/cancel",
                headers=cancel_headers,
            )
            self.assertEqual(conflicting_cancel.status_code, 409)
            self.assertEqual(
                conflicting_cancel.json()["error"]["code"], "IDEMPOTENCY_CONFLICT"
            )
