from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "web" / "static" / "cockpit.tsx"


class ArinTask8TelemetrySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = COCKPIT.read_text(encoding="utf-8")

    def test_authenticated_telemetry_surface_uses_governed_api(self):
        self.assertIn("function TelemetryPage()", self.source)
        self.assertIn("const { session } = useAuth();", self.source)
        self.assertIn("useApi<JsonRecord>('/api/v2/telemetry', token)", self.source)
        self.assertIn('path="telemetry" element={<TelemetryPage />}', self.source)

    def test_telemetry_surface_is_read_only_and_descriptive(self):
        start = self.source.index("function TelemetryPage()")
        end = self.source.index("function SettingsPage()", start)
        surface = self.source[start:end]
        self.assertNotIn("api.post(", surface)
        self.assertNotIn("api.upload(", surface)
        self.assertNotIn("method: 'DELETE'", surface)
        self.assertIn("This is not public ingress telemetry.", surface)
        self.assertIn("data?.disclosure", surface)

    def test_telemetry_surface_exposes_runtime_health_not_actuation(self):
        start = self.source.index("function TelemetryPage()")
        end = self.source.index("function SettingsPage()", start)
        surface = self.source[start:end]
        for label in ("PID", "CPU %", "MEM RSS", "MEM VMS", "DISK TOTAL", "DISK FREE"):
            self.assertIn(label, surface)
        for forbidden in ("actuator", "motion", "joint", "torque", "velocity", "execute-approved-skill"):
            self.assertNotIn(forbidden, surface.lower())


if __name__ == "__main__":
    unittest.main()
