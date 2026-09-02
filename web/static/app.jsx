import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';
import {
    BrowserRouter,
    NavLink,
    Outlet,
    Route,
    Routes,
    useNavigate,
} from 'react-router-dom';
import * as THREE from 'three';

const API_ROOT = (import.meta.env.VITE_API_ROOT || '').replace(/\/$/, '');

class ApiError extends Error {
    constructor(response, payload) {
        super(payload?.error?.message || `Request failed (${response.status})`);
        this.status = response.status;
        this.code = payload?.error?.code || 'HTTP_ERROR';
        this.payload = payload;
    }
}

const api = {
    async request(path, { token, method = 'GET', body, headers = {} } = {}) {
        const requestHeaders = { Accept: 'application/json', ...headers };
        if (token) requestHeaders.Authorization = `Bearer ${token}`;
        if (body !== undefined) requestHeaders['Content-Type'] = 'application/json';
        const response = await fetch(`${API_ROOT}${path}`, {
            method,
            headers: requestHeaders,
            body: body === undefined ? undefined : JSON.stringify(body),
            cache: 'no-store',
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch {
            payload = null;
        }
        if (!response.ok) throw new ApiError(response, payload);
        return payload;
    },
    get(path, token) {
        return this.request(path, { token });
    },
    post(path, token, body, headers = {}) {
        return this.request(path, { token, method: 'POST', body, headers });
    },
};

const AuthContext = createContext(null);
const ThemeContext = createContext(null);
const ToastContext = createContext(null);

function useAuth() {
    return useContext(AuthContext);
}

function AuthProvider({ children }) {
    const [session, setSession] = useState(null);
    const [error, setError] = useState('');

    const login = useCallback(async (apiKey) => {
        setError('');
        try {
            const next = await api.post('/api/v2/sessions', undefined, { api_key: apiKey });
            setSession(next);
            return next;
        } catch (err) {
            setError(err.message);
            throw err;
        }
    }, []);

    const logout = useCallback(async () => {
        if (session?.access_token) {
            try {
                await api.post('/api/v2/sessions/revoke', session.access_token);
            } catch {
                // Clearing local state is still safe when the server already revoked it.
            }
        }
        setSession(null);
    }, [session]);

    const value = useMemo(() => ({ session, login, logout, error }), [session, login, logout, error]);
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function ThemeProvider({ children }) {
    const [theme, setTheme] = useState(() => localStorage.getItem('zasi_theme') || 'dark');
    useEffect(() => {
        document.body.className = theme === 'light' ? 'theme-light' : 'theme-dark';
        localStorage.setItem('zasi_theme', theme);
    }, [theme]);
    return (
        <ThemeContext.Provider value={{ theme, toggleTheme: () => setTheme((value) => value === 'dark' ? 'light' : 'dark') }}>
            {children}
        </ThemeContext.Provider>
    );
}

function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const addToast = useCallback((message, type = 'info') => {
        const id = `${Date.now()}-${Math.random()}`;
        setToasts((items) => [...items, { id, message, type }]);
        window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 4000);
    }, []);
    return (
        <ToastContext.Provider value={{ addToast }}>
            {children}
            <div className="toast-container" aria-live="polite">
                {toasts.map((toast) => <div className={`toast-banner toast-${toast.type}`} key={toast.id}>{toast.message}</div>)}
            </div>
        </ToastContext.Provider>
    );
}

function LoginPage() {
    const { login, error } = useAuth();
    const [apiKey, setApiKey] = useState('');
    const [pending, setPending] = useState(false);
    const submit = async (event) => {
        event.preventDefault();
        if (!apiKey.trim()) return;
        setPending(true);
        try {
            await login(apiKey);
            setApiKey('');
        } catch {
            // AuthProvider exposes the redacted error message.
        } finally {
            setPending(false);
        }
    };
    return (
        <main className="auth-page">
            <section className="auth-card card">
                <div className="logo"><span className="logo-z">Z</span>ASI</div>
                <h1>Governed command cockpit</h1>
                <p className="muted">Authenticate a scoped operator session. The credential stays in memory and is never rendered or stored by the cockpit.</p>
                <form onSubmit={submit}>
                    <label htmlFor="api-key">Bootstrap credential</label>
                    <input id="api-key" className="chat-input" type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
                    <button className="btn primary" disabled={pending || !apiKey.trim()} type="submit">{pending ? 'AUTHENTICATING…' : 'AUTHENTICATE'}</button>
                </form>
                {error && <p className="error-text" role="alert">Authentication failed. {error}</p>}
                <p className="disclosure">Reference profile: external writes, research execution, physical actuation, and runtime hot swap are disabled.</p>
            </section>
        </main>
    );
}

function useTelemetry(ms = 5000) {
    const { session } = useAuth();
    const [snapshot, setSnapshot] = useState(null);
    useEffect(() => {
        let active = true;
        if (!session?.access_token) return undefined;
        const load = () => api.get('/api/v2/snapshot', session.access_token).then((data) => {
            if (active) setSnapshot(data);
        }).catch(() => {});
        load();
        const id = window.setInterval(load, ms);
        return () => { active = false; window.clearInterval(id); };
    }, [ms, session?.access_token]);
    return snapshot;
}

function parseSseBlock(block) {
    const lines = block.split('\n');
    const type = (lines.find((line) => line.startsWith('event:')) || '').slice(6).trim();
    const dataLine = lines.find((line) => line.startsWith('data:'));
    if (!dataLine) return { type, data: null };
    try {
        return { type, data: JSON.parse(dataLine.slice(5).trim()) };
    } catch {
        return { type, data: null };
    }
}

function useEventFeed() {
    const { session } = useAuth();
    const [state, setState] = useState({ status: 'disconnected', cursor: 0, events: [] });
    useEffect(() => {
        if (!session?.access_token) return undefined;
        let stopped = false;
        let cursor = 0;
        let controller;
        const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
        const connect = async () => {
            while (!stopped) {
                controller = new AbortController();
                setState((current) => ({ ...current, status: 'connecting' }));
                try {
                    const response = await fetch(`${API_ROOT}/api/v2/events?after=${cursor}&follow=true`, {
                        headers: { Accept: 'text/event-stream', Authorization: `Bearer ${session.access_token}` },
                        cache: 'no-store',
                        signal: controller.signal,
                    });
                    if (!response.ok || !response.body) throw new Error(`event stream unavailable (${response.status})`);
                    setState((current) => ({ ...current, status: 'connected' }));
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    while (!stopped) {
                        const chunk = await reader.read();
                        if (chunk.done) break;
                        buffer += decoder.decode(chunk.value, { stream: true });
                        const blocks = buffer.split('\n\n');
                        buffer = blocks.pop() || '';
                        blocks.forEach((block) => {
                            const parsed = parseSseBlock(block);
                            if (!parsed.data) return;
                            if (parsed.type === 'resync.required') {
                                api.get('/api/v2/snapshot', session.access_token).then((snapshot) => {
                                    cursor = snapshot.cursor || 0;
                                    setState({ status: 'connected', cursor, events: [] });
                                }).catch(() => setState((current) => ({ ...current, status: 'degraded' })));
                                return;
                            }
                            if (parsed.data.sequence) cursor = parsed.data.sequence;
                            if (parsed.type !== 'stream.end') {
                                setState((current) => ({ status: current.status, cursor, events: [...current.events, parsed.data].slice(-40) }));
                            }
                        });
                    }
                } catch (error) {
                    if (!stopped && error.name !== 'AbortError') setState((current) => ({ ...current, status: 'degraded' }));
                }
                if (!stopped) await sleep(1000);
            }
        };
        connect();
        return () => {
            stopped = true;
            controller?.abort();
        };
    }, [session?.access_token]);
    return state;
}

function HypergraphCanvas({ nodeCount = 1 }) {
    const mountRef = useRef(null);
    useEffect(() => {
        const element = mountRef.current;
        if (!element) return undefined;
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(60, Math.max(element.clientWidth, 1) / Math.max(element.clientHeight, 1), 0.1, 1000);
        camera.position.z = 28;
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(element.clientWidth, element.clientHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        element.appendChild(renderer.domElement);
        const group = new THREE.Group();
        group.add(new THREE.Mesh(new THREE.SphereGeometry(1.4, 24, 24), new THREE.MeshBasicMaterial({ color: 0x38bdf8 })));
        const count = Math.max(1, Math.min(Number(nodeCount) || 1, 256));
        const material = new THREE.MeshBasicMaterial({ color: 0x67e8f9, wireframe: true });
        const geometry = new THREE.SphereGeometry(0.26, 12, 12);
        for (let index = 0; index < count; index += 1) {
            const phi = Math.acos(-1 + (2 * index) / count);
            const theta = Math.sqrt(count * Math.PI) * phi;
            const radius = 7 + (index % 5) * 1.2;
            const node = new THREE.Mesh(geometry, material);
            node.position.set(radius * Math.cos(theta) * Math.sin(phi), radius * Math.sin(theta) * Math.sin(phi), radius * Math.cos(phi));
            group.add(node);
        }
        scene.add(group);
        const resize = () => {
            camera.aspect = Math.max(element.clientWidth, 1) / Math.max(element.clientHeight, 1);
            camera.updateProjectionMatrix();
            renderer.setSize(element.clientWidth, element.clientHeight);
        };
        let frame;
        const animate = () => {
            frame = requestAnimationFrame(animate);
            group.rotation.y += 0.0015;
            group.rotation.x += 0.0005;
            renderer.render(scene, camera);
        };
        window.addEventListener('resize', resize);
        animate();
        return () => {
            cancelAnimationFrame(frame);
            window.removeEventListener('resize', resize);
            geometry.dispose();
            material.dispose();
            renderer.dispose();
            if (element.contains(renderer.domElement)) element.removeChild(renderer.domElement);
        };
    }, [nodeCount]);
    return <div ref={mountRef} className="hypergraph-container" aria-label="Capability registry visualization" />;
}

function StatusBadge({ status, children }) {
    return <span className={`status-badge status-${status}`}>{children || status}</span>;
}

function CommandPalette({ isOpen, onClose }) {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const actions = [
        { label: 'Go to Overview', path: '/' },
        { label: 'Open J.A.R.V.I.S. Observe', path: '/jarvis' },
        { label: 'Open Capability Registry', path: '/subsystems' },
        { label: 'Open Safety Cockpit', path: '/cockpit' },
        { label: 'Open Governed MCP Console', path: '/mcp' },
    ];
    useEffect(() => {
        const onKey = (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); onClose(); }
            if (event.key === 'Escape' && isOpen) onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);
    if (!isOpen) return null;
    return (
        <div className="modal-overlay" onClick={onClose} role="presentation">
            <div className="palette-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
                <input autoFocus className="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search governed views…" />
                <div className="palette-list">
                    {actions.filter((item) => item.label.toLowerCase().includes(query.toLowerCase())).map((item) => (
                        <button className="palette-item" key={item.path} onClick={() => { navigate(item.path); onClose(); }}>{item.label}</button>
                    ))}
                </div>
            </div>
        </div>
    );
}

function OverviewPage() {
    const { session } = useAuth();
    const snapshot = useTelemetry();
    const feed = useEventFeed();
    const { addToast } = useContext(ToastContext);
    const [capabilities, setCapabilities] = useState([]);
    const [result, setResult] = useState(null);
    useEffect(() => {
        if (session?.access_token) api.get('/api/v2/capabilities', session.access_token).then((data) => setCapabilities(data.capabilities || [])).catch(() => {});
    }, [session?.access_token]);
    const observe = async () => {
        try {
            const intent = await api.post('/api/v2/intents', session.access_token, {
                source_kind: 'text', source_text: 'show system status',
                goal: { verb: 'observe', object: 'system.status', parameters: {} },
                requested_mode: 'observe', requested_risk_tier: 'R0',
            });
            const plan = await api.post(`/api/v2/intents/${intent.intent_id}/plan`, session.access_token);
            const run = await api.post(`/api/v2/plans/${plan.plan_id}/run`, session.access_token, {}, { 'Idempotency-Key': `observe-${Date.now()}` });
            setResult(run);
            addToast('Read-only observation completed', 'success');
        } catch (error) {
            setResult({ status: 'unavailable', disclosure: error.message });
            addToast('Observation unavailable', 'error');
        }
    };
    return (
        <div className="page route-fade">
            <div className="page-heading"><h2 className="page-title">⚡ Governed control-plane overview</h2><StatusBadge status={feed.status}>{feed.status.toUpperCase()}</StatusBadge></div>
            <div className="notice"><strong>Reference profile disclosure:</strong> this surface reports registry and evidence state. It does not claim that the legacy catalog is live, and it exposes no direct mutation controls.</div>
            <div className="telemetry-grid">
                <div className="tele-card"><div className="tele-label">TENANT</div><div className="tele-val">{session.tenant_id}</div><div className="muted">scoped session</div></div>
                <div className="tele-card"><div className="tele-label">CAPABILITIES</div><div className="tele-val">{capabilities.length}</div><div className="muted">registry-derived</div></div>
                <div className="tele-card"><div className="tele-label">EVENT CURSOR</div><div className="tele-val">{feed.cursor}</div><div className="muted">tenant scoped</div></div>
                <div className="tele-card"><div className="tele-label">DATABASE</div><div className="tele-val">{snapshot?.capabilities?.database || '—'}</div><div className="muted">authoritative readiness</div></div>
            </div>
            <div className="card">
                <div className="card-header">OBSERVE → TYPED INTENT → PLAN → EVIDENCE</div>
                <p className="muted">Run the only enabled reference observation. It creates durable intent, plan, audit, event, run, and evidence records.</p>
                <button className="btn primary" onClick={observe}>OBSERVE SYSTEM STATUS</button>
                {result && <pre className="code-out">{JSON.stringify(result, null, 2)}</pre>}
            </div>
            <div className="card"><div className="card-header">CAPABILITY REGISTRY GRAPH · {capabilities.length} REGISTERED</div><HypergraphCanvas nodeCount={capabilities.length} /></div>
            <div className="card"><div className="card-header">DURABLE EVENT FEED</div>{feed.events.length ? feed.events.slice(-8).map((event) => <div className="log-line" key={event.event_id}>{event.sequence} · {event.type} · {event.payload?.status || event.aggregate?.id}</div>) : <p className="muted">No events received in this session.</p>}</div>
        </div>
    );
}

function JarvisPage() {
    const { session } = useAuth();
    const [messages, setMessages] = useState([{ speaker: 'J.A.R.V.I.S.', text: 'Authenticated. Observe and Assist are available; no external write is enabled.', cls: 'jarvis-msg' }]);
    const [input, setInput] = useState('');
    const [listening, setListening] = useState(false);
    const [voiceInput, setVoiceInput] = useState(false);
    const chatRef = useRef(null);
    const { addToast } = useContext(ToastContext);
    useEffect(() => { if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight; }, [messages]);
    const send = async () => {
        const text = input.trim();
        if (!text) return;
        setInput('');
        setMessages((items) => [...items, { speaker: 'USER', text, cls: 'user-msg' }]);
        try {
            const intent = await api.post('/api/v2/intents', session.access_token, {
                source_kind: voiceInput ? 'voice' : 'text', source_text: text,
                goal: { verb: 'observe', object: 'system.status', parameters: {} },
                requested_mode: 'assist', requested_risk_tier: 'R0',
            });
            const plan = await api.post(`/api/v2/intents/${intent.intent_id}/plan`, session.access_token);
            const run = await api.post(`/api/v2/plans/${plan.plan_id}/run`, session.access_token, {}, { 'Idempotency-Key': `jarvis-${Date.now()}` });
            setMessages((items) => [...items, { speaker: 'J.A.R.V.I.S.', text: `Observation ${run.status}. Evidence is ${run.evidence?.status || 'unavailable'}. ${run.evidence?.provenance?.disclosure || ''}`, cls: 'jarvis-msg' }]);
            addToast('Assistive observation recorded', 'success');
        } catch (error) {
            setMessages((items) => [...items, { speaker: 'J.A.R.V.I.S.', text: `Request not executed: ${error.message}`, cls: 'jarvis-msg' }]);
            addToast('Request rejected or unavailable', 'error');
        }
        setVoiceInput(false);
    };
    const startVoiceInput = () => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) { addToast('Browser speech recognition is unavailable; type the request instead.', 'error'); return; }
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onstart = () => { setListening(true); setVoiceInput(true); };
        recognition.onend = () => setListening(false);
        recognition.onerror = () => { setListening(false); setVoiceInput(false); addToast('Voice input failed; no command was authorized.', 'error'); };
        recognition.onresult = (event) => setInput(event.results[0][0].transcript);
        recognition.start();
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">🤖 J.A.R.V.I.S. Observe / Assist</h2>
            <div className="notice">Voice transcription is an input signal only. It does not establish identity or approval.</div>
            <div className="card">
                <div className="chat-window" ref={chatRef}>
                    {messages.map((message, index) => <div className={`chat-msg ${message.cls}`} key={`${message.speaker}-${index}`}><span className="speaker">{message.speaker}</span><span className="text">{message.text}</span></div>)}
                </div>
                <div className="chat-input-row"><input className="chat-input" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && send()} placeholder="Ask for a read-only observation…" /><button className={`btn secondary small ${listening ? 'listening' : ''}`} onClick={startVoiceInput}>{listening ? '🔴 Listening…' : '🎤 Voice input'}</button><button className="btn primary" onClick={send}>SUBMIT INTENT</button></div>
            </div>
        </div>
    );
}

function SubsystemsPage() {
    const { session } = useAuth();
    const [capabilities, setCapabilities] = useState([]);
    useEffect(() => { api.get('/api/v2/capabilities', session.access_token).then((data) => setCapabilities(data.capabilities || [])).catch(() => {}); }, [session?.access_token]);
    return (
        <div className="page route-fade">
            <h2 className="page-title">🔬 Capability registry</h2>
            <div className="notice">Registry entries are not execution grants. Each state below is independent and evidence-backed.</div>
            <div className="subsystems-grid">{capabilities.map((capability) => <article className="subsystem-card" key={capability.capability_id}><div className="subsystem-id">{capability.capability_id}</div><h4 className="subsystem-name">{capability.tool_id}</h4><div className="meta">Risk: {capability.risk_tier}</div><div className="state-row"><StatusBadge status={capability.implementation_state}>{capability.implementation_state}</StatusBadge><StatusBadge status={capability.runtime_state}>{capability.runtime_state}</StatusBadge><StatusBadge status={capability.evidence_state}>{capability.evidence_state}</StatusBadge></div><p className="disclosure">{capability.disclosure}</p></article>)}</div>
        </div>
    );
}

function CockpitPage() {
    const { session } = useAuth();
    const [connectors, setConnectors] = useState(null);
    useEffect(() => { api.get('/api/v2/connectors', session.access_token).then(setConnectors).catch(() => {}); }, [session?.access_token]);
    return (
        <div className="page route-fade">
            <h2 className="page-title">🛡 Safety cockpit</h2>
            <div className="card"><div className="card-header">HIGH-IMPACT CAPABILITIES</div><div className="safety-grid"><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>Physical actuation</h3><p className="disclosure">No actuator endpoint exists in the reference profile.</p></div><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>Research compiler / RSI</h3><p className="disclosure">No runtime code generation or hot swap is exposed.</p></div><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>External egress</h3><p className="disclosure">Connector calls require a separately configured egress broker.</p></div></div></div>
            <div className="card"><div className="card-header">CONNECTOR STATUS</div><pre className="code-out">{connectors ? JSON.stringify(connectors, null, 2) : 'Loading…'}</pre></div>
        </div>
    );
}

const DEFAULT_MCP = JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 }, null, 2);

function MCPPage() {
    const { session } = useAuth();
    const [input, setInput] = useState(DEFAULT_MCP);
    const [response, setResponse] = useState('');
    const { addToast } = useContext(ToastContext);
    const send = async () => {
        try {
            const request = JSON.parse(input);
            const needsKey = request.method === 'tools/call';
            const result = await api.post('/api/v2/mcp', session.access_token, request, needsKey ? { 'Idempotency-Key': `mcp-${Date.now()}` } : {});
            setResponse(JSON.stringify(result, null, 2));
            addToast('Governed MCP request completed', 'success');
        } catch (error) {
            setResponse(error instanceof ApiError ? JSON.stringify(error.payload, null, 2) : `Invalid request: ${error.message}`);
            addToast('MCP request rejected', 'error');
        }
    };
    return <div className="page route-fade"><h2 className="page-title">🔌 Governed MCP JSON-RPC 2.0</h2><div className="notice">Discovery is read-only. Tool calls use the same identity, policy, idempotency, audit, and evidence path as REST.</div><div className="card"><div className="card-header">REQUEST</div><textarea className="mcp-textarea" value={input} onChange={(event) => setInput(event.target.value)} rows={8} /><button className="btn primary" onClick={send}>DISPATCH</button></div><div className="card"><div className="card-header">RESPONSE</div><pre className="code-out">{response || 'Awaiting dispatch…'}</pre></div></div>;
}

const NAV = [
    { to: '/', label: '⚡ Overview', end: true },
    { to: '/jarvis', label: '🤖 J.A.R.V.I.S.' },
    { to: '/subsystems', label: '🔬 Registry' },
    { to: '/cockpit', label: '🛡 Safety' },
    { to: '/mcp', label: '🔌 MCP' },
];

function Shell() {
    const { session, logout } = useAuth();
    const { theme, toggleTheme } = useContext(ThemeContext);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const feed = useEventFeed();
    return <div className="shell"><header className="top-bar"><div className="logo"><span className="logo-z">Z</span>ASI <span className="logo-version">governed reference profile</span></div><nav className="nav-links">{NAV.map((link) => <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>{link.label}</NavLink>)}</nav><div className="header-actions"><StatusBadge status={feed.status}>{feed.status}</StatusBadge><span className="tenant-label">{session.tenant_id}</span><button className="btn secondary small" onClick={() => setPaletteOpen(true)} title="Command palette">⌘K</button><button className="btn secondary small" onClick={toggleTheme}>{theme === 'dark' ? '☀️' : '🌙'}</button><button className="btn secondary small" onClick={logout}>SIGN OUT</button></div></header><main className="main-content"><Outlet /></main><footer className="footer">ZASI governed control plane · Observe / Assist · simulated and unavailable states are disclosed</footer><CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} /></div>;
}

function AuthenticatedApp() {
    const { session } = useAuth();
    if (!session) return <LoginPage />;
    return <Routes><Route path="/" element={<Shell />}><Route index element={<OverviewPage />} /><Route path="jarvis" element={<JarvisPage />} /><Route path="subsystems" element={<SubsystemsPage />} /><Route path="cockpit" element={<CockpitPage />} /><Route path="mcp" element={<MCPPage />} /></Route></Routes>;
}

function App() {
    return <ThemeProvider><ToastProvider><AuthProvider><BrowserRouter><AuthenticatedApp /></BrowserRouter></AuthProvider></ToastProvider></ThemeProvider>;
}

// Kept as a reviewed compatibility module while app.tsx owns the typed entrypoint.
export default App;
