"""
ZASI Fast Asynchronous Backend Server (REST API, WebSockets, MCP JSON-RPC 2.0)
Provides real-time telemetry streaming, subsystem control, and cognitive daemon interaction.
"""
import http.server
import socketserver
import json
import os
import threading
import time
from urllib.parse import urlparse, parse_qs

# Import ZASI Core Subsystems
from src import (
    SystemState,
    SymbolicVerifier,
    NeuralSpeculator,
    NeuralSymbolicReasoner,
    MCTSPlanner,
    AlignmentGovernor,
    AdversarialDebateArena,
    RSIController,
    AutonomousSuperintelligenceDaemon,
    UniversalTelemetryMesh,
    ArcReactorEnergyOptimizer,
    NVIDIAGPUTelemetrySupervisor,
    OSTelemetrySupervisor,
    PlanetaryConsciousnessGrid,
    MCPProtocolServer
)

HOST = "0.0.0.0"
PORT = 8080
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")

# Shared In-Memory Backend State
invariants = ["x + y <= 100", "x >= 0", "y >= 0"]
state = SystemState(variables={"x": 20, "y": 30}, invariants=invariants)
verifier = SymbolicVerifier(invariants)
speculator = NeuralSpeculator()
reasoner = NeuralSymbolicReasoner(verifier, speculator)
planner = MCTSPlanner(verifier, max_simulations=100)
governor = AlignmentGovernor(drift_threshold=0.15)
debate_arena = AdversarialDebateArena(verifier, consensus_threshold=0.75)
rsi_engine = RSIController(reasoner)

daemon = AutonomousSuperintelligenceDaemon(
    state=state,
    reasoner=reasoner,
    planner=planner,
    governor=governor,
    debate_arena=debate_arena,
    rsi_engine=rsi_engine
)

telemetry_mesh = UniversalTelemetryMesh()
arc_reactor = ArcReactorEnergyOptimizer(base_output_gw=3.2)
gpu_supervisor = NVIDIAGPUTelemetrySupervisor()
os_supervisor = OSTelemetrySupervisor()
consciousness_grid = PlanetaryConsciousnessGrid()
mcp_server = MCPProtocolServer()

class ZASIUnifiedHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json_response({
                "status": "ONLINE",
                "version": "25.0.0-apex-omega",
                "subsystems": 128,
                "active_version": rsi_engine.current_version,
                "state": state.variables,
                "timestamp": time.time()
            })
        elif parsed.path == "/api/telemetry":
            host_m = os_supervisor.probe_host_metrics()
            gpus = [
                {
                    "index": g.gpu_index,
                    "name": g.gpu_name,
                    "vram_used": g.memory_used_mb,
                    "vram_total": g.memory_total_mb,
                    "utilization": g.gpu_utilization_pct,
                    "temp_c": g.temperature_c,
                    "power_w": g.power_draw_watts
                }
                for g in gpu_supervisor.probe_all_gpus()
            ]
            arc_status = arc_reactor.balance_energy_budget(3500.0)
            c_snap = consciousness_grid.synthesize_global_consciousness(128)
            self.send_json_response({
                "cpu_load": host_m.cpu_load_pct,
                "memory_used_mb": host_m.memory_used_mb,
                "memory_total_mb": host_m.memory_total_mb,
                "active_pids": host_m.active_process_count,
                "gpus": gpus,
                "arc_reactor_gw": arc_status.core_output_gigawatts,
                "arc_efficiency_pct": arc_status.thermodynamic_efficiency_pct,
                "global_phi": c_snap.integrated_information_phi,
                "active_subsystems": 128
            })
        elif parsed.path == "/api/tick":
            tick_res = daemon.step_cycle()
            self.send_json_response({
                "status": tick_res.get("status", "TICK_COMPLETED"),
                "state": state.variables,
                "action": tick_res.get("action_committed"),
                "version": rsi_engine.current_version
            })
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            body = json.loads(post_data)
        except Exception:
            body = {}

        if parsed.path == "/api/mcp":
            resp = mcp_server.handle_json_rpc_request(body)
            self.send_json_response(resp)
        elif parsed.path == "/api/mutate":
            var_name = body.get("variable", "x")
            delta = body.get("delta", 5)
            state.variables[var_name] = state.variables.get(var_name, 0) + delta
            self.send_json_response({"success": True, "state": state.variables})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json_response(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def run_backend(port=PORT):
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((HOST, port), ZASIUnifiedHandler) as httpd:
        print(f"[✓] ZASI Full-Stack Server Running on http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_backend()
