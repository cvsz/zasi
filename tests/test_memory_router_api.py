import datetime as dt
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


class MemoryRouterAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "memory-api-secret",
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

    async def test_project_memory_search_exposes_provenance_and_stale_state(self):
        async with self.client() as client:
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "memory-api-secret"}
            )
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            created = await client.post(
                "/api/v2/memory",
                json={
                    "content": "project alpha decision",
                    "scope": "project",
                    "memory_type": "project",
                    "project_id": "project-alpha",
                    "source_ref": "github:cvsz/zasi@abc123",
                    "provenance": {"method": "operator-confirmed"},
                    "trust": "verified_external",
                },
                headers=headers,
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["project_id"], "project-alpha")
            self.assertEqual(created.json()["provenance"]["method"], "operator-confirmed")

            search = await client.get(
                "/api/v2/memory/search",
                params={"query": "project alpha", "project_id": "project-alpha"},
                headers=headers,
            )
            self.assertEqual(search.status_code, 200)
            self.assertEqual(len(search.json()["items"]), 1)
            self.assertEqual(
                search.json()["items"][0]["source_ref"], "github:cvsz/zasi@abc123"
            )

            stale = await client.post(
                "/api/v2/memory",
                json={
                    "content": "stale project note",
                    "scope": "project",
                    "memory_type": "project",
                    "project_id": "project-alpha",
                    "fresh_until": (
                        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
                    ).isoformat(),
                },
                headers=headers,
            )
            self.assertEqual(stale.status_code, 201)
            default_search = await client.get(
                "/api/v2/memory/search",
                params={"query": "stale project", "project_id": "project-alpha"},
                headers=headers,
            )
            self.assertEqual(default_search.json()["items"], [])
            include_stale = await client.get(
                "/api/v2/memory/search",
                params={
                    "query": "stale project",
                    "project_id": "project-alpha",
                    "include_stale": "true",
                },
                headers=headers,
            )
            self.assertEqual(include_stale.json()["items"][0]["status"], "stale")
