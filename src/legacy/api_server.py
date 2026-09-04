r"""
Retained J.A.R.V.I.S. reference HUD compatibility surface.

The governed API is implemented by ``backend.app``. This module is not an
RBAC or capability authority and is disabled unless a caller supplies an
explicit bearer token.
"""
import http.server
import socketserver
import json
import threading
import time
from html import escape
from typing import Dict, Any, List, Optional

class ZASIWebServer:
    def __init__(self, system_daemon, port: int = 8080, api_token: Optional[str] = None):
        self.daemon = system_daemon
        self.port = port
        self.api_token = api_token
        self.server = None
        self.thread = None
        self.audit_log: List[Dict[str, Any]] = []

    def log_audit_event(self, action: str, principal: str, status: str, details: Dict[str, Any]):
        event = {
            "timestamp": time.time(),
            "action": action,
            "principal": principal,
            "status": status,
            "details": details
        }
        self.audit_log.append(event)

    def _get_system_snapshot(self) -> Dict[str, Any]:
        return {
            "version": "compat-reference",
            "variables": self.daemon.state.variables,
            "invariants": self.daemon.state.invariants,
            "telemetry_recent": self.daemon.telemetry_history[-5:] if self.daemon.telemetry_history else [],
            "status": "reference",
            "runtime_state": "disabled",
            "evidence_state": "unverified",
            "disclosure": (
                "Retained HUD compatibility surface; daemon telemetry is "
                "simulation/reference data and does not establish live capability."
            ),
            "persona": "J.A.R.V.I.S.",
            "auth_scheme": "EXPLICIT_BEARER_TOKEN_COMPAT"
        }

    def _generate_html_dashboard(self) -> str:
        snapshot = self._get_system_snapshot()
        version = escape(str(snapshot["version"]))
        status = escape(str(snapshot["status"]))
        variables = escape(json.dumps(snapshot["variables"], ensure_ascii=False))
        invariants = escape(json.dumps(snapshot["invariants"], ensure_ascii=False))
        telemetry = escape(json.dumps(snapshot["telemetry_recent"], indent=2, ensure_ascii=False))
        audit_log = escape(json.dumps(self.audit_log[-3:], indent=2, ensure_ascii=False))
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>J.A.R.V.I.S. Holographic Tactical HUD</title>
    <meta http-equiv="refresh" content="3">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
            integrity="sha384-CI3ELBVUz9XQO+97x6nwMDPosPR5XvsxW2ua7N1Xeygeh1IxtgqtCkGfQY9WWdHu"
            crossorigin="anonymous"></script>
    <style>
        body {{ font-family: 'Consolas', 'Courier New', monospace; background: #030712; color: #38bdf8; margin: 0; padding: 20px; overflow-x: hidden; }}
        h1 {{ color: #00f0ff; text-shadow: 0 0 10px rgba(0, 240, 255, 0.7); border-bottom: 1px solid #0284c7; padding-bottom: 10px; }}
        .card {{ background: rgba(15, 23, 42, 0.85); border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 0 15px rgba(0, 240, 255, 0.2); border: 1px solid #0369a1; backdrop-filter: blur(10px); }}
        .badge {{ background: #0284c7; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; box-shadow: 0 0 8px #38bdf8; }}
        pre {{ background: #020617; padding: 10px; border-radius: 4px; overflow-x: auto; color: #67e8f9; border: 1px solid #0f172a; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        #canvas3d {{ width: 100%; height: 260px; background: radial-gradient(circle, #082f49 0%, #030712 100%); border-radius: 6px; border: 1px solid #0284c7; }}
        .btn {{ background: #0284c7; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-family: inherit; font-weight: bold; }}
        .btn:hover {{ background: #0369a1; box-shadow: 0 0 10px #38bdf8; }}
    </style>
</head>
<body>
    <h1>⚡ J.A.R.V.I.S. REFERENCE HUD <span class="badge">{version}</span></h1>
    <div class="grid">
        <div class="card">
            <h3>Reference Telemetry (disabled runtime)</h3>
            <p><strong>Variables:</strong> {variables}</p>
            <p><strong>Formal Invariants:</strong> {invariants}</p>
            <p><strong>Status:</strong> <span style="color: #4ade80;">{status}</span></p>
            <button class="btn" onclick="speakStatus()">🔊 Voice Status Report</button>
            <div id="canvas3d" style="margin-top: 15px;"></div>
        </div>
        <div class="card">
            <h3>Autonomous Cognitive Telemetry Stream</h3>
            <pre>{telemetry}</pre>
            <h3>Security & Audit Log</h3>
            <pre>{audit_log}</pre>
        </div>
    </div>
    <script>
        function speakStatus() {{
            if ('speechSynthesis' in window) {{
                const utterance = new SpeechSynthesisUtterance("ZASI reference HUD. Live subsystem and hardware capability evidence is unavailable.");
                utterance.pitch = 0.9;
                utterance.rate = 1.05;
                window.speechSynthesis.speak(utterance);
            }}
        }}

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, 2, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
        const container = document.getElementById('canvas3d');
        if (container) {{
            renderer.setSize(container.clientWidth, container.clientHeight);
            container.appendChild(renderer.domElement);
            const geometry = new THREE.TorusKnotGeometry(1.5, 0.4, 100, 16);
            const material = new THREE.MeshBasicMaterial({{ color: 0x00f0ff, wireframe: true }});
            const torus = new THREE.Mesh(geometry, material);
            scene.add(torus);
            camera.position.z = 4;
            function animate() {{
                requestAnimationFrame(animate);
                torus.rotation.x += 0.01;
                torus.rotation.y += 0.015;
                renderer.render(scene, camera);
            }}
            animate();
        }}
    </script>
</body>
</html>"""

    def start(self):
        if not self.api_token:
            print(
                "  [J.A.R.V.I.S. Reference HUD] disabled: an explicit bearer "
                "token is required; use backend.app for the authoritative API."
            )
            return
        parent = self
        class RequestHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(parent._generate_html_dashboard().encode())
                elif self.path == "/api/snapshot":
                    # Check token authentication for JSON API
                    auth_header = self.headers.get("Authorization", "")
                    if auth_header != f"Bearer {parent.api_token}":
                        parent.log_audit_event("API_READ_ATTEMPT", "ANONYMOUS", "UNAUTHORIZED", {"path": self.path})
                        self.send_response(401)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Unauthorized: Invalid or missing Bearer token."}).encode())
                        return

                    parent.log_audit_event("API_SNAPSHOT_READ", "OPERATOR_KEY", "AUTHORIZED", {})
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(parent._get_system_snapshot()).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.server = socketserver.TCPServer(("127.0.0.1", self.port), RequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"  [J.A.R.V.I.S. Tactical HUD] Secure API Running at http://localhost:{self.port}")
        except Exception as e:
            print(f"  [J.A.R.V.I.S. Tactical HUD] Notice: Web HUD port {self.port} bound ({e}).")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
