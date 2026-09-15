import unittest
from unittest.mock import MagicMock, patch

from scripts.measure_canary import measure, verify_artifact


class CanaryMeasurementTests(unittest.TestCase):
    def test_rejects_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            measure("http://staging.example.com/health/ready", 20, 1)

    def test_requires_minimum_sample(self):
        with self.assertRaisesRegex(ValueError, "at least 20"):
            measure("https://staging.example.com/health/ready", 19, 1)

    @patch("scripts.measure_canary.time.perf_counter", side_effect=[0.0, 0.1] * 20)
    @patch("scripts.measure_canary.urllib.request.build_opener")
    def test_emits_external_probe_provenance_and_reads_complete_body(self, build_opener, _clock):
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "https://staging.example.com/health/ready"
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        build_opener.return_value = opener

        result = measure("https://staging.example.com/health/ready", 20, 1)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["measurement_source"], "external-http-probe")
        self.assertEqual(result["request_count"], 20)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["error_rate"], 0.0)
        self.assertEqual(result["p95_ms"], 100.0)
        self.assertRegex(result["artifact_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(verify_artifact(result))
        self.assertEqual(response.read.call_count, 20)
        for call in response.read.call_args_list:
            self.assertEqual(call.args, ())

    @patch("scripts.measure_canary.time.perf_counter", side_effect=[0.0, 0.1] * 20)
    @patch("scripts.measure_canary.urllib.request.build_opener")
    def test_integrity_digest_rejects_metric_tampering(self, build_opener, _clock):
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "https://staging.example.com/health/ready"
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        build_opener.return_value = opener

        result = measure("https://staging.example.com/health/ready", 20, 1)
        result["p95_ms"] = 1.0
        self.assertFalse(verify_artifact(result))

    @patch("scripts.measure_canary.time.perf_counter", side_effect=[0.0, 0.1] * 20)
    @patch("scripts.measure_canary.urllib.request.build_opener")
    def test_integrity_digest_rejects_endpoint_substitution(self, build_opener, _clock):
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "https://staging.example.com/health/ready"
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        build_opener.return_value = opener

        result = measure("https://staging.example.com/health/ready", 20, 1)
        result["endpoint_url"] = "https://other.example.com/health/ready"
        self.assertFalse(verify_artifact(result))

    @patch("scripts.measure_canary.time.perf_counter", side_effect=[0.0, 0.1] * 20)
    @patch("scripts.measure_canary.urllib.request.build_opener")
    def test_rejects_response_from_different_final_url(self, build_opener, _clock):
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "https://healthy.example.net/health/ready"
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        build_opener.return_value = opener

        result = measure("https://staging.example.com/health/ready", 20, 1)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_count"], 20)
        self.assertTrue(verify_artifact(result))


if __name__ == "__main__":
    unittest.main()
