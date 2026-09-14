import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.readiness import probe
from src.control_plane.config import Settings
from src.control_plane.execution import ToolRegistry
from src.control_plane.storage import ControlPlaneStore


class HealthyRedis:
    def ping(self):
        return True


class ReadinessTests(unittest.TestCase):
    def _staging_settings(self, database_path: str) -> Settings:
        """Build a valid settings object without coupling readiness tests to secret-provider I/O."""
        local = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "readiness-test-secret",
                "ZASI_DATABASE_PATH": database_path,
            }
        )
        return replace(
            local,
            profile="staging",
            database_backend="postgresql",
            database_url="postgresql://zasi:test@127.0.0.1:5432/zasi_test",
            redis_url="redis://:test@127.0.0.1:6379/0",
            secret_provider="systemd-credential",
            backup_policy="managed",
        )

    def test_missing_frontend_bundle_degrades_full_stack_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ControlPlaneStore(str(Path(directory) / "control-plane.db"))
            store.initialize()
            settings = Settings.from_mapping(
                {
                    "ZASI_PROFILE": "local",
                    "ZASI_API_KEY": "readiness-test-secret",
                    "ZASI_DATABASE_PATH": str(Path(directory) / "control-plane.db"),
                }
            )
            try:
                with patch(
                    "backend.readiness.frontend_dist_path",
                    return_value=Path(directory) / "missing-frontend",
                ):
                    result = probe(store, settings, ToolRegistry())
            finally:
                store.close()

        self.assertEqual(result["checks"]["frontend_bundle"], "unavailable")
        self.assertEqual(result["status"], "degraded")

    def test_staging_without_release_identity_is_degraded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frontend = root / "frontend"
            frontend.mkdir()
            (frontend / "index.html").write_text("ready", encoding="utf-8")
            store = ControlPlaneStore(str(root / "control-plane.db"))
            store.initialize()
            settings = self._staging_settings(str(root / "control-plane.db"))
            try:
                with (
                    patch("backend.readiness.frontend_dist_path", return_value=frontend),
                    patch.dict(
                        "os.environ",
                        {"ZASI_RELEASE_COMMIT": "", "ZASI_RELEASE_IMAGE": ""},
                    ),
                ):
                    result = probe(
                        store,
                        settings,
                        ToolRegistry(),
                        redis_runtime=HealthyRedis(),
                    )
            finally:
                store.close()

        self.assertEqual(result["checks"]["release_identity"], "unavailable")
        self.assertEqual(result["release_identity"]["commit"], None)
        self.assertEqual(result["release_identity"]["image"], None)
        self.assertEqual(result["status"], "degraded")

    def test_staging_reports_valid_immutable_release_identity(self):
        commit = "a" * 40
        image = "ghcr.io/cvsz/zasi@sha256:" + "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frontend = root / "frontend"
            frontend.mkdir()
            (frontend / "index.html").write_text("ready", encoding="utf-8")
            store = ControlPlaneStore(str(root / "control-plane.db"))
            store.initialize()
            settings = self._staging_settings(str(root / "control-plane.db"))
            try:
                with (
                    patch("backend.readiness.frontend_dist_path", return_value=frontend),
                    patch.dict(
                        "os.environ",
                        {"ZASI_RELEASE_COMMIT": commit, "ZASI_RELEASE_IMAGE": image},
                    ),
                ):
                    result = probe(
                        store,
                        settings,
                        ToolRegistry(),
                        redis_runtime=HealthyRedis(),
                    )
            finally:
                store.close()

        self.assertEqual(result["checks"]["release_identity"], "ready")
        self.assertEqual(result["release_identity"]["commit"], commit)
        self.assertEqual(result["release_identity"]["image"], image)
        self.assertEqual(result["status"], "ready")


if __name__ == "__main__":
    unittest.main()
