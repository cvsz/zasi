"""Task 8 provider-surface security regression.

This slice intentionally tests the existing ModelsPage before any provider UI
expansion. Browser-visible provider/model status must remain authenticated and
read-only; provider credentials and mutation/actuation authority stay server-side.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "web" / "static" / "cockpit.tsx"


class ProviderSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COCKPIT.read_text(encoding="utf-8")
        start = cls.source.index("function ModelsPage()")
        # Keep assertions scoped to the existing provider/model status surface.
        next_page = re.search(r"\nfunction [A-Z][A-Za-z0-9]+Page\(\)", cls.source[start + 1 :])
        if next_page is None:
            raise AssertionError("ModelsPage must be followed by another page component")
        end = start + 1 + next_page.start()
        cls.surface = cls.source[start:end]

    def test_surface_binds_model_status_to_authenticated_session(self) -> None:
        self.assertIn("useAuth()", self.surface)
        token_match = re.search(
            r"const\s+(\w+)\s*=\s*session\?\.access_token\s*(?:\?\?|\|\|)\s*null",
            self.surface,
        )
        self.assertIsNotNone(token_match, "ModelsPage must derive a token from the authenticated session")
        token_name = token_match.group(1)
        self.assertRegex(
            self.surface,
            rf"useModelStatus\(\s*{re.escape(token_name)}\s*\)",
            "provider/model status must be requested with the session-derived token",
        )

    def test_surface_is_read_only(self) -> None:
        mutation_call = re.compile(
            r"(?:\bapi\s*\.\s*(?:post|put|patch|delete|upload|request)|\bfetch)"
            r"\s*(?:<[^;(){}]+>)?\s*\(",
            re.IGNORECASE,
        )
        self.assertIsNone(
            mutation_call.search(self.surface),
            "ModelsPage must not issue browser-side mutation or direct fetch calls",
        )
        self.assertIsNone(re.search(r"method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]", self.surface))

    def test_surface_does_not_handle_provider_secrets(self) -> None:
        lowered = self.surface.lower()
        for forbidden in (
            "api_key", "apikey", "secret_key", "client_secret", "access_key",
            "private_key", "bearer ", "localstorage", "sessionstorage", "indexeddb",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_surface_grants_no_device_or_actuator_authority(self) -> None:
        lowered = self.surface.lower()
        for forbidden in (
            "actuator", "torque", "joint", "velocity", "motion command",
            "device command", "raw actuator",
        ):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
