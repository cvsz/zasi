"""
ZASI Holographic J.A.R.V.I.S. HUD & Web Audio Voice Dashboard
"""
import http.server
import socketserver
import json
import threading
from typing import Dict, Any

class ZASIWebServer:
    def __init__(self, system_daemon, port: int = 8080):
        self.daemon = system_daemon
        self.port = port
        self.server = None
        self.thread = None

    def _get_system_snapshot(self) -> Dict[str, Any]:
        return {
            "version": self.daemon.rsi_engine.current_version,
            "variables": self.daemon.state.variables,
            "invariants": self.daemon.state.invariants,
            "telemetry_recent": self.daemon.telemetry_history[-5:] if self.daemon.telemetry_history else [],
            "status": "OPERATIONAL",
            "persona": "J.A.R.V.I.S."
        }

    def _generate_html_dashboard(self) -> str:
        snapshot = self._get_system_snapshot()
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>J.A.R.V.I.S. Holographic Tactical HUD</title>
    <meta http-equiv="refresh" content="3">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
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
        </div>
    </div>
    <script>
        function speakStatus() {{
            if ('speechSynthesis' in window) {{
                const text = "All systems operational, Sir. Core variables are running smoothly.";
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = 1.05;
                utterance.pitch = 0.95;
                window.speechSynthesis.speak(utterance);
            }}
        }}

        const container = document.getElementById('canvas3d');
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
        renderer.setSize(container.clientWidth, container.clientHeight);
        container.appendChild(renderer.domElement);

        const geometry = new THREE.TorusKnotGeometry(1.5, 0.4, 100, 16);
        const material = new THREE.MeshBasicMaterial({{ color: 0x00f0ff, wireframe: true }});
        const mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);
        camera.position.z = 4.5;

        function animate() {{
            requestAnimationFrame(animate);
            mesh.rotation.x += 0.01;
            mesh.rotation.y += 0.015;
            renderer.render(scene, camera);
        }}
        animate();
    </script>
</body>
</html>"""

    def start(self):
        handler_self = self
        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(handler_self._get_system_snapshot()).encode())
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(handler_self._generate_html_dashboard().encode())
            def log_message(self, format, *args):
                pass

        socketserver.TCPServer.allow_reuse_address = True
        self.server = socketserver.TCPServer(("", self.port), CustomHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"  [J.A.R.V.I.S. Tactical HUD] Running at http://localhost:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
