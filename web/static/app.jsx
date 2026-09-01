// ZASI J.A.R.V.I.S. Command Cockpit — React 18 + React Router v6
// Routes: / (Overview) | /jarvis | /subsystems | /cockpit | /mcp
const { useState, useEffect, useRef } = React;
const { BrowserRouter, Routes, Route, NavLink, Outlet } = ReactRouterDOM;

// ─────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────
const api = {
    get:  (url)       => fetch(url).then(r => r.json()),
    post: (url, body) => fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body)
    }).then(r => r.json())
};

// ─────────────────────────────────────────────
// TTS helper
// ─────────────────────────────────────────────
function speakPersona(text, persona) {
    if (!('speechSynthesis' in window)) return;
    const u   = new SpeechSynthesisUtterance(text);
    u.pitch   = persona === 'FRIDAY' ? 1.2 : persona === 'EDITH' ? 1.0 : 0.95;
    u.rate    = persona === 'FRIDAY' ? 1.1 : persona === 'EDITH' ? 1.15 : 1.05;
    window.speechSynthesis.speak(u);
}

// ─────────────────────────────────────────────
// Three.js 168-node Hypergraph
// ─────────────────────────────────────────────
function HypergraphCanvas() {
    const mountRef = useRef(null);

    useEffect(() => {
        const el = mountRef.current;
        if (!el) return;

        const scene    = new THREE.Scene();
        scene.fog      = new THREE.FogExp2(0x030712, 0.015);
        const camera   = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.1, 1000);
        camera.position.z = 28;
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(el.clientWidth, el.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        el.appendChild(renderer.domElement);

        const group   = new THREE.Group();
        const coreMat = new THREE.MeshBasicMaterial({ color: 0xf43f5e });
        group.add(new THREE.Mesh(new THREE.SphereGeometry(1.4, 32, 32), coreMat));

        const nodeMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
        const nodeGeo = new THREE.SphereGeometry(0.32, 16, 16);
        for (let i = 0; i < 168; i++) {
            const phi   = Math.acos(-1 + (2 * i) / 168);
            const theta = Math.sqrt(168 * Math.PI) * phi;
            const r     = 9 + (i % 7) * 1.6;
            const node  = new THREE.Mesh(nodeGeo, nodeMat);
            node.position.set(
                r * Math.cos(theta) * Math.sin(phi),
                r * Math.sin(theta) * Math.sin(phi),
                r * Math.cos(phi)
            );
            group.add(node);
        }
        scene.add(group);

        const onResize = () => {
            camera.aspect = el.clientWidth / el.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(el.clientWidth, el.clientHeight);
        };
        window.addEventListener('resize', onResize);

        let raf;
        const animate = () => {
            raf = requestAnimationFrame(animate);
            group.rotation.y += 0.002;
            group.rotation.x += 0.0008;
            renderer.render(scene, camera);
        };
        animate();

        return () => {
            cancelAnimationFrame(raf);
            window.removeEventListener('resize', onResize);
            renderer.dispose();
            if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
        };
    }, []);

    return <div ref={mountRef} style={{ width: '100%', height: '480px', borderRadius: '12px', overflow: 'hidden' }} />;
}

// ─────────────────────────────────────────────
// Hook: live telemetry
// ─────────────────────────────────────────────
function useTelemetry(ms = 2000) {
    const [tele, setTele] = useState(null);
    useEffect(() => {
        const fetch_ = () => api.get('/api/telemetry').then(setTele).catch(() => {});
        fetch_();
        const id = setInterval(fetch_, ms);
        return () => clearInterval(id);
    }, [ms]);
    return tele;
}

// ─────────────────────────────────────────────
// Page: Overview (/)
// ─────────────────────────────────────────────
function OverviewPage() {
    const tele         = useTelemetry();
    const [status, setStatus] = useState(null);

    useEffect(() => {
        const fetch_ = () => api.get('/api/status').then(setStatus).catch(() => {});
        fetch_();
        const id = setInterval(fetch_, 3000);
        return () => clearInterval(id);
    }, []);

    const meters = [
        { label: 'CPU',         val: tele ? `${tele.cpu_load?.toFixed(1)}%` : '—',                      pct: tele?.cpu_load || 0 },
        { label: 'RAM',         val: tele ? `${tele.memory_used_mb?.toLocaleString()} MB` : '—',         pct: tele ? (tele.memory_used_mb / tele.memory_total_mb) * 100 : 0 },
        { label: 'ARC REACTOR', val: tele ? `${tele.arc_reactor_gw?.toFixed(1)} GW` : '—',               pct: tele ? Math.min(100, tele.arc_reactor_gw * 0.56) : 0 },
        ...(tele?.gpus?.[0] ? [{
            label: 'GPU',
            val: `${tele.gpus[0].utilization?.toFixed(1)}% | ${tele.gpus[0].temp_c}°C | ${tele.gpus[0].power_w}W`,
            pct: tele.gpus[0].utilization
        }] : [])
    ];

    return (
        <div className="page">
            <h2 className="page-title">⚡ Overview — Omniversal Status</h2>

            <div className="arc-reactor-ring">
                <div className="arc-inner"><div className="arc-glow" /></div>
            </div>

            <div className="telemetry-grid">
                {meters.map(m => (
                    <div className="tele-card" key={m.label}>
                        <div className="tele-label">{m.label}</div>
                        <div className="tele-val">{m.val}</div>
                        <div className="meter-bar"><div className="meter-fill" style={{ width: `${m.pct}%` }} /></div>
                    </div>
                ))}
            </div>

            <div className="card">
                <div className="card-header">COGNITIVE STATE VECTOR</div>
                <pre className="code-out">{status ? JSON.stringify(status.state, null, 2) : 'Loading...'}</pre>
                <div className="btn-row">
                    <button className="btn primary"   onClick={() => api.post('/api/tick', {}).then(d => setStatus(p => ({ ...p, state: d.state })))}>⚡ Daemon Tick</button>
                    <button className="btn secondary"  onClick={() => api.post('/api/rsi/upgrade', { version: 'v30.0.0-apex-prime' })}>🔁 RSI Upgrade</button>
                    <button className="btn accent"     onClick={() => api.post('/api/mutate', { variable: 'iq', delta: 10 })}>+10 IQ</button>
                </div>
            </div>

            <div className="card">
                <div className="card-header">168-NODE MULTIVERSE HYPERGRAPH</div>
                <HypergraphCanvas />
            </div>

            <div className="card">
                <div className="card-header">SYSTEM LOG</div>
                <div className="log-window">
                    {(tele?.logs || []).map((l, i) => (
                        <div className="log-line" key={i}>[{l.timestamp}] [{l.level}] {l.message}</div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Page: J.A.R.V.I.S. Chat (/jarvis)
// ─────────────────────────────────────────────
function JarvisPage() {
    const [messages, setMessages] = useState([
        { speaker: 'J.A.R.V.I.S.', text: 'Good day, Sir. All 168 subsystems online. How may I assist?', cls: 'jarvis-msg' }
    ]);
    const [input,   setInput]   = useState('');
    const [persona, setPersona] = useState('JARVIS');
    const [voiceOn, setVoiceOn] = useState(true);
    const chatRef = useRef(null);

    useEffect(() => {
        if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }, [messages]);

    const send = async () => {
        const msg = input.trim();
        if (!msg) return;
        setMessages(m => [...m, { speaker: 'USER', text: msg, cls: 'user-msg' }]);
        setInput('');
        try {
            const data = await api.post('/api/jarvis/chat', { message: msg, persona });
            setMessages(m => [...m, { speaker: data.speaker, text: data.response, cls: 'jarvis-msg' }]);
            if (voiceOn) speakPersona(data.response, data.speaker);
        } catch {
            setMessages(m => [...m, { speaker: 'J.A.R.V.I.S.', text: 'Connection interrupted. Retrying subsystem link...', cls: 'jarvis-msg' }]);
        }
    };

    return (
        <div className="page">
            <h2 className="page-title">🤖 J.A.R.V.I.S. Conversational Core</h2>
            <div className="card">
                <div className="card-header" style={{ display:'flex', gap:'1rem', alignItems:'center', flexWrap:'wrap' }}>
                    <span>PERSONA</span>
                    <select className="persona-select" value={persona} onChange={e => setPersona(e.target.value)}>
                        <option value="JARVIS">J.A.R.V.I.S. — Invariant SMT Prover</option>
                        <option value="FRIDAY">F.R.I.D.A.Y. — 1T MoE Router</option>
                        <option value="EDITH">E.D.I.T.H. — Orbital Defense Grid</option>
                    </select>
                    <button className="btn secondary small" onClick={() => setVoiceOn(v => !v)}>
                        {voiceOn ? '🔊 Voice ON' : '🔇 Voice OFF'}
                    </button>
                </div>

                <div className="chat-window" ref={chatRef}>
                    {messages.map((m, i) => (
                        <div className={`chat-msg ${m.cls}`} key={i}>
                            <span className="speaker">{m.speaker}</span>
                            <span className="text">{m.text}</span>
                        </div>
                    ))}
                </div>

                <div className="chat-input-row">
                    <input
                        className="chat-input"
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && send()}
                        placeholder={`Command ${persona}...`}
                    />
                    <button className="btn primary" onClick={send}>TRANSMIT</button>
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Page: Subsystems Catalog (/subsystems)
// ─────────────────────────────────────────────
function SubsystemCard({ s }) {
    const [result, setResult] = useState(null);
    const probe = () => api.get(`/api/execute/${s.module}`).then(setResult).catch(() => {});
    return (
        <div className="subsystem-card">
            <div className="subsystem-id">#{s.id}</div>
            <h4 className="subsystem-name">{s.name}</h4>
            <div className="meta">Module: {s.module}</div>
            <div className="meta">Category: {s.category}</div>
            <button className="btn secondary small" onClick={probe}>PROBE</button>
            {result && <pre className="code-out small">{JSON.stringify(result, null, 2)}</pre>}
        </div>
    );
}

function SubsystemsPage() {
    const [catalog, setCatalog] = useState([]);
    const [filter,  setFilter]  = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/api/subsystems')
            .then(d => { setCatalog(d.catalog || []); setLoading(false); })
            .catch(() => setLoading(false));
    }, []);

    const filtered = catalog.filter(s =>
        s.name.toLowerCase().includes(filter.toLowerCase()) ||
        (s.category || '').toLowerCase().includes(filter.toLowerCase()) ||
        String(s.id).includes(filter)
    );

    return (
        <div className="page">
            <h2 className="page-title">🔬 168 Subsystems Catalog</h2>
            <div className="card">
                <input className="search-input" placeholder="Filter by name, category, or ID…" value={filter} onChange={e => setFilter(e.target.value)} />
                {loading && <p style={{ color: 'var(--accent-cyan)', padding: '1rem' }}>Loading catalog…</p>}
                <div className="subsystems-grid">
                    {filtered.map(s => <SubsystemCard key={s.id} s={s} />)}
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Page: Quantum Cockpit (/cockpit)
// ─────────────────────────────────────────────
const RUNNERS = [
    { label: '🛡  Surface Code QEC d=7',          key: 'surface_code_qec'           },
    { label: '🔮  Quantum Teleportation Matrix',   key: 'quantum_teleportation'      },
    { label: '🌡  Ambient 373 K Superconductor',   key: 'ambient_superconductor'     },
    { label: '🌀  Kerr Penrose Harvester',          key: 'penrose_ergosphere'         },
    { label: '⚡  AMD Alveo FPGA Tensor Core',     key: 'fpga_accelerator'           },
    { label: '🌌  Apex Prime Superintelligence',   key: 'apex_prime_superintelligence'},
];

function CockpitPage() {
    const [outputs, setOutputs] = useState({});
    const run = (key) => api.get(`/api/execute/${key}`)
        .then(d  => setOutputs(p => ({ ...p, [key]: d })))
        .catch(e => setOutputs(p => ({ ...p, [key]: { error: e.message } })));

    return (
        <div className="page">
            <h2 className="page-title">🚀 Quantum Hardware Cockpit</h2>
            <div className="cockpit-grid">
                {RUNNERS.map(r => (
                    <div className="cockpit-card" key={r.key}>
                        <div className="cockpit-label">{r.label}</div>
                        <button className="btn accent" onClick={() => run(r.key)}>FIRE</button>
                        {outputs[r.key] && (
                            <pre className="code-out small">{JSON.stringify(outputs[r.key], null, 2)}</pre>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Page: MCP Console (/mcp)
// ─────────────────────────────────────────────
const DEFAULT_MCP = JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 }, null, 2);

function MCPPage() {
    const [input,    setInput]    = useState(DEFAULT_MCP);
    const [response, setResponse] = useState('');

    const send = async () => {
        try {
            const res = await fetch('/api/mcp', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    input
            });
            setResponse(JSON.stringify(await res.json(), null, 2));
        } catch (e) {
            setResponse(`Error: ${e.message}`);
        }
    };

    return (
        <div className="page">
            <h2 className="page-title">🔌 MCP JSON-RPC 2.0 Console</h2>
            <div className="card">
                <div className="card-header">REQUEST PAYLOAD</div>
                <textarea className="mcp-textarea" value={input} onChange={e => setInput(e.target.value)} rows={10} />
                <button className="btn primary" style={{ marginTop: '0.75rem' }} onClick={send}>DISPATCH RPC</button>
            </div>
            <div className="card">
                <div className="card-header">SERVER RESPONSE</div>
                <pre className="code-out">{response || 'Awaiting dispatch…'}</pre>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────
// Shell Layout
// ─────────────────────────────────────────────
const NAV = [
    { to: '/',           label: '⚡ Overview',    end: true },
    { to: '/jarvis',     label: '🤖 J.A.R.V.I.S.' },
    { to: '/subsystems', label: '🔬 Subsystems'   },
    { to: '/cockpit',    label: '🚀 Cockpit'       },
    { to: '/mcp',        label: '🔌 MCP'           },
];

function Shell() {
    return (
        <div className="shell">
            <header className="top-bar">
                <div className="logo">
                    <span className="logo-z">Z</span>ASI
                    <span className="logo-version">v30.0.0 · 168 Subsystems · 320× RSI</span>
                </div>
                <nav className="nav-links">
                    {NAV.map(l => (
                        <NavLink key={l.to} to={l.to} end={l.end}
                            className={({ isActive }) => 'nav-tab' + (isActive ? ' active' : '')}>
                            {l.label}
                        </NavLink>
                    ))}
                </nav>
            </header>
            <main className="main-content">
                <Outlet />
            </main>
            <footer className="footer">
                ZASI Omniversal Superintelligence · React 18 + React Router v6 · 168 Subsystems · MCP/REST Backend
            </footer>
        </div>
    );
}

// ─────────────────────────────────────────────
// Root App — React Router v6 route tree
// ─────────────────────────────────────────────
function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Shell />}>
                    <Route index           element={<OverviewPage />}    />
                    <Route path="jarvis"     element={<JarvisPage />}      />
                    <Route path="subsystems" element={<SubsystemsPage />}  />
                    <Route path="cockpit"    element={<CockpitPage />}     />
                    <Route path="mcp"        element={<MCPPage />}         />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

// Mount React 18 root
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
