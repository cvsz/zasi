import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from backend import server as legacy_server
from main import legacy_demo_main
from src.api_server import ZASIWebServer


class LegacyTruthfulnessTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(legacy_server.ZASIUnifiedHandler)

    def _chat(self, query, persona="JARVIS"):
        with patch.multiple(
            legacy_server,
            OPENROUTER_API_KEY="",
            OPENCODE_API_KEY="",
            KILO_API_KEY="",
            GEMINI_API_KEY="",
        ):
            return self.handler.process_jarvis_command(query, persona)

    def test_legacy_chat_reports_reference_boundaries(self):
        for query in ("status", "cad", "screenshot", "rsi", "hardware"):
            response = self._chat(query)
            lowered = response.lower()
            self.assertIn("unavailable", lowered)
            self.assertIn("reference", lowered)
            self.assertNotIn("178.2 gw", lowered)
            self.assertNotIn("320x", lowered)
            self.assertNotIn("3,500 exaflops", lowered)
            self.assertNotIn("operating at peak efficiency", lowered)

    def test_legacy_chat_cannot_trigger_tick_or_rsi(self):
        with patch.object(legacy_server.daemon, "step_cycle") as step_cycle:
            with patch.object(legacy_server.rsi_engine, "hot_swap_runtime") as hot_swap:
                self._chat("tick")
                self._chat("upgrade rsi")
        step_cycle.assert_not_called()
        hot_swap.assert_not_called()

    def test_legacy_subsystem_execution_is_disabled(self):
        with patch.object(legacy_server.fpga_accel, "dispatch_systolic_matmul") as dispatch:
            result = self.handler.execute_subsystem("fpga_accelerator")
        dispatch.assert_not_called()
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(result["active"])
        self.assertEqual(result["evidence_state"], "unverified")

    def test_legacy_openapi_marks_side_effect_paths_retired(self):
        self.assertIn("legacy", legacy_server.OPENAPI_SPEC["info"]["description"].lower())
        self.assertIn(
            "local host",
            legacy_server.OPENAPI_SPEC["paths"]["/api/telemetry"]["get"]["summary"].lower(),
        )
        self.assertIn(
            "historical",
            legacy_server.OPENAPI_SPEC["paths"]["/api/subsystems"]["get"]["summary"].lower(),
        )
        for path in ("/api/tick", "/api/mutate", "/api/rsi/upgrade", "/api/webhooks"):
            responses = legacy_server.OPENAPI_SPEC["paths"][path]["get" if path == "/api/tick" else "post"]["responses"]
            self.assertIn("410", responses)

    def test_legacy_background_mutation_surfaces_are_disabled(self):
        self.assertFalse(legacy_server._legacy_background_work_enabled())

    def test_legacy_demo_entrypoint_is_disabled(self):
        output = io.StringIO()
        with redirect_stdout(output):
            legacy_demo_main()
        rendered = output.getvalue().lower()
        self.assertIn("simulation-only", rendered)
        self.assertIn("disabled", rendered)
        self.assertNotIn("178.2 gw", rendered)
        self.assertNotIn("asi runtime daemon", rendered)

    def test_legacy_hud_has_no_fixed_default_token_or_live_status(self):
        daemon = SimpleNamespace(
            rsi_engine=SimpleNamespace(current_version="reference"),
            state=SimpleNamespace(variables={}, invariants=[]),
            telemetry_history=[],
        )
        hud = ZASIWebServer(daemon)
        self.assertIsNone(hud.api_token)
        snapshot = hud._get_system_snapshot()
        self.assertEqual(snapshot["status"], "reference")
        self.assertEqual(snapshot["auth_scheme"], "EXPLICIT_BEARER_TOKEN_COMPAT")
        self.assertEqual(snapshot["runtime_state"], "disabled")
        self.assertEqual(snapshot["evidence_state"], "unverified")
        self.assertNotIn("zasi-apex-master-key-2026", hud._generate_html_dashboard())

    def test_legacy_hud_escapes_untrusted_snapshot_values(self):
        daemon = SimpleNamespace(
            rsi_engine=SimpleNamespace(current_version="reference"),
            state=SimpleNamespace(
                variables={"payload": "</pre><script>alert(1)</script>"},
                invariants=[],
            ),
            telemetry_history=[],
        )
        html = ZASIWebServer(daemon)._generate_html_dashboard()
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("</pre><script>", html)
        self.assertIn("&lt;/pre&gt;", html)


if __name__ == "__main__":
    unittest.main()
