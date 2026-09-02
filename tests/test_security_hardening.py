import unittest

from backend import server as legacy_server
from src.javis_voice_multimodal import (
    AudioWaveformPacket,
    JAVISVoiceMultimodalInterface,
    MultimodalVisualFrame,
)
from src.sandbox_vm import MicroVMSandbox
from src.self_compilation import AutonomousSelfCompiler, CapabilityDisabled


class SecurityHardeningTests(unittest.TestCase):
    def test_legacy_websocket_requires_configured_api_key(self):
        class FakeHandler:
            path = "/ws"
            headers = {"X-API-Key": "wrong-secret"}
            client_address = ("127.0.0.1", 12345)
            responses = []

            def send_json_response(self, payload, status=200):
                self.responses.append((payload, status))

        previous_key = legacy_server.ZASI_API_KEY
        legacy_server.ZASI_API_KEY = "legacy-test-secret"
        try:
            handler = FakeHandler()
            self.assertFalse(legacy_server.ZASIUnifiedHandler._check_api_auth(handler))
            self.assertEqual(handler.responses[-1][1], 401)
            handler.headers = {"X-API-Key": "legacy-test-secret"}
            self.assertTrue(legacy_server.ZASIUnifiedHandler._check_api_auth(handler))
        finally:
            legacy_server.ZASI_API_KEY = previous_key

    def test_sandbox_rejects_execution_when_isolation_is_unavailable(self):
        sandbox = MicroVMSandbox(has_bwrap=False)
        result = sandbox.execute_in_sandbox("echo must-not-run")
        self.assertEqual(result.exit_code, -1)
        self.assertFalse(result.isolated_env)
        self.assertEqual(result.isolation_backend, "UNAVAILABLE")

    def test_self_compilation_is_disabled_without_a_research_worker(self):
        compiler = AutonomousSelfCompiler()
        with self.assertRaises(CapabilityDisabled):
            compiler.compile_dynamic_subroutine(
                "candidate-1",
                "def optimized_policy(value):\n    return value + 1\n",
            )

    def test_voice_flags_and_confidence_do_not_authorize_a_caller(self):
        interface = JAVISVoiceMultimodalInterface()
        packet = AudioWaveformPacket(
            sample_rate_hz=16000,
            duration_sec=1.0,
            transcript_text="status",
            speaker_tag="attacker",
            voiceprint_confidence=0.99,
            is_verified_commander=True,
        )
        self.assertFalse(interface.verify_speaker_biometrics(packet))

    def test_multimodal_outputs_disclose_unverified_data(self):
        interface = JAVISVoiceMultimodalInterface()
        brief = interface.synthesize_morning_brief({})
        self.assertEqual(brief.overnight_subsystems_evaluated, 0)
        self.assertEqual(brief.hardware_power_gw, 0.0)
        self.assertIn("unavailable", brief.greeting.lower())

        cad = interface.ingest_cad_assembly("untrusted-upload")
        self.assertFalse(cad.thermal_stress_nominal)
        self.assertEqual(cad.analysis_status, "simulation")

        analysis = interface.analyze_competitor_screen(
            MultimodalVisualFrame(
                width=100,
                height=100,
                detected_objects=[],
                scene_description="unknown",
                threat_assessment="unknown",
            )
        )
        self.assertEqual(analysis["evidence_state"], "unverified")
        self.assertNotIn("surpasses", analysis["benchmark_evaluation"].lower())


if __name__ == "__main__":
    unittest.main()
