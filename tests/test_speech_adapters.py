import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from src.control_plane.speech_adapters import (
    FliteTTSAdapter,
    SpeechAdapterError,
    WhisperCppSTTAdapter,
)


class SpeechAdapterTests(unittest.TestCase):
    def _executable(self, directory: str, name: str, body: str) -> str:
        path = Path(directory) / name
        path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body), encoding="utf-8")
        path.chmod(0o700)
        return str(path)

    def test_whisper_cpp_adapter_runs_bounded_subprocess_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self._executable(
                directory,
                "stt-runner",
                """
                import pathlib, sys
                arguments = iter(sys.argv[1:])
                output_prefix = None
                for argument in arguments:
                    if argument == '-of':
                        output_prefix = next(arguments)
                pathlib.Path(output_prefix + '.txt').write_text('status report\\n', encoding='utf-8')
                """,
            )
            model = Path(directory) / "model.bin"
            model.write_bytes(b"model-bytes")
            model.chmod(0o600)

            result = WhisperCppSTTAdapter(
                executable=executable,
                model_path=str(model),
                timeout_seconds=5,
            ).transcribe(b"audio-bytes", content_type="audio/wav")

            self.assertEqual(result.text, "status report")
            self.assertEqual(result.adapter_id, "zasi.stt.whisper-cpp")
            self.assertEqual(result.evidence_state, "locally_verified")
            self.assertTrue(result.source_digest.startswith("sha256:"))
            self.assertTrue(result.model_digest.startswith("sha256:"))
            self.assertIn("argv-only", result.disclosure)

    def test_flite_adapter_runs_bounded_subprocess_and_returns_wave_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self._executable(
                directory,
                "tts-runner",
                """
                import pathlib, sys, wave
                arguments = iter(sys.argv[1:])
                output = None
                for argument in arguments:
                    if argument == '-o':
                        output = next(arguments)
                with wave.open(output, 'wb') as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes(b'\\x00\\x00' * 160)
                """,
            )

            result = FliteTTSAdapter(
                executable=executable,
                timeout_seconds=5,
            ).synthesize("system ready")

            self.assertEqual(result.content_type, "audio/wav")
            self.assertGreater(len(result.audio_bytes), 44)
            self.assertEqual(result.adapter_id, "zasi.tts.flite")
            self.assertEqual(result.evidence_state, "locally_verified")
            self.assertIn("argv-only", result.disclosure)

    def test_adapters_fail_closed_on_missing_inputs_and_unsafe_text(self):
        with self.assertRaisesRegex(SpeechAdapterError, "model"):
            WhisperCppSTTAdapter(
                executable="/does/not/exist",
                model_path="/does/not/exist/model.bin",
            ).transcribe(b"audio", content_type="audio/wav")

        with tempfile.TemporaryDirectory() as directory:
            executable = self._executable(directory, "tts-runner", "raise SystemExit(0)")
            with self.assertRaisesRegex(SpeechAdapterError, "text"):
                FliteTTSAdapter(executable=executable).synthesize("bad\x00text")

    def test_adapters_reject_unsupported_audio_and_unbounded_text(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self._executable(directory, "stt-runner", "raise SystemExit(0)")
            model = Path(directory) / "model.bin"
            model.write_bytes(b"model")
            model.chmod(0o600)
            adapter = WhisperCppSTTAdapter(
                executable=executable,
                model_path=str(model),
            )
            with self.assertRaisesRegex(SpeechAdapterError, "audio format"):
                adapter.transcribe(b"audio", content_type="application/octet-stream")

            tts = FliteTTSAdapter(executable=executable, max_text_chars=4)
            with self.assertRaisesRegex(SpeechAdapterError, "text length"):
                tts.synthesize("too long")


if __name__ == "__main__":
    unittest.main()
