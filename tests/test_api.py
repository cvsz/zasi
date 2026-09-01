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
        
        # Poll until server is responding
        for _ in range(30):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                    break
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_status_endpoint(self):
        req = urllib.request.Request(self._url("/api/status"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("status"), "OPERATIONAL")
            self.assertEqual(data.get("subsystems_online"), 168)

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
            self.assertEqual(data.get("total_subsystems"), 168)
            self.assertEqual(len(data.get("catalog")), 168)

    def test_openapi_spec(self):
        req = urllib.request.Request(self._url("/api/openapi.json"))
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("openapi"), "3.0.3")
            self.assertIn("/api/status", data.get("paths", {}))

    def test_jarvis_chat(self):
        payload = json.dumps({"message": "status report", "persona": "JARVIS"}).encode()
        req = urllib.request.Request(self._url("/api/jarvis/chat"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("speaker"), "JARVIS")
            self.assertIn("168 subsystems", data.get("response"))

    def test_mutate_state(self):
        payload = json.dumps({"variable": "x", "delta": 5}).encode()
        req = urllib.request.Request(self._url("/api/mutate"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("success"))

    def test_mcp_jsonrpc(self):
        payload = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}).encode()
        req = urllib.request.Request(self._url("/api/mcp"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("jsonrpc"), "2.0")

if __name__ == "__main__":
    unittest.main()
