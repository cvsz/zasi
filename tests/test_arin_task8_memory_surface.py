"""Task 8 memory-surface security regression.

This bounded slice locks the existing MemoryPage to authenticated, tenant-scoped
memory APIs. It does not turn memory into the canonical zknowbase runtime and it
grants no device, motion, tool, or actuator authority.
"""
from pathlib import Path
import posixpath
import re
import unittest
from urllib.parse import unquote

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
        auth_match = re.search(r"const\s*\{\s*session(?:\s*:\s*(\w+))?\s*\}\s*=\s*useAuth\(\)", self.surface)
        self.assertIsNotNone(auth_match, "MemoryPage must obtain its session directly from useAuth()")
        return auth_match.group(1) or "session"

    def _session_token_name(self) -> str:
        session = re.escape(self._authenticated_session_name())
        token_match = re.search(rf"const\s+(\w+)\s*=\s*{session}\?\.access_token\s*(?:\?\?|\|\|)\s*null", self.surface)
        self.assertIsNotNone(token_match, "MemoryPage must derive a token from the authenticated useAuth session")
        return token_match.group(1)

    def _assert_memory_route(self, route: str) -> None:
        path_literal = route.split("?", 1)[0].split("#", 1)[0]
        self.assertNotRegex(
            path_literal,
            r"\\(?:x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|u\{[0-9A-Fa-f]+\}|[0-7]{1,3})",
            "memory routes must not use JavaScript character escapes that can become browser dot segments",
        )
        interpolations = re.findall(r"\$\{([^{}]+)\}", path_literal)
        for expression in interpolations:
            self.assertRegex(
                expression.strip(),
                r"^encodeURIComponent\([A-Za-z_$][A-Za-z0-9_.$]*\)$",
                "dynamic memory path segments must be encoded with encodeURIComponent before fetch URL parsing",
            )
        static_path = re.sub(r"\$\{[^{}]+\}", "encoded-segment", path_literal)
        decoded = static_path
        for _ in range(4):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
        decoded = decoded.replace("\\", "/")
        self.assertNotIn("..", decoded.split("/"), "memory routes must not contain encoded, literal, or backslash dot-segment escapes")
        self.assertNotIn(".", decoded.split("/"), "memory routes must not contain encoded, literal, or backslash dot-segment aliases")
        path = posixpath.normpath(decoded)
        self.assertTrue(path == "/api/v2/memory" or path.startswith("/api/v2/memory/"), f"unexpected MemoryPage API route: {route}")

    @staticmethod
    def _top_level_object_properties(options: str) -> list[str]:
        properties: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        escaped = False
        for index, char in enumerate(options):
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "'\"`":
                quote = char
            elif char in "([{":
                depth += 1
            elif char in ")]}" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                properties.append(options[start:index].strip())
                start = index + 1
        properties.append(options[start:].strip())
        return [item for item in properties if item]

    @staticmethod
    def _balanced_object_body(source: str, open_brace: int) -> tuple[str, int]:
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(open_brace, len(source)):
            char = source[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "'\"`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[open_brace + 1:index], index + 1
        raise AssertionError("api.request options object must be balanced and statically provable")

    def test_surface_derives_authority_from_authenticated_session(self) -> None:
        token = re.escape(self._session_token_name())
        self.assertRegex(self.surface, rf"useApi<JsonRecord\[\]>\(\s*`/api/v2/memory/search\?\$\{{params\}}`\s*,\s*{token}\s*&&\s*\([^)]*\)\s*\?\s*{token}\s*:\s*null\s*\)", "memory search must pass the authenticated session-derived token on its authorized branch")

    def test_surface_uses_only_governed_memory_routes(self) -> None:
        call_pattern = re.compile(r"(?:api\.\w+(?:<[^>]+>)?|useApi(?:<[^>]+>)?)\(\s*")
        calls = list(call_pattern.finditer(self.surface))
        self.assertTrue(calls, "MemoryPage must expose governed API routes")
        for call in calls:
            remainder = self.surface[call.end():]
            route_match = re.match(r"(['\"`])(/api/[^'\"`\s,]*)\1\s*,", remainder)
            self.assertIsNotNone(route_match, "every MemoryPage API call must use a complete literal /api/ route as its first argument so its boundary is provable")
            self._assert_memory_route(route_match.group(2))
        self.assertNotRegex(self.surface, r"\bfetch\s*\(")

    def test_mutations_require_the_authenticated_token(self) -> None:
        token = self._session_token_name()
        positional_pattern = re.compile(r"api\.(post|put|patch|delete)(?:<[^>]+>)?\(\s*(['\"`])(/api/v2/memory[^'\"`]*)\2\s*,\s*([^,\n)]+)")
        positional_mutations = list(positional_pattern.finditer(self.surface))
        for mutation in positional_mutations:
            self._assert_memory_route(mutation.group(3))
            self.assertEqual(mutation.group(4).strip(), token, f"{mutation.group(1)} memory mutation must use exactly the authenticated session-derived token expression")

        request_start = re.compile(r"api\.request(?:<[^>]+>)?\(\s*(['\"`])(/api/v2/memory[^'\"`]*)\1\s*,\s*\{")
        request_mutations = []
        request_calls = list(request_start.finditer(self.surface))
        for request in request_calls:
            open_brace = request.end() - 1
            options, _ = self._balanced_object_body(self.surface, open_brace)
            properties = self._top_level_object_properties(options)
            method_properties = [prop for prop in properties if re.match(r"^method\s*:", prop)]
            self.assertEqual(len(method_properties), 1, "every api.request memory call must have exactly one statically provable method")
            method_match = re.fullmatch(r"method\s*:\s*['\"]([A-Z]+)['\"]", method_properties[0])
            self.assertIsNotNone(method_match, "api.request memory method must be a static uppercase literal")
            if method_match.group(1) in {"POST", "PUT", "PATCH", "DELETE"}:
                request_mutations.append(request)
                self._assert_memory_route(request.group(2))
                self.assertFalse(any(prop.startswith("...") for prop in properties), "request memory mutation options must not use spreads because they can override authorization")
                token_properties = [prop for prop in properties if prop == token or re.match(r"^token\s*:", prop)]
                self.assertEqual(len(token_properties), 1, "request memory mutation must have exactly one top-level token property")
                authenticated = bool(re.fullmatch(rf"token\s*:\s*{re.escape(token)}", token_properties[0]) or token_properties[0] == token)
                self.assertTrue(authenticated, "request memory mutation top-level token property must use the authenticated session-derived token")

        self.assertTrue(positional_mutations or request_mutations, "MemoryPage must expose governed memory mutations")

    def test_surface_does_not_handle_service_credentials(self) -> None:
        lowered = self.surface.lower()
        for forbidden in ("api_key", "apikey", "secret_key", "client_secret", "access_key", "private_key", "bearer ", "localstorage", "sessionstorage", "indexeddb"):
            self.assertNotIn(forbidden, lowered)

    def test_surface_grants_no_device_or_actuator_authority(self) -> None:
        lowered = self.surface.lower()
        for forbidden in ("actuator", "torque", "joint", "velocity", "motion command", "device command", "raw actuator", "ros2", "ros 2"):
            self.assertNotIn(forbidden, lowered)

if __name__ == "__main__":
    unittest.main()
