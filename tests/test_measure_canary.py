import unittest
from unittest.mock import MagicMock, patch

from scripts.measure_canary import measure


class CanaryMeasurementTests(unittest.TestCase):
    def test_rejects_non_https_endpoint(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            measure("http://staging.example.com/health/ready", 20, 1)

    def test_requires_minimum_sample(self):
        with self.assertRaisesRegex(ValueError, "at least 20"):
            measure("https://staging.example.com/health/ready", 19, 1)

    @patch("scripts.measure_canary.time.perf_counter", side_effect=[0.0, 0.1] * 20)
    @patch("scripts.measure_canary.urllib.request.urlopen")
    def test_emits_external_probe_provenance(self, urlopen, _clock):
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        urlopen.return_value = response
        result = measure("https://staging.example.com/health/ready", 20, 1)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["measurement_source"], "external-http-probe")
        self.assertEqual(result["request_count"], 20)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["error_rate"], 0.0)
        self.assertEqual(result["p95_ms"], 100.0)


if __name__ == "__main__":
    unittest.main()
