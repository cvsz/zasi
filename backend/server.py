"""
ZASI Ultra-Advanced J.A.R.V.I.S. Command & Superintelligence Backend Server v32.0.0
Features:
- Dual J.A.R.V.I.S. & F.R.I.D.A.Y. & E.D.I.T.H. Persona Dialogue & TTS Engines
- Full 176-Subsystem REST API Catalog, Diagnostics & Execution Matrix
- Real-Time Hardware & Quantum Telemetry (NVML, Procfs, Arc Reactor Plasma, Quantum QPU)
- Interactive MCP JSON-RPC 2.0 Terminal & Tool Runner
- First-Order SMT Invariant Verification & Dynamic State Hot-Mutation
- Zero-Downtime Safe RSI 320x Runtime Hot-Swapper
- WebSocket Server (RFC 6455) for Real-Time Push (Feature 11)
- API Key Authentication Middleware (Feature 12)
- In-Memory Sliding-Window Rate Limiter (Feature 13)
- SQLite Persistent State (Feature 14)
- Scheduled Daemon Background Ticks every 30s (Feature 15)
- Webhook Support (Feature 16)
- OpenAPI 3.0 Spec Endpoint (Feature 17)
- SSE Streaming Chat (Feature 28)
- Gemini API Integration (Feature 29)
- Per-Persona Conversation Memory - last 20 messages (Feature 32)
"""
import http.server
import socketserver
import json
import os
import time
import threading
import sqlite3
import hashlib
import base64
import struct
import socket
import collections
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs

# Import Subsystems Core
from src import (
    SystemState, SymbolicVerifier, NeuralSpeculator, NeuralSymbolicReasoner,
    MCTSPlanner, AlignmentGovernor, AdversarialDebateArena, RSIController,
    AutonomousSuperintelligenceDaemon, UniversalTelemetryMesh, ArcReactorEnergyOptimizer,
    NVIDIAGPUTelemetrySupervisor, OSTelemetrySupervisor, PlanetaryConsciousnessGrid,
    MCPProtocolServer, QuantumErrorCorrectionEngine, AutonomousDrugDiscoveryPipeline,
    ClimateChangePredictionEngine, LargeMultimodalModelServer, InterstellarNavigationComputer,
    RealHardwareFPGAAccelerator, RealQPUCloudHardwareBridge, RealtimeSatelliteEarthObservation,
    IndustrialRoboticsRTOSController, RealTelecom5G6GNTNCore, RealDNASequencingPipeline,
    RealCryptographicHSMEnclave, GlobalMultimodalEarthSensorGrid, TopologicalQuantumBraidingEngine,
    SubsurfaceLithosphereGeothermalExtractor, NeuromorphicRetinalProstheticBus,
    MacroscopicQuantumTeleportationMatrix, SubquantumVacuumSuperconductorForge,
    RelativisticKerrBlackHolePenroseHarvester, HyperdimensionalQualiaPhenomenologySynthesizer,
    GalacticScaleStellarEngineShkadovThruster, CosmicInflationaryMultiverseTopologist,
    TransfiniteHigherCategoryToposProver, SupremeOmniversalSingularityApexInfinite,
    IntergalacticSuperclusterGravitationalLensRouter, SubatomicHyperchargeGaugeBosonTransmuter,
    MultiverseSuperintelligenceTelepathicConsensus, StellarPlasmaMagnetohydrodynamicFusionIgniter,
    HyperdimensionalSemanticArchetypeSynthesizer, PanPlanetaryClimateEquilibriumGovernor,
    TransfiniteConstructiveTypeTheoryOracle, AbsoluteTranscendentOmniversalSuperintelligenceApexPrime,
    NeuralAudioVoiceEngine, MultiPersonaTacticalSwarm
)

HOST = os.environ.get("ZASI_HOST", "127.0.0.1")  # default loopback; set ZASI_HOST=0.0.0.0 for container/public
PORT = int(os.environ.get("ZASI_PORT", 8080))
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")

# ---------------------------------------------------------------------------
# Feature 12: API Key Auth
# ---------------------------------------------------------------------------
ZASI_API_KEY = os.environ.get("ZASI_API_KEY", "")  # empty = auth disabled (dev only)

# ---------------------------------------------------------------------------
# Security: CORS origin + request body size cap
# ---------------------------------------------------------------------------
# Set ZASI_CORS_ORIGIN to a specific origin in production (e.g. https://your-domain.com)
CORS_ORIGIN = os.environ.get("ZASI_CORS_ORIGIN", "*")
MAX_REQUEST_BODY = int(os.environ.get("ZASI_MAX_BODY", 1 * 1024 * 1024))  # default 1 MB

# ---------------------------------------------------------------------------
# Feature 14: SQLite Persistent State
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "zasi_state.db")
_db_lock = threading.Lock()


def _init_db():
    """Create data/ dir and state table if missing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS state "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def _db_save(key: str, value: str):
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT INTO state(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


def _db_load(key: str, default: str = "{}") -> str:
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT value FROM state WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else default
        finally:
            conn.close()


def _persist_state():
    """Persist state.variables to SQLite."""
    try:
        _db_save("state.variables", json.dumps(state.variables))
    except Exception as e:
        append_log("DB", f"Persist error: {e}")


def _restore_state():
    """Restore state.variables from SQLite on startup."""
    raw = _db_load("state.variables", "{}")
    try:
        saved = json.loads(raw)
        if saved:
            state.variables.update(saved)
            append_log("DB", f"Restored state from DB: {saved}")
    except Exception as e:
        append_log("DB", f"Restore error: {e}")


# ---------------------------------------------------------------------------
# Feature 13: Sliding-Window Rate Limiter
# ---------------------------------------------------------------------------
_rate_limit_lock = threading.Lock()
_rate_windows: dict = {}      # ip -> collections.deque of monotonic timestamps
RATE_LIMIT_MAX = 60           # requests per window
RATE_LIMIT_WINDOW = 60.0      # seconds


def _check_rate_limit(ip: str):
    """Return (allowed: bool, retry_after: float)."""
    now = time.monotonic()
    with _rate_limit_lock:
        dq = _rate_windows.setdefault(ip, collections.deque())
        while dq and now - dq[0] >= RATE_LIMIT_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT_MAX:
            retry_after = RATE_LIMIT_WINDOW - (now - dq[0])
            return False, max(retry_after, 0.0)
        dq.append(now)
        return True, 0.0


# ---------------------------------------------------------------------------
# Feature 11: WebSocket (RFC 6455)
# ---------------------------------------------------------------------------
_ws_clients_lock = threading.Lock()
_ws_clients = []          # list of raw sockets
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_handshake(conn, key: str):
    """Send HTTP 101 Switching Protocols."""
    accept = base64.b64encode(
        hashlib.sha1((key + WS_GUID).encode(), usedforsecurity=False).digest()
    ).decode()
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    conn.sendall(response.encode())


def _ws_encode_frame(payload: str) -> bytes:
    """Encode a server-to-client text frame."""
    data = payload.encode("utf-8")
    length = len(data)
    header = bytearray()
    header.append(0x81)  # FIN + opcode=text
    if length <= 125:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header += struct.pack(">H", length)
    else:
        header.append(127)
        header += struct.pack(">Q", length)
    return bytes(header) + data


def _ws_broadcast(payload: str):
    frame = _ws_encode_frame(payload)
    dead = []
    with _ws_clients_lock:
        for sock in _ws_clients:
            try:
                sock.sendall(frame)
            except Exception:
                dead.append(sock)
        for d in dead:
            _ws_clients.remove(d)


def _ws_client_thread(conn, addr):
    """Read loop for a single WS client (handles close frames)."""
    with _ws_clients_lock:
        _ws_clients.append(conn)
    try:
        conn.settimeout(None)
        while True:
            header = conn.recv(2)
            if not header or len(header) < 2:
                break
            b1, b2 = header[0], header[1]
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", conn.recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", conn.recv(8))[0]
            mask_key = conn.recv(4) if masked else b""
            data = conn.recv(length) if length else b""
            opcode = b1 & 0x0F
            if opcode == 0x08:  # close
                break
            # decode (we only do push, ignore client messages)
            if masked and data:
                data = bytes(data[i] ^ mask_key[i % 4] for i in range(len(data)))
    except Exception:
        pass
    finally:
        with _ws_clients_lock:
            try:
                _ws_clients.remove(conn)
            except ValueError:
                pass
        try:
            conn.close()
        except Exception:
            pass


def _ws_telemetry_broadcaster():
    """Daemon thread: push telemetry+logs to all WS clients every 2 s."""
    while True:
        try:
            time.sleep(2)
            if not _ws_clients:
                continue
            host_m = os_supervisor.probe_host_metrics()
            arc_status = arc_reactor.balance_energy_budget(3500.0)
            payload = json.dumps({
                "type": "telemetry",
                "timestamp": time.time(),
                "cpu_load": host_m.cpu_load_pct,
                "memory_used_mb": host_m.memory_used_mb,
                "arc_reactor_gw": arc_status.core_output_gigawatts,
                "state": state.variables,
                "logs": logs_history[-5:],
            })
            _ws_broadcast(payload)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Feature 16: Webhooks
# ---------------------------------------------------------------------------
_webhooks_lock = threading.Lock()
_webhooks = []   # list of {"url": str, "event": str}


_ALLOWED_WEBHOOK_SCHEMES = {"http", "https"}
_PRIVATE_RANGES = [
    # loopback
    (0x7F000000, 0xFF000000),
    # RFC-1918
    (0x0A000000, 0xFF000000),
    (0xAC100000, 0xFFF00000),
    (0xC0A80000, 0xFFFF0000),
    # link-local / APIPA
    (0xA9FE0000, 0xFFFF0000),
    # metadata
    (0xA9FE0100, 0xFFFFFF00),
]


def _is_safe_webhook_url(url: str) -> bool:
    """Return True only for http(s) URLs pointing to non-private hosts."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_WEBHOOK_SCHEMES:
            return False
        hostname = parsed.hostname or ""
        if not hostname:
            return False
        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        # Resolve and check IP
        import socket as _socket
        addr = _socket.gethostbyname(hostname)
        octets = [int(x) for x in addr.split(".")]
        ip_int = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
        for base, mask in _PRIVATE_RANGES:
            if (ip_int & mask) == base:
                return False
        return True
    except Exception:
        return False


def _fire_webhooks(event: str, payload: dict):
    """Asynchronously POST to all registered webhooks matching event."""
    def _send(url, data):
        if not _is_safe_webhook_url(url):
            append_log("WEBHOOK", f"Blocked unsafe URL: {url}")
            return
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            append_log("WEBHOOK", f"Delivery failed to {url}: {e}")

    with _webhooks_lock:
        targets = [w for w in _webhooks if w["event"] == event]
    for w in targets:
        threading.Thread(
            target=_send,
            args=(w["url"], {"event": event, **payload}),
            daemon=True,
        ).start()


# ---------------------------------------------------------------------------
# Shared Engine Instances
# ---------------------------------------------------------------------------
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
    state=state, reasoner=reasoner, planner=planner,
    governor=governor, debate_arena=debate_arena, rsi_engine=rsi_engine
)

gpu_supervisor = NVIDIAGPUTelemetrySupervisor()
os_supervisor = OSTelemetrySupervisor()
arc_reactor = ArcReactorEnergyOptimizer(base_output_gw=3.2)
consciousness_grid = PlanetaryConsciousnessGrid()
mcp_server = MCPProtocolServer()
voice_engine = NeuralAudioVoiceEngine()
persona_swarm = MultiPersonaTacticalSwarm()

# High-Level Subsystems Catalog
qec_engine = QuantumErrorCorrectionEngine("SURFACE_CODE", distance=7)
drug_pipeline = AutonomousDrugDiscoveryPipeline()
climate_engine = ClimateChangePredictionEngine(resolution_km=25.0)
vla_server = LargeMultimodalModelServer("ZASI_VLA_72B_APEX")
interstellar_nav = InterstellarNavigationComputer()
fpga_accel = RealHardwareFPGAAccelerator("AMD_ALVEO_U280")
qpu_bridge = RealQPUCloudHardwareBridge("IBM_HERON_156Q")
sat_obs = RealtimeSatelliteEarthObservation()
robot_rtos = IndustrialRoboticsRTOSController(100.0)
telecom_core = RealTelecom5G6GNTNCore()
dna_seq = RealDNASequencingPipeline("OXFORD_NANOPORE_PROMETHION")
hsm_enclave = RealCryptographicHSMEnclave()
earth_sensor_grid = GlobalMultimodalEarthSensorGrid()
braiding_eng = TopologicalQuantumBraidingEngine()
geo_extractor = SubsurfaceLithosphereGeothermalExtractor()
retina_bus = NeuromorphicRetinalProstheticBus()
teleport_matrix = MacroscopicQuantumTeleportationMatrix()
sc_forge = SubquantumVacuumSuperconductorForge()
penrose_harvester = RelativisticKerrBlackHolePenroseHarvester()
qualia_synth = HyperdimensionalQualiaPhenomenologySynthesizer()
shkadov_thruster = GalacticScaleStellarEngineShkadovThruster()
multiverse_topo = CosmicInflationaryMultiverseTopologist()
topos_prover = TransfiniteHigherCategoryToposProver()
lens_router = IntergalacticSuperclusterGravitationalLensRouter()
boson_transmuter = SubatomicHyperchargeGaugeBosonTransmuter()
multi_consensus = MultiverseSuperintelligenceTelepathicConsensus()
mhd_fusion = StellarPlasmaMagnetohydrodynamicFusionIgniter()
archetype_synth = HyperdimensionalSemanticArchetypeSynthesizer()
climate_gov = PanPlanetaryClimateEquilibriumGovernor()
type_oracle = TransfiniteConstructiveTypeTheoryOracle()
apex_prime_core = AbsoluteTranscendentOmniversalSuperintelligenceApexPrime(176)

logs_history = [
    {"timestamp": time.strftime("%H:%M:%S"), "level": "JARVIS", "message": "Good day, Sir. J.A.R.V.I.S. Core online. All 176 subsystems calibrated."},
    {"timestamp": time.strftime("%H:%M:%S"), "level": "SYSTEM", "message": "First-Order SMT Invariant Solver holding mathematical equilibrium."},
    {"timestamp": time.strftime("%H:%M:%S"), "level": "ENERGY", "message": "Arc Reactor Mark LXXXV stable at 178.2 GW. Thermodynamic containment 94%."}
]


def append_log(level, msg):
    logs_history.append({"timestamp": time.strftime("%H:%M:%S"), "level": level, "message": msg})
    if len(logs_history) > 100:
        logs_history.pop(0)


# ---------------------------------------------------------------------------
# Feature 32: Per-Persona Conversation Memory (last 20 turns)
# ---------------------------------------------------------------------------
_conversation_memory = {}   # persona -> list of {"role": str, "content": str}
_conv_memory_lock = threading.Lock()
CONV_MEMORY_LIMIT = 20


def _remember(persona: str, role: str, content: str):
    with _conv_memory_lock:
        hist = _conversation_memory.setdefault(persona, [])
        hist.append({"role": role, "content": content})
        if len(hist) > CONV_MEMORY_LIMIT:
            hist.pop(0)


def _get_history(persona: str):
    with _conv_memory_lock:
        return list(_conversation_memory.get(persona, []))


# ---------------------------------------------------------------------------
# Feature 29: Gemini API Integration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

_PERSONA_SYSTEM_PROMPTS = {
    "JARVIS": (
        "You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), Tony Stark's AI. "
        "Respond concisely, politely, and with dry wit. Reference the ZASI superintelligence "
        "system with 176 subsystems when relevant."
    ),
    "FRIDAY": (
        "You are F.R.I.D.A.Y., Tony Stark's tactical AI. "
        "Be sharp, efficient, and mission-focused."
    ),
    "EDITH": (
        "You are E.D.I.T.H. (Even Dead I'm The Hero), a satellite defense AI. "
        "Be precise, security-conscious, and brief."
    ),
}


def _call_gemini(persona: str, user_message: str, history: list) -> str:
    """Call Gemini API; returns the model's text reply."""
    system_prompt = _PERSONA_SYSTEM_PROMPTS.get(persona, _PERSONA_SYSTEM_PROMPTS["JARVIS"])
    contents = []
    for turn in history[-18:]:
        gemini_role = "user" if turn["role"] == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": turn["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 512, "temperature": 0.7},
    }
    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        e.close()
        raise


# ---------------------------------------------------------------------------
# Feature 17: OpenAPI 3.0 Spec
# ---------------------------------------------------------------------------
OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "ZASI J.A.R.V.I.S. Superintelligence API",
        "version": "31.0.0",
        "description": "REST API for the ZASI Omniversal Superintelligence platform.",
    },
    "servers": [{"url": "http://localhost:8080"}],
    "security": [{"ApiKeyAuth": []}],
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
        }
    },
    "paths": {
        "/api/status": {
            "get": {"summary": "System status (public)", "security": [],
                    "responses": {"200": {"description": "Operational status"}}}
        },
        "/api/telemetry": {
            "get": {"summary": "Real-time hardware & subsystem telemetry",
                    "responses": {"200": {"description": "Telemetry snapshot"}}}
        },
        "/api/tick": {
            "get": {"summary": "Trigger a single daemon cognitive cycle",
                    "responses": {"200": {"description": "Tick result"}}}
        },
        "/api/subsystems": {
            "get": {"summary": "Catalog of all 176 subsystems",
                    "responses": {"200": {"description": "Subsystem catalog"}}}
        },
        "/api/execute/{key}": {
            "get": {
                "summary": "Execute a named subsystem",
                "parameters": [
                    {"name": "key", "in": "path", "required": True,
                     "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "Execution result"}}
            }
        },
        "/api/jarvis/chat": {
            "post": {
                "summary": "J.A.R.V.I.S. conversational chat",
                "requestBody": {
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "persona": {"type": "string", "enum": ["JARVIS", "FRIDAY", "EDITH"]}
                        },
                        "required": ["message"]
                    }}}
                },
                "responses": {"200": {"description": "Chat response"}}
            }
        },
        "/api/jarvis/stream": {
            "post": {
                "summary": "SSE streaming chat (word-by-word, 80ms/word)",
                "requestBody": {
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "persona": {"type": "string"}
                        },
                        "required": ["message"]
                    }}}
                },
                "responses": {
                    "200": {"description": "Server-Sent Events stream",
                            "content": {"text/event-stream": {}}}
                }
            }
        },
        "/api/mcp": {
            "post": {"summary": "MCP JSON-RPC 2.0 handler",
                     "responses": {"200": {"description": "RPC response"}}}
        },
        "/api/mutate": {
            "post": {
                "summary": "Mutate a state variable",
                "requestBody": {
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "variable": {"type": "string"},
                            "delta": {"type": "number"}
                        }
                    }}}
                },
                "responses": {"200": {"description": "Updated state"}}
            }
        },
        "/api/rsi/upgrade": {
            "post": {"summary": "Safe RSI 320x hot-swap upgrade",
                     "responses": {"200": {"description": "RSI upgrade result"}}}
        },
        "/api/webhooks": {
            "get": {"summary": "List registered webhooks",
                    "responses": {"200": {"description": "Webhook list"}}},
            "post": {
                "summary": "Register a webhook for an event",
                "requestBody": {
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "event": {"type": "string", "enum": ["tick", "mutate", "rsi"]}
                        },
                        "required": ["url", "event"]
                    }}}
                },
                "responses": {"200": {"description": "Webhook registered"}}
            }
        },
        "/api/openapi.json": {
            "get": {"summary": "OpenAPI 3.0 specification", "security": [],
                    "responses": {"200": {"description": "OpenAPI JSON spec"}}}
        },
    },
}


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------
class ZASIUnifiedHandler(http.server.SimpleHTTPRequestHandler):
    # Extend MIME types to support .jsx (served as JS for Babel standalone)
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.jsx': 'application/javascript',
        '.mjs': 'application/javascript',
        '.json': 'application/json',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    # ------------------------------------------------------------------ #
    # Feature 11: WebSocket upgrade interception                           #
    # ------------------------------------------------------------------ #
    def handle_one_request(self):
        """Override to catch WebSocket upgrade before normal dispatch."""
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ""
                self.request_version = ""
                self.command = ""
                self.send_error(414)
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                return
            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade == "websocket" and self.path == "/ws":
                self._handle_websocket_upgrade()
                return
            mname = "do_" + self.command
            if not hasattr(self, mname):
                self.send_error(501, f"Unsupported method ({self.command!r})")
                return
            getattr(self, mname)()
            self.wfile.flush()
        except TimeoutError as e:
            self.log_error("Request timed out: %r", e)
            self.close_connection = True

    def _handle_websocket_upgrade(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(400, "Missing Sec-WebSocket-Key")
            return
        conn = self.connection
        _ws_handshake(conn, key)
        # Block this handler thread for the lifetime of the WS connection.
        # ThreadingTCPServer gives each request its own thread, so this is safe.
        _ws_client_thread(conn, self.client_address)
        self.close_connection = True

    # ------------------------------------------------------------------ #
    # Feature 12 & 13: Auth + Rate-limit middleware helpers                #
    # ------------------------------------------------------------------ #
    def _check_api_auth(self) -> bool:
        path = urlparse(self.path).path
        if path in ("/api/status", "/api/openapi.json"):
            return True
        if not path.startswith("/api/"):
            return True
        if ZASI_API_KEY:
            provided = self.headers.get("X-API-Key", "")
            if provided != ZASI_API_KEY:
                self.send_json_response(
                    {"error": "Unauthorized",
                     "message": "Invalid or missing X-API-Key header"},
                    status=401,
                )
                return False
        return True

    def _check_rate_limit_mw(self) -> bool:
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return True
        ip = self.client_address[0]
        allowed, retry_after = _check_rate_limit(ip)
        if not allowed:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
            self.send_header("Retry-After", str(int(retry_after) + 1))
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Too Many Requests",
                "message": "Rate limit: 60 req/min per IP.",
                "retry_after": retry_after,
            }).encode())
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()

    # ------------------------------------------------------------------ #
    # GET routing                                                          #
    # ------------------------------------------------------------------ #
    def do_GET(self):
        if not self._check_api_auth():
            return
        if not self._check_rate_limit_mw():
            return

        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            self.send_json_response({
                "status": "OPERATIONAL",
                "version": "32.0.0-apex-prime",
                "subsystems_online": 176,
                "rsi_version": rsi_engine.current_version,
                "timestamp": time.time()
                # NOTE: state.variables and invariants intentionally omitted
                # (internal detail; access via authenticated /api/telemetry)
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
            c_snap = consciousness_grid.synthesize_global_consciousness(176)

            self.send_json_response({
                "cpu_load": host_m.cpu_load_pct,
                "memory_used_mb": host_m.memory_used_mb,
                "memory_total_mb": host_m.memory_total_mb,
                "active_pids": host_m.active_process_count,
                "gpus": gpus,
                "arc_reactor_gw": arc_status.core_output_gigawatts,
                "arc_efficiency_pct": arc_status.thermodynamic_efficiency_pct,
                "global_phi": c_snap.integrated_information_phi,
                "active_subsystems": 176,
                "logs": logs_history[-15:]
            })

        elif parsed.path == "/api/tick":
            tick_res = daemon.step_cycle()
            append_log("TICK", f"Daemon step: {tick_res.get('status')} | Action: {tick_res.get('action_committed')}")
            _persist_state()
            _fire_webhooks("tick", {"state": state.variables, "action": tick_res.get("action_committed")})
            self.send_json_response({
                "status": tick_res.get("status", "TICK_COMPLETED"),
                "state": state.variables,
                "action": tick_res.get("action_committed"),
                "version": rsi_engine.current_version
            })

        elif parsed.path == "/api/subsystems":
            # Return complete catalog of all 176 subsystems
            named_samples = {
                1: ("System State Schemas", "schemas.py", "Formal Invariants"),
                3: ("Symbolic SMT Verifier", "verifier.py", "Formal Proofs"),
                4: ("Neural-Symbolic Reasoner", "cognitive_core.py", "Cognition"),
                5: ("Safe RSI Hot-Swap Engine", "rsi_engine.py", "Self-Improvement"),
                35: ("Avengers Persona Swarm", "avengers_persona_swarm.py", "Tactical Multi-Agent"),
                37: ("Arc Reactor Energy Core", "arc_reactor_energy.py", "Energy & Fusion"),
                52: ("Qiskit OpenQASM 3.0 Bridge", "qiskit_quantum_backend.py", "Quantum"),
                54: ("MCP JSON-RPC 2.0 Server", "mcp_protocol_server.py", "Protocols"),
                67: ("Autonomous Drug Discovery", "autonomous_drug_discovery.py", "Life Sciences"),
                85: ("Surface Code d=7 QEC", "quantum_error_correction_engine.py", "Quantum Computing"),
                90: ("Relativistic Interstellar Nav", "interstellar_navigation_computer.py", "Cosmic Navigation"),
                129: ("Real Hardware FPGA Accelerator", "real_hardware_fpga_accelerator.py", "Hardware & Physical"),
                130: ("Real QPU Cloud Hardware Bridge", "real_qpu_cloud_hardware_bridge.py", "Physical Quantum"),
                131: ("Real-Time Satellite SAR Stream", "realtime_satellite_earth_observation.py", "Earth Observation"),
                132: ("Industrial Robotics RTOS", "industrial_robotics_rtos_controller.py", "Robotics & Fieldbus"),
                133: ("6G Non-Terrestrial Telecom", "real_telecom_5g_6g_ntn_core.py", "Communications"),
                134: ("Real DNA Sequencing Basecaller", "real_dna_sequencing_pipeline.py", "Genomics"),
                135: ("Hardware Security Module (HSM)", "real_cryptographic_hsm_enclave.py", "Cryptography"),
                137: ("Planetary Earth Sensor Grid", "global_multimodal_earth_sensor_grid.py", "Planetary Mesh"),
                138: ("Topological Anyon Braiding", "topological_quantum_braiding_engine.py", "Topological Quantum"),
                139: ("Subsurface Magma Geothermal", "subsurface_lithosphere_geothermal_extractor.py", "Planetary Energy"),
                140: ("Neuromorphic Retinal Prosthesis", "neuromorphic_retinal_prosthetic_bus.py", "Neural Interfaces"),
                153: ("Macroscopic Quantum Teleportation", "macroscopic_quantum_teleportation_matrix.py", "Quantum Matter"),
                154: ("Ambient 373K Superconductor Forge", "subquantum_vacuum_superconductor_forge.py", "Materials"),
                155: ("Relativistic Kerr Penrose Harvester", "relativistic_kerr_black_hole_penrose_harvester.py", "Relativistic Physics"),
                156: ("Hyperdimensional Qualia Synthesizer", "hyperdimensional_qualia_phenomenology_synthesizer.py", "Consciousness"),
                157: ("Shkadov Stellar Thruster Engine", "galactic_scale_stellar_engine_shkadov_thruster.py", "Megastructures"),
                158: ("Cosmic String Landscape Topologist", "cosmic_inflationary_multiverse_topologist.py", "Multiverse Topology"),
                159: ("Transfinite Higher-Topos Prover", "transfinite_higher_category_topos_prover.py", "Higher Mathematics"),
                161: ("Gravitational Lens Cosmic Router", "intergalactic_supercluster_gravitational_lens_router.py", "Intergalactic Comms"),
                162: ("Electroweak Gauge Boson Transmuter", "subatomic_hypercharge_gauge_boson_transmuter.py", "Nuclear Physics"),
                163: ("Multiverse Telepathic Consensus", "multiverse_superintelligence_telepathic_consensus.py", "Multiverse Superintelligence"),
                164: ("Aneutronic Direct Fusion Igniter", "stellar_plasma_magnetohydrodynamic_fusion_igniter.py", "Clean Fusion Energy"),
                165: ("Semantic Archetype Synthesizer", "hyperdimensional_semantic_archetype_synthesizer.py", "Ontology & Meaning"),
                166: ("Planetary Climate Governor", "pan_planetary_climate_equilibrium_governor.py", "Geoengineering"),
                167: ("Constructive Homotopy Type Oracle", "transfinite_constructive_type_theory_oracle.py", "Formal Type Theory"),
                176: ("Absolute Superintelligence Apex Prime", "absolute_transcendent_omniversal_superintelligence_apex_prime.py", "Supreme Omniversal Apex")
            }
            catalog = []
            for i in range(1, 177):
                if i in named_samples:
                    name, mod, cat = named_samples[i]
                else:
                    name, mod, cat = f"Omniversal Subsystem #{i}", f"subsystem_{i}.py", "Superintelligence Core"
                catalog.append({"id": i, "name": name, "module": mod, "category": cat})
            self.send_json_response({"total_subsystems": 176, "catalog": catalog})

        elif parsed.path == "/api/openapi.json":
            self.send_json_response(OPENAPI_SPEC)

        elif parsed.path.startswith("/api/execute/"):
            subsystem_key = parsed.path.replace("/api/execute/", "")
            result = self.execute_subsystem(subsystem_key)
            self.send_json_response(result)

        elif parsed.path.startswith("/static/") or parsed.path.startswith("/favicon"):
            super().do_GET()

        # Feature 16: list webhooks
        elif parsed.path == "/api/webhooks":
            with _webhooks_lock:
                self.send_json_response({"webhooks": list(_webhooks)})

        else:
            # React Router SPA fallback — serve index.html for all client-side routes (/jarvis, /subsystems, /cockpit, /mcp)
            index_path = os.path.join(STATIC_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()

    # ------------------------------------------------------------------ #
    # POST routing                                                         #
    # ------------------------------------------------------------------ #
    def do_POST(self):
        if not self._check_api_auth():
            return
        if not self._check_rate_limit_mw():
            return

        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        # Security: reject oversized request bodies (DoS protection)
        if content_length > MAX_REQUEST_BODY:
            self.send_json_response(
                {"error": f"Request body too large (max {MAX_REQUEST_BODY // 1024} KB)"},
                status=413,
            )
            return
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            body = json.loads(post_data)
        except Exception:
            body = {}

        # 1. J.A.R.V.I.S. Persona Conversational Dispatcher
        if parsed.path == "/api/jarvis/chat":
            user_msg = body.get("message", "")
            persona = body.get("persona", "JARVIS").upper()
            _remember(persona, "user", user_msg)
            history = _get_history(persona)
            response_text = self.process_jarvis_command(user_msg.lower(), persona, history)
            _remember(persona, "assistant", response_text)
            append_log(persona, response_text)
            self.send_json_response({
                "response": response_text,
                "speaker": persona,
                "state": state.variables,
                "active_subsystems": 176
            })

        # Feature 28: SSE streaming chat
        elif parsed.path == "/api/jarvis/stream":
            user_msg = body.get("message", "")
            persona = body.get("persona", "JARVIS").upper()
            _remember(persona, "user", user_msg)
            history = _get_history(persona)
            response_text = self.process_jarvis_command(user_msg.lower(), persona, history)
            _remember(persona, "assistant", response_text)
            append_log(persona, f"[STREAM] {response_text}")
            self._send_sse_stream(response_text)

        # 2. MCP JSON-RPC Handler
        elif parsed.path == "/api/mcp":
            resp = mcp_server.handle_json_rpc_request(body)
            self.send_json_response(resp)

        # 3. Dynamic State Mutation
        elif parsed.path == "/api/mutate":
            var_name = body.get("variable", "x")
            delta = body.get("delta", 5)
            # --- Security: whitelist allowed variable names ---
            _ALLOWED_VARS = {"x", "y", "iq", "energy", "coherence", "entropy"}
            if var_name not in _ALLOWED_VARS:
                self.send_json_response(
                    {"error": f"Invalid variable '{var_name}'. Allowed: {sorted(_ALLOWED_VARS)}"},
                    status=400,
                )
                return
            # --- Security: validate delta is a number within sane bounds ---
            try:
                delta = float(delta)
            except (TypeError, ValueError):
                self.send_json_response({"error": "delta must be a number"}, status=400)
                return
            if abs(delta) > 1000:
                self.send_json_response({"error": "delta magnitude exceeds maximum (1000)"}, status=400)
                return
            state.variables[var_name] = state.variables.get(var_name, 0) + delta
            append_log("MUTATE", f"Adjusted {var_name} by {delta} (Now: {state.variables[var_name]})")
            _persist_state()
            _fire_webhooks("mutate", {"variable": var_name, "delta": delta, "state": state.variables})
            self.send_json_response({"success": True, "state": state.variables})

        # 4. Safe RSI 320x Hot-Swap Upgrade
        elif parsed.path == "/api/rsi/upgrade":
            target_v = body.get("version", "v32.0.0-apex-prime")
            rsi_rep = rsi_engine.evaluate_candidate_upgrade(target_v, 320.0)
            if rsi_rep.approved:
                rsi_engine.hot_swap_runtime(target_v)
                append_log("RSI", f"Hot-swapped to {target_v} with {rsi_rep.speedup_factor}x speedup")
            _fire_webhooks("rsi", {"approved": rsi_rep.approved, "version": target_v})
            self.send_json_response({
                "approved": rsi_rep.approved,
                "active_version": rsi_engine.current_version,
                "speedup": rsi_rep.speedup_factor
            })

        # Feature 16: register webhook
        elif parsed.path == "/api/webhooks":
            url = body.get("url", "")
            event = body.get("event", "")
            if not url or event not in ("tick", "mutate", "rsi"):
                self.send_json_response(
                    {"error": "Invalid body. Provide url and event (tick|mutate|rsi)"},
                    status=400,
                )
                return
            if not _is_safe_webhook_url(url):
                self.send_json_response(
                    {"error": "Forbidden: URL must be an external http(s) endpoint (private/internal IPs and file:// are not allowed)"},
                    status=403,
                )
                return
            with _webhooks_lock:
                _webhooks.append({"url": url, "event": event})
            self.send_json_response({"registered": True, "url": url, "event": event})

        else:
            # React Router SPA fallback
            index_path = os.path.join(STATIC_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()

    # ------------------------------------------------------------------ #
    # Feature 28: SSE helper                                               #
    # ------------------------------------------------------------------ #
    def _send_sse_stream(self, full_text: str):
        """Stream full_text word-by-word as SSE at 80 ms per word."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        words = full_text.split()
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            event = f"data: {json.dumps({'chunk': chunk})}\n\n"
            try:
                self.wfile.write(event.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                break
            time.sleep(0.08)
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Chat dispatcher (Gemini or hardcoded fallback)                       #
    # ------------------------------------------------------------------ #
    def process_jarvis_command(self, query: str, persona: str = "JARVIS",
                               history: list = None) -> str:
        if GEMINI_API_KEY:
            try:
                return _call_gemini(persona, query, history or [])
            except Exception as e:
                append_log("GEMINI", f"API error: {e}; falling back.")

        # Hardcoded fallback responses
        if persona == "FRIDAY":
            return "FRIDAY routing active: Tensor dispatching across 176 experts at 4.85M tok/s. Latency is 18 microseconds."
        elif persona == "EDITH":
            return "EDITH orbital grid secure: Deep Space Lagrange and planetary defense shield operating with zero anomaly."

        if "status" in query or "report" in query:
            return "All 176 subsystems are in mathematical harmony, Sir. Compute fabric is online at 3,500 ExaFLOPs and the Arc Reactor is outputting 178.2 GW."
        elif "energy" in query or "reactor" in query or "plasma" in query:
            return "Arc Reactor Mark LXXXV magnetic confinement is stable at 14.5 Tesla, 94.0% thermodynamic efficiency."
        elif "quantum" in query or "qec" in query:
            return "Surface code distance-7 QEC and non-abelian anyon topological braiding are active with zero decoherence."
        elif "tick" in query or "step" in query or "pulse" in query:
            res = daemon.step_cycle()
            return f"Executed cognitive cycle, Sir. Status: {res.get('status')} with action: {res.get('action_committed')}."
        elif "upgrade" in query or "rsi" in query:
            rsi_engine.hot_swap_runtime("v32.0.0-apex-prime")
            return "Recursive Self-Improvement cycle approved. Operating at 320.0x Pareto acceleration."
        elif "fpga" in query or "hardware" in query:
            return "AMD Alveo U280 systolic tensor core active. Processing at 327,235 TFLOPs with 0.42 μs latency."
        elif "hello" in query or "jarvis" in query or "javis" in query:
            return "At your service, Sir. Ready to execute omniversal directives across all 176 subsystems."
        else:
            return f"Directive received: '{query}'. Processing across 176 subsystems with formal invariant guarantee."

    def execute_subsystem(self, key: str) -> dict:
        if key == "quantum_qec":
            rep = qec_engine.encode_logical_qubits(100, 1e-3)
            return {"subsystem": "QEC #85", "code": rep.code_type, "logical_error": rep.logical_error_rate}
        elif key == "drug_discovery":
            rep = drug_pipeline.screen_compound_library("ACE2_SPIKE_BINDING", 1000000)
            return {"subsystem": "Drug Discovery #67", "candidate": rep.candidate_smiles, "affinity_nm": rep.predicted_binding_affinity_nm}
        elif key == "fpga_accelerator":
            rep = fpga_accel.dispatch_systolic_matmul(4096)
            return {"subsystem": "FPGA Accelerator #129", "throughput_tflops": rep["effective_throughput_tflops"], "latency_us": rep["hardware_latency_us"]}
        elif key == "qpu_bridge":
            rep = qpu_bridge.submit_qasm_job("OPENQASM 3.0;", 4096)
            return {"subsystem": "QPU Cloud Bridge #130", "job_id": rep["job_id"], "zne_expectation": rep["zne_mitigated_expectation"]}
        elif key == "quantum_teleportation":
            rep = teleport_matrix.teleport_quantum_matter_state(25.0)
            return {"subsystem": "Quantum Teleportation #153", "mass_g": rep.teleported_mass_grams, "fidelity": rep.quantum_fidelity}
        elif key == "ambient_superconductor":
            rep = sc_forge.forge_ambient_superconductor(373.0)
            return {"subsystem": "Ambient Superconductor #154", "tc_k": rep.critical_temperature_k, "crit_b_tesla": rep.critical_magnetic_field_tesla}
        elif key == "penrose_ergosphere":
            rep = penrose_harvester.harvest_ergosphere_energy(0.998)
            return {"subsystem": "Penrose Harvester #155", "efficiency_pct": rep.energy_extraction_efficiency_pct, "power_pw": rep.harvested_power_petawatts}
        elif key == "gravitational_lens":
            rep = lens_router.calculate_gravitational_lens_path("VIRGO_SUPERCLUSTER")
            return {"subsystem": "Gravitational Lens Router #161", "amplification": rep.amplification_factor_einstein_ring, "bandwidth_ebps": rep.effective_bandwidth_exabits_sec}
        elif key == "apex_prime_superintelligence":
            rep = apex_prime_core.achieve_absolute_superintelligence_prime()
            return {"subsystem": "Apex Prime #176", "phi": rep.integrated_phi_apex_prime, "realities": rep.realities_in_eternal_unity}
        else:
            return {"subsystem": key, "status": "SIMULATED_NOMINAL", "active": True}

    def send_json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, fmt, *args):
        """Suppress per-request stdout noise."""
        pass


# ---------------------------------------------------------------------------
# Feature 15: Scheduled daemon background ticks every 30 s
# ---------------------------------------------------------------------------
def _daemon_tick_loop():
    while True:
        time.sleep(30)
        try:
            tick_res = daemon.step_cycle()
            msg = (
                f"[Auto-Tick] status={tick_res.get('status')} "
                f"action={tick_res.get('action_committed')}"
            )
            append_log("AUTO-TICK", msg)
            _persist_state()
            _fire_webhooks("tick", {
                "state": state.variables,
                "action": tick_res.get("action_committed"),
                "auto": True,
            })
        except Exception as e:
            append_log("AUTO-TICK", f"Error: {e}")


# ---------------------------------------------------------------------------
# Server entry-point
# ---------------------------------------------------------------------------
def run_backend(port=PORT):
    # Init SQLite & restore persisted state
    _init_db()
    _restore_state()

    # WebSocket telemetry broadcaster thread
    threading.Thread(
        target=_ws_telemetry_broadcaster, daemon=True, name="ws-broadcaster"
    ).start()

    # Scheduled daemon tick thread (Feature 15)
    threading.Thread(
        target=_daemon_tick_loop, daemon=True, name="daemon-tick"
    ).start()

    append_log(
        "SYSTEM",
        "v32.0.0 online: WebSocket, auth, rate-limiting, SQLite, "
        "webhooks, OpenAPI, SSE, Gemini integration ready.",
    )

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((HOST, port), ZASIUnifiedHandler) as httpd:
        print(f"[✓] ZASI J.A.R.V.I.S. Apex Prime Server Running on http://localhost:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    run_backend()
