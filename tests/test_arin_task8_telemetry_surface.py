from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "web" / "static" / "cockpit.tsx"


class ArinTask8TelemetrySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COCKPIT.read_text(encoding="utf-8")
        start = cls.source.index("function TelemetryPage()")
        end = cls.source.index("function SettingsPage()", start)
        cls.surface = cls.source[start:end]

    def test_authenticated_telemetry_surface_uses_governed_api(self):
        self.assertIn("const { session } = useAuth();", self.surface)
        self.assertIn("const token = session?.access_token ?? null;", self.surface)
        self.assertIn("useApi<JsonRecord>('/api/v2/telemetry', token)", self.surface)
        self.assertIn('path="telemetry" element={<TelemetryPage />}', self.source)

    def test_telemetry_surface_is_get_only_and_descriptive(self):
        # TelemetryPage must remain a passive governed read surface. Reject any
        # direct API/fetch mutation regardless of HTTP write method spelling.
        self.assertNotRegex(self.surface, r"\bapi\.(?:post|upload)\s*\(")
        self.assertNotRegex(self.surface, r"\bapi\.request\s*\(")
        self.assertNotRegex(self.surface, r"\bfetch\s*\(")
        self.assertNotRegex(
            self.surface,
            r"method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]",
        )
        self.assertEqual(
            re.findall(r"useApi<[^>]+>\((['\"])(.*?)\1\s*,", self.surface),
            [("'", "/api/v2/telemetry")],
        )
        self.assertIn("This is not public ingress telemetry.", self.surface)
        self.assertIn("data?.disclosure", self.surface)

    def test_telemetry_surface_exposes_runtime_health_not_actuation(self):
        for label in ("PID", "CPU %", "MEM RSS", "MEM VMS", "DISK TOTAL", "DISK FREE"):
            self.assertIn(label, self.surface)
        for forbidden in ("actuator", "motion", "joint", "torque", "velocity", "execute-approved-skill"):
            self.assertNotIn(forbidden, self.surface.lower())


if __name__ == "__main__":
    unittest.main()
