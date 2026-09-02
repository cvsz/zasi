import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


class BriefingAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "briefing-api-secret",
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

    async def test_briefing_is_source_backed_and_connector_health_is_explicit(self):
        async with self.client() as client:
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "briefing-api-secret"}
            )
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            response = await client.post(
                "/api/v2/briefings",
                json={"sources": ["github"]},
                headers=headers,
            )
            self.assertEqual(response.status_code, 201)
            content = response.json()["content"]
            self.assertEqual(content["brief_id"], response.json()["briefing_id"])
            self.assertEqual(content["status"], "partial")
            self.assertEqual(content["missing_sources"][0]["source_ref"], "github")
            self.assertTrue(content["claims"])
            self.assertTrue(all(claim["evidence"] for claim in content["claims"]))

            connectors = await client.get("/api/v2/connectors", headers=headers)
            self.assertEqual(connectors.status_code, 200)
            connector_ids = {item["connector_id"] for item in connectors.json()["connectors"]}
            self.assertTrue({"github", "email", "calendar", "files", "web"}.issubset(connector_ids))
            self.assertEqual(
                next(item for item in connectors.json()["connectors"] if item["connector_id"] == "github")["status"],
                "unavailable",
            )
