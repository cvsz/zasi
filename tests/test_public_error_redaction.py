import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import HTTPException

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.redaction import REDACTED
from src.control_plane.storage import ControlPlaneStore


class PublicErrorRedactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "test-bootstrap-secret",
                "ZASI_CORS_ORIGINS": "http://localhost:5173",
                "ZASI_DATABASE_PATH": str(Path(self.tempdir.name) / "control-plane.db"),
            }
        )
        self.store = ControlPlaneStore(settings.database_path)
        self.app = create_app(settings=settings, store=self.store)

        @self.app.get("/api/v2/_test/public-error-redaction")
        async def injected_public_error():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "UPSTREAM_CONFLICT",
                    "message": "upstream rejected Authorization: Bearer message-secret",
                    "details": {
                        "api_key": "detail-secret",
                        "nested": {
                            "message": "password=embedded-secret",
                            "safe": "observable",
                        },
                    },
                },
            )

    async def asyncTearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    @asynccontextmanager
    async def client(self):
        async with self.app.router.lifespan_context(self.app):
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                yield client

    async def test_http_exception_payload_redacts_credentials_before_response(self):
        async with self.client() as client:
            response = await client.get("/api/v2/_test/public-error-redaction")

        self.assertEqual(response.status_code, 409)
        body = response.json()["error"]
        self.assertEqual(body["code"], "UPSTREAM_CONFLICT")
        self.assertIn(REDACTED, body["message"])
        self.assertEqual(body["details"]["api_key"], REDACTED)
        self.assertEqual(body["details"]["nested"]["safe"], "observable")
        self.assertIn(REDACTED, body["details"]["nested"]["message"])

        for secret in ("message-secret", "detail-secret", "embedded-secret"):
            self.assertNotIn(secret, response.text)


if __name__ == "__main__":
    unittest.main()
