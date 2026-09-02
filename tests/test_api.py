"""
ZASI Backend Integration Test Suite (REST & MCP & Telemetry & OpenAPI)
"""
import unittest
import threading
import time
import json
import urllib.request
import urllib.error
import socket
import os
os.environ.setdefault("ZASI_ENABLE_LEGACY_COMPAT", "yes")
from backend.server import run_backend, HOST

class TestZASIBackendIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 18080
        cls.server_thread = threading.Thread(
            target=run_backend,
            kwargs={"port": cls.port},
            daemon=True
        )
        cls.server_thread.start()
        
        # Poll until server is responding cleanly
        for _ in range(30):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                    break
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _assert_retired(self, req):
        try:
            urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as exc:
            try:
                self.assertEqual(exc.code, 410)
            finally:
                exc.close()
        else:
            self.fail("retired route unexpectedly returned success")

    def test_status_endpoint(self):
        req = urllib.request.Request(self._url("/api/status"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "READY")
            self.assertEqual(data.get("subsystems_online"), 0)
            self.assertEqual(data.get("subsystems_catalog_entries"), 176)

    def test_telemetry_endpoint(self):
        req = urllib.request.Request(self._url("/api/telemetry"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("cpu_load", data)
            self.assertIn("arc_reactor_gw", data)

    def test_subsystems_catalog(self):
        req = urllib.request.Request(self._url("/api/subsystems"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("total_subsystems"), 176)
            self.assertEqual(len(data.get("catalog")), 176)

    def test_openapi_spec(self):
        req = urllib.request.Request(self._url("/api/openapi.json"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("openapi"), "3.0.3")
            self.assertIn("/api/status", data.get("paths", {}))
            self.assertIn("410", data["paths"]["/api/jarvis/chat"]["post"]["responses"])

    def test_legacy_jarvis_chat_is_retired(self):
        payload = json.dumps({"message": "status report", "persona": "JARVIS"}).encode()
        req = urllib.request.Request(self._url("/api/jarvis/chat"), data=payload, headers={"Content-Type": "application/json"})
        self._assert_retired(req)

    def test_legacy_mutation_is_retired(self):
        payload = json.dumps({"variable": "x", "delta": 5}).encode()
        req = urllib.request.Request(self._url("/api/mutate"), data=payload, headers={"Content-Type": "application/json"})
        self._assert_retired(req)

    def test_legacy_mcp_route_is_retired(self):
        payload = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}).encode()
        req = urllib.request.Request(self._url("/api/mcp"), data=payload, headers={"Content-Type": "application/json"})
        self._assert_retired(req)

    def test_legacy_webhook_routes_are_retired(self):
        get_req = urllib.request.Request(self._url("/api/webhooks"))
        self._assert_retired(get_req)
        payload = json.dumps({"url": "https://example.com/hook", "event": "tick"}).encode()
        post_req = urllib.request.Request(
            self._url("/api/webhooks"),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        self._assert_retired(post_req)

if __name__ == "__main__":
    unittest.main()
