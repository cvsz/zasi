"""Task 8 memory-surface security regression.

This bounded slice locks the existing MemoryPage to authenticated, tenant-scoped
memory APIs. It does not turn memory into the canonical zknowbase runtime and it
grants no device, motion, tool, or actuator authority.
"""
from pathlib import Path
import posixpath
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

    def _authenticated_session_name(self) -> str:
        auth_match = re.search(
            r"const\s*\{\s*session(?:\s*:\s*(\w+))?\s*\}\s*=\s*useAuth\(\)",
            self.surface,
        )
        self.assertIsNotNone(auth_match, "MemoryPage must obtain its session directly from useAuth()")
        return auth_match.group(1) or "session"

    def _session_token_name(self) -> str:
        session = re.escape(self._authenticated_session_name())
        token_match = re.search(
            rf"const\s+(\w+)\s*=\s*{session}\?\.access_token\s*(?:\?\?|\|\|)\s*null",
            self.surface,
        )
        self.assertIsNotNone(token_match, "MemoryPage must derive a token from the authenticated useAuth session")
        return token_match.group(1)

    def _assert_memory_route(self, route: str) -> None:
        self.assertNotIn("..", route.split("?", 1)[0].split("#", 1)[0].split("/"), "memory routes must not contain dot-segment escapes")
        path = posixpath.normpath(route.split("?", 1)[0].split("#", 1)[0])
        self.assertTrue(path == "/api/v2/memory" or path.startswith("/api/v2/memory/"), f"unexpected MemoryPage API route: {route}")

    def test_surface_derives_authority_from_authenticated_session(self) -> None:
        token = re.escape(self._session_token_name())
        self.assertRegex(
            self.surface,
            rf"useApi<JsonRecord\[\]>\(\s*`/api/v2/memory/search\?\$\{{params\}}`\s*,\s*{token}\s*&&\s*\([^)]*\)\s*\?\s*{token}\s*:\s*null\s*\)",
            "memory search must pass the authenticated session-derived token on its authorized branch",
        )

    def test_surface_uses_only_governed_memory_routes(self) -> None:
        # Audit both direct api.* calls and useApi hooks. Fail closed unless the
        # first argument is a literal route provably contained by the memory API.
        call_pattern = re.compile(r"(?:api\.\w+(?:<[^>]+>)?|useApi(?:<[^>]+>)?)\(\s*")
        calls = list(call_pattern.finditer(self.surface))
        self.assertTrue(calls, "MemoryPage must expose governed API routes")
        for call in calls:
            remainder = self.surface[call.end() :]
            route_match = re.match(r"(['\"`])(/api/[^'\"`\s,)]*)", remainder)
            self.assertIsNotNone(route_match, "every MemoryPage API call must use a literal /api/ route so its boundary is provable")
            self._assert_memory_route(route_match.group(2))
        self.assertNotRegex(self.surface, r"\bfetch\s*\(")

    def test_mutations_require_the_authenticated_token(self) -> None:
        token = self._session_token_name()

        # Positional-token helpers carry authorization as the second argument.
        positional_pattern = re.compile(r"api\.(post|put|patch|delete)(?:<[^>]+>)?\(\s*(['\"`])(/api/v2/memory[^'\"`]*)\2\s*,\s*([^,}\s]+)")
        positional_mutations = list(positional_pattern.finditer(self.surface))
        for mutation in positional_mutations:
            self._assert_memory_route(mutation.group(3))
            self.assertEqual(mutation.group(4), token, f"{mutation.group(1)} memory mutation must use the authenticated session-derived token")

        # request() carries authorization inside its options object. Validate
        # every request mutation independently instead of parsing it as a
        # positional-token helper.
        request_pattern = re.compile(r"api\.request\(\s*(['\"`])(/api/v2/memory[^'\"`]*)\1\s*,\s*\{([^}]*)\}", re.DOTALL)
        request_mutations = []
        for request in request_pattern.finditer(self.surface):
            options = request.group(3)
            if re.search(r"method:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]", options):
                request_mutations.append(request)
                self._assert_memory_route(request.group(2))
                self.assertRegex(options, rf"(?:^|[,\s]){re.escape(token)}(?:[,\s]|$)", "request memory mutation must use the authenticated session-derived token")

        self.assertTrue(positional_mutations or request_mutations, "MemoryPage must expose governed memory mutations")

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
