import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.readiness import probe
from src.control_plane.config import Settings
from src.control_plane.execution import ToolRegistry
from src.control_plane.storage import ControlPlaneStore


class ReadinessTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
