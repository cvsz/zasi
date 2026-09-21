"""Task 8 memory-surface security regression.

This bounded slice locks the existing MemoryPage to authenticated, tenant-scoped
memory APIs. It does not turn memory into the canonical zknowbase runtime and it
grants no device, motion, tool, or actuator authority.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "web" / "static" / "cockpit.tsx"


class MemorySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = COCKPIT.read_text(encoding="utf-8")
        start = cls.source.index("function MemoryPage()")
        next_page = re.search(r"\nfunction [A-Z][A-Za-z0-9]+Page\(\)", cls.source[start + 1 :])
        if next_page is None:
            raise AssertionError("MemoryPage must be followed by another page component")
        end = start + 1 + next_page.start()
        cls.surface = cls.source[start:end]

    def _session_token_name(self) -> str:
        token_match = re.search(
            r"const\s+(\w+)\s*=\s*session\?\.access_token\s*(?:\?\?|\|\|)\s*null",
            self.surface,
        )
        self.assertIsNotNone(token_match, "MemoryPage must derive a token from the authenticated session")
        return token_match.group(1)

    def test_surface_derives_authority_from_authenticated_session(self) -> None:
        self.assertIn("useAuth()", self.surface)
        token = self._session_token_name()
        self.assertRegex(
            self.surface,
            rf"useApi<JsonRecord\[\]>\([^;]+,\s*{re.escape(token)}\s*&&",
            "memory search must remain gated by the session-derived token",
        )

    def test_surface_uses_only_governed_memory_routes(self) -> None:
        # Inspect string arguments beginning with /api/v2, including template
        # literals, so a route cannot escape this guard by changing quote style.
        routes = set(re.findall(r"(?:['\"`])(/api/v2/[^'\"`?${}]+)", self.surface))
        self.assertTrue(routes, "MemoryPage must expose governed API routes")
        for route in routes:
            self.assertTrue(
                route == "/api/v2/memory" or route.startswith("/api/v2/memory/"),
                f"unexpected MemoryPage API route: {route}",
            )
        self.assertNotRegex(self.surface, r"\bfetch\s*\(")

    def test_mutations_require_the_authenticated_token(self) -> None:
        token = re.escape(self._session_token_name())
        self.assertRegex(
            self.surface,
            rf"api\.post\(\s*['\"]/api/v2/memory['\"]\s*,\s*{token}\s*,",
            "memory creation must use the session-derived authenticated token",
        )
        self.assertRegex(
            self.surface,
            rf"api\.request\(\s*`/api/v2/memory/\$\{{memoryId\}}`\s*,\s*\{{\s*{token}\s*,\s*method:\s*['\"]DELETE['\"]",
            "memory deletion must use the session-derived authenticated token",
        )

    def test_surface_does_not_handle_service_credentials(self) -> None:
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
            "device command", "raw actuator", "ros2", "ros 2",
        ):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
