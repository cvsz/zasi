import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


class GoalTaskAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "test-bootstrap-secret",
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

    async def test_authenticated_goal_task_lifecycle_and_lease_boundary(self):
        async with self.client() as client:
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            self.assertEqual(session.status_code, 201)
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}

            created_goal = await client.post(
                "/api/v2/goals",
                json={"title": "Prepare governed briefing", "priority": 10},
                headers=headers,
            )
            self.assertEqual(created_goal.status_code, 201)
            goal = created_goal.json()

            first_response = await client.post(
                f"/api/v2/goals/{goal['goal_id']}/tasks",
                json={
                    "title": "Collect sources",
                    "instruction": "Read the registered local sources.",
                    "idempotency_key": "api-goal-collect",
                },
                headers=headers,
            )
            self.assertEqual(first_response.status_code, 201)
            first = first_response.json()

            second_response = await client.post(
                f"/api/v2/goals/{goal['goal_id']}/tasks",
                json={
                    "title": "Draft briefing",
                    "instruction": "Draft only from collected evidence.",
                    "idempotency_key": "api-goal-draft",
                    "depends_on": [first["task_id"]],
                },
                headers=headers,
            )
            self.assertEqual(second_response.status_code, 201)
            second = second_response.json()

            blocked = await client.post(
                f"/api/v2/tasks/{second['task_id']}/claim",
                json={"worker_id": "api-worker"},
                headers=headers,
            )
            self.assertEqual(blocked.status_code, 409)
            self.assertEqual(blocked.json()["error"]["code"], "TASK_NOT_CLAIMABLE")

            claimed = await client.post(
                f"/api/v2/tasks/{first['task_id']}/claim",
                json={"worker_id": "api-worker", "lease_seconds": 60},
                headers=headers,
            )
            self.assertEqual(claimed.status_code, 200)
            lease = claimed.json()["lease_token"]
            self.assertTrue(lease)

            stolen = await client.post(
                f"/api/v2/tasks/{first['task_id']}/complete",
                json={
                    "worker_id": "other-worker",
                    "lease_token": lease,
                    "result": {"sources": 2},
                },
                headers=headers,
            )
            self.assertEqual(stolen.status_code, 409)

            completed = await client.post(
                f"/api/v2/tasks/{first['task_id']}/complete",
                json={
                    "worker_id": "api-worker",
                    "lease_token": lease,
                    "result": {"sources": 2},
                },
                headers=headers,
            )
            self.assertEqual(completed.status_code, 200)
            self.assertEqual(completed.json()["status"], "completed")
            self.assertNotIn("lease_token", completed.json())

            second_claim = await client.post(
                f"/api/v2/tasks/{second['task_id']}/claim",
                json={"worker_id": "api-worker"},
                headers=headers,
            )
            self.assertEqual(second_claim.status_code, 200)
            second_completed = await client.post(
                f"/api/v2/tasks/{second['task_id']}/complete",
                json={
                    "worker_id": "api-worker",
                    "lease_token": second_claim.json()["lease_token"],
                    "result": {"status": "drafted"},
                },
                headers=headers,
            )
            self.assertEqual(second_completed.status_code, 200)

            fetched_goal = await client.get(
                f"/api/v2/goals/{goal['goal_id']}", headers=headers
            )
            self.assertEqual(fetched_goal.status_code, 200)
            self.assertEqual(fetched_goal.json()["status"], "completed")

            tasks = await client.get(
                f"/api/v2/goals/{goal['goal_id']}/tasks", headers=headers
            )
            self.assertEqual(tasks.status_code, 200)
            self.assertEqual(len(tasks.json()["tasks"]), 2)
            self.assertTrue(
                all("lease_token" not in task for task in tasks.json()["tasks"])
            )

    async def test_goal_task_routes_require_authentication_and_scope(self):
        async with self.client() as client:
            response = await client.get("/api/v2/goals")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

            session = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            response = await client.post(
                "/api/v2/goals",
                json={"title": "No extra fields", "unexpected": True},
                headers=headers,
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
