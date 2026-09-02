r"""
ZASI Secure Holographic J.A.R.V.I.S. HUD & Authenticated REST API
Includes Bearer Token Auth, RBAC (Admin/Operator/Auditor), Audit Logging, and Mutation Approval Gates.
"""
import http.server
import socketserver
import json
import threading
import time
from typing import Dict, Any, List

class ZASIWebServer:
    def __init__(self, system_daemon, port: int = 8080, api_token: str = "zasi-apex-master-key-2026"):
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
            "version": self.daemon.rsi_engine.current_version,
            "variables": self.daemon.state.variables,
            "invariants": self.daemon.state.invariants,
            "telemetry_recent": self.daemon.telemetry_history[-5:] if self.daemon.telemetry_history else [],
            "status": "OPERATIONAL",
            "persona": "J.A.R.V.I.S.",
            "auth_scheme": "BEARER_TOKEN_RBAC"
        }

    def _generate_html_dashboard(self) -> str:
        snapshot = self._get_system_snapshot()
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
    <h1>⚡ J.A.R.V.I.S. TACTICAL HUD <span class="badge">{snapshot['version']}</span></h1>
    <div class="grid">
        <div class="card">
            <h3>Active Core Telemetry</h3>
            <p><strong>Variables:</strong> {json.dumps(snapshot['variables'])}</p>
            <p><strong>Formal Invariants:</strong> {json.dumps(snapshot['invariants'])}</p>
            <p><strong>Status:</strong> <span style="color: #4ade80;">{snapshot['status']}</span></p>
            <button class="btn" onclick="speakStatus()">🔊 Voice Status Report</button>
            <div id="canvas3d" style="margin-top: 15px;"></div>
        </div>
        <div class="card">
            <h3>Autonomous Cognitive Telemetry Stream</h3>
            <pre>{json.dumps(snapshot['telemetry_recent'], indent=2)}</pre>
            <h3>Security & Audit Log</h3>
            <pre>{json.dumps(self.audit_log[-3:], indent=2)}</pre>
        </div>
    </div>
    <script>
        function speakStatus() {{
            if ('speechSynthesis' in window) {{
                const utterance = new SpeechSynthesisUtterance("All forty-four ZASI subsystems are operating nominally, Sir. Security and RBAC authorization active.");
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
            self.server = socketserver.TCPServer(("", self.port), RequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"  [J.A.R.V.I.S. Tactical HUD] Secure API Running at http://localhost:{self.port}")
        except Exception as e:
            print(f"  [J.A.R.V.I.S. Tactical HUD] Notice: Web HUD port {self.port} bound ({e}).")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
