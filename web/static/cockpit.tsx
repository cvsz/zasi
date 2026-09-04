import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ChangeEvent,
    type FormEvent,
    type KeyboardEvent as ReactKeyboardEvent,
    type MouseEvent as ReactMouseEvent,
    type ReactNode,
} from 'react';
import {
    BrowserRouter,
    NavLink,
    Outlet,
    Route,
    Routes,
    useNavigate,
    useLocation,
} from 'react-router-dom';

const API_ROOT = (import.meta.env.VITE_API_ROOT || '').replace(/\/$/, '');
const ROUTER_BASENAME = import.meta.env.BASE_URL.startsWith('/')
    ? import.meta.env.BASE_URL.replace(/\/$/, '') || undefined
    : undefined;

type JsonRecord = Record<string, unknown>;

interface Session {
    access_token: string;
    tenant_id: string;
    [key: string]: unknown;
}

interface IntentResponse extends JsonRecord {
    intent_id: string;
}

interface PlanResponse extends JsonRecord {
    plan_id: string;
}

interface RunResponse extends JsonRecord {
    status?: string;
    evidence?: {
        status?: string;
        provenance?: { disclosure?: string };
    } | null;
    disclosure?: string;
}

interface Snapshot extends JsonRecord {
    cursor?: number;
    capabilities?: { database?: string };
}

interface Capability extends JsonRecord {
    capability_id: string;
    tool_id: string;
    risk_tier: string;
    implementation_state: string;
    runtime_state: string;
    evidence_state: string;
    disclosure: string;
}

interface CapabilitiesResponse extends JsonRecord {
    capabilities?: Capability[];
}

interface Message {
    speaker: string;
    text: string;
    cls: 'jarvis-msg' | 'user-msg';
}

interface SpeechRecognitionResultLike {
    [index: number]: { transcript: string };
}

interface SpeechRecognitionEventLike {
    results: { [index: number]: SpeechRecognitionResultLike };
}

interface SpeechRecognitionLike {
    continuous: boolean;
    interimResults: boolean;
    onstart: (() => void) | null;
    onend: (() => void) | null;
    onerror: (() => void) | null;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    start: () => void;
}

interface SpeechRecognitionConstructor {
    new (): SpeechRecognitionLike;
}

declare global {
    interface Window {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
    }
}

interface FeedEvent extends JsonRecord {
    event_id?: string;
    sequence?: number;
    type?: string;
    payload?: JsonRecord;
    aggregate?: { id?: string };
}

type FeedStatus = 'disconnected' | 'connecting' | 'connected' | 'degraded';

interface FeedState {
    status: FeedStatus;
    cursor: number;
    events: FeedEvent[];
}

interface SseBlock {
    type: string;
    data: FeedEvent | null;
}

interface ApiErrorPayload extends JsonRecord {
    error?: { message?: unknown; code?: unknown };
}

interface ApiRequestOptions {
    token?: string;
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
}

function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Unknown error';
}

function displayValue(value: unknown, fallback = '—'): string {
    return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback;
}

class ApiError extends Error {
    readonly status: number;
    readonly code: string;
    readonly payload: ApiErrorPayload | null;

    constructor(response: Response, payload: ApiErrorPayload | null) {
        const message = typeof payload?.error?.message === 'string'
            ? payload.error.message
            : `Request failed (${response.status})`;
        super(message);
        this.name = 'ApiError';
        this.status = response.status;
        this.code = typeof payload?.error?.code === 'string' ? payload.error.code : 'HTTP_ERROR';
        this.payload = payload;
    }
}

const api = {
    async request<T = JsonRecord>(path: string, { token, method = 'GET', body, headers = {} }: ApiRequestOptions = {}): Promise<T> {
        const requestHeaders: Record<string, string> = { Accept: 'application/json', ...headers };
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
            payload = await response.json() as ApiErrorPayload;
        } catch {
            payload = null;
        }
        if (!response.ok) throw new ApiError(response, payload);
        return payload as T;
    },
    get<T = JsonRecord>(path: string, token?: string): Promise<T> {
        return this.request<T>(path, { token });
    },
    post<T = JsonRecord>(path: string, token?: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
        return this.request<T>(path, { token, method: 'POST', body, headers });
    },
    async upload<T = JsonRecord>(path: string, token: string, body: BodyInit, contentType: string): Promise<T> {
        const response = await fetch(`${API_ROOT}${path}`, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                Authorization: `Bearer ${token}`,
                'Content-Type': contentType,
            },
            body,
            cache: 'no-store',
        });
        let payload: ApiErrorPayload | null = null;
        try {
            payload = await response.json() as ApiErrorPayload;
        } catch {
            payload = null;
        }
        if (!response.ok) throw new ApiError(response, payload);
        return payload as T;
    },
};

interface AuthContextValue {
    session: Session | null;
    login: (apiKey: string) => Promise<Session>;
    logout: () => Promise<void>;
    error: string;
}

interface ThemeContextValue {
    theme: 'dark' | 'light';
    toggleTheme: () => void;
}

type ToastType = 'info' | 'success' | 'error';

interface Toast {
    id: string;
    message: string;
    type: ToastType;
}

interface ToastContextValue {
    addToast: (message: string, type?: ToastType) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const ThemeContext = createContext<ThemeContextValue | null>(null);
const ToastContext = createContext<ToastContextValue | null>(null);

function useAuth(): AuthContextValue {
    const context = useContext(AuthContext);
    if (!context) throw new Error('AuthProvider is missing');
    return context;
}

function useTheme(): ThemeContextValue {
    const context = useContext(ThemeContext);
    if (!context) throw new Error('ThemeProvider is missing');
    return context;
}

function useToast(): ToastContextValue {
    const context = useContext(ToastContext);
    if (!context) throw new Error('ToastProvider is missing');
    return context;
}

function AuthProvider({ children }: { children: ReactNode }) {
    const [session, setSession] = useState<Session | null>(null);
    const [error, setError] = useState('');

    const login = useCallback(async (apiKey: string): Promise<Session> => {
        setError('');
        try {
            const next = await api.post<Session>('/api/v2/sessions', undefined, { api_key: apiKey });
            setSession(next);
            return next;
        } catch (err: unknown) {
            setError(errorMessage(err));
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

function ThemeProvider({ children }: { children: ReactNode }) {
    const [theme, setTheme] = useState<'dark' | 'light'>(() => localStorage.getItem('zasi_theme') === 'light' ? 'light' : 'dark');
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

function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const addToast = useCallback((message: string, type: ToastType = 'info') => {
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
    const submit = async (event: FormEvent<HTMLFormElement>) => {
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
            <section className="auth-card card" aria-labelledby="login-title">
                <div className="logo"><span className="logo-z">Z</span>ASI</div>
                <h1 id="login-title">Governed command cockpit</h1>
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

function useTelemetry(ms: number = 5000): Snapshot | null {
    const { session } = useAuth();
    const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
    useEffect(() => {
        let active = true;
        if (!session?.access_token) return undefined;
        const load = () => api.get<Snapshot>('/api/v2/snapshot', session.access_token).then((data) => {
            if (active) setSnapshot(data);
        }).catch(() => {});
        load();
        const id = window.setInterval(load, ms);
        return () => { active = false; window.clearInterval(id); };
    }, [ms, session?.access_token]);
    return snapshot;
}

function isJsonRecord(value: unknown): value is JsonRecord {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseSseBlock(block: string): SseBlock {
    const lines = block.split('\n');
    const type = (lines.find((line) => line.startsWith('event:')) || '').slice(6).trim();
    const dataLine = lines.find((line) => line.startsWith('data:'));
    if (!dataLine) return { type, data: null };
    try {
        const parsed: unknown = JSON.parse(dataLine.slice(5).trim());
        return { type, data: isJsonRecord(parsed) ? parsed as FeedEvent : null };
    } catch {
        return { type, data: null };
    }
}

function useEventFeed(): FeedState {
    const { session } = useAuth();
    const [state, setState] = useState<FeedState>({ status: 'disconnected', cursor: 0, events: [] });
    useEffect(() => {
        if (!session?.access_token) return undefined;
        let stopped = false;
        let cursor = 0;
        let controller: AbortController | undefined;
        const sleep = (ms: number): Promise<void> => new Promise((resolve) => window.setTimeout(resolve, ms));
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
                            const data = parsed.data;
                            if (!data) return;
                            if (parsed.type === 'resync.required') {
                                api.get<Snapshot>('/api/v2/snapshot', session.access_token).then((snapshot) => {
                                    cursor = snapshot.cursor ?? 0;
                                    setState({ status: 'connected', cursor, events: [] });
                                }).catch(() => setState((current) => ({ ...current, status: 'degraded' })));
                                return;
                            }
                            if (typeof data.sequence === 'number') cursor = data.sequence;
                            if (parsed.type !== 'stream.end') {
                                setState((current) => ({ status: current.status, cursor, events: [...current.events, data].slice(-40) }));
                            }
                        });
                    }
                } catch (error: unknown) {
                    if (!stopped && !(error instanceof DOMException && error.name === 'AbortError')) setState((current) => ({ ...current, status: 'degraded' }));
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

interface HypergraphCanvasProps {
    nodeCount?: number;
}

function HypergraphCanvas({ nodeCount = 1 }: HypergraphCanvasProps) {
    const mountRef = useRef<HTMLDivElement | null>(null);
    const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');
    useEffect(() => {
        let disposed = false;
        let disposeRenderer: (() => void) | undefined;
        setStatus('loading');
        const initialize = async (): Promise<void> => {
            const THREE = await import('three');
            if (disposed) return;
            const element = mountRef.current;
            if (!element) {
                setStatus('unavailable');
                return;
            }
            const scene = new THREE.Scene();
            const camera = new THREE.PerspectiveCamera(60, Math.max(element.clientWidth, 1) / Math.max(element.clientHeight, 1), 0.1, 1000);
            camera.position.z = 28;
            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            renderer.setSize(element.clientWidth, element.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            element.appendChild(renderer.domElement);
            const group = new THREE.Group();
            const coreGeometry = new THREE.SphereGeometry(1.4, 24, 24);
            const coreMaterial = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
            group.add(new THREE.Mesh(coreGeometry, coreMaterial));
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
            let frame: number | undefined;
            const animate = () => {
                frame = requestAnimationFrame(animate);
                group.rotation.y += 0.0015;
                group.rotation.x += 0.0005;
                renderer.render(scene, camera);
            };
            window.addEventListener('resize', resize);
            animate();
            setStatus('ready');
            disposeRenderer = () => {
                if (frame !== undefined) cancelAnimationFrame(frame);
                window.removeEventListener('resize', resize);
                coreGeometry.dispose();
                coreMaterial.dispose();
                geometry.dispose();
                material.dispose();
                renderer.dispose();
                if (element.contains(renderer.domElement)) element.removeChild(renderer.domElement);
            };
        };
        void initialize().catch(() => {
            if (!disposed) setStatus('unavailable');
        });
        return () => {
            disposed = true;
            disposeRenderer?.();
        };
    }, [nodeCount]);
    return <div ref={mountRef} className="hypergraph-container" role="img" aria-label="Capability registry visualization">{status === 'loading' && <span className="muted">Loading visualization…</span>}{status === 'unavailable' && <span className="muted">Visualization unavailable; the registry remains authoritative.</span>}</div>;
}

function StatusBadge({ status, children }: { status: string; children?: ReactNode }) {
    return <span className={`status-badge status-${status}`}>{children || status}</span>;
}

interface CommandPaletteProps {
    isOpen: boolean;
    onClose: () => void;
}

interface NavigationAction {
    label: string;
    path: string;
}

interface NavigationLink {
    to: string;
    label: string;
    end?: boolean;
}

function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const actions: NavigationAction[] = [
        { label: 'Go to Overview', path: '/' },
        { label: 'Open J.A.R.V.I.S. Observe', path: '/jarvis' },
        { label: 'Open Capability Registry', path: '/subsystems' },
        { label: 'Open Engineering Artifacts', path: '/engineering' },
        { label: 'Open Safety Cockpit', path: '/cockpit' },
        { label: 'Open Governed MCP Console', path: '/mcp' },
        { label: 'Open Morning Brief', path: '/briefings' },
        { label: 'Open Do This', path: '/do-this' },
        { label: 'Open Advanced', path: '/advanced' },
        { label: 'Open Humanoid', path: '/humanoid' },
        { label: 'Open Mobile Link', path: '/mobile-link' },
    ];
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); onClose(); }
            if (event.key === 'Escape' && isOpen) onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);
    if (!isOpen) return null;
    return (
        <div className="modal-overlay" onClick={onClose} role="presentation">
            <div className="palette-modal" onClick={(event: ReactMouseEvent<HTMLDivElement>) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="command-palette-title">
                <h2 id="command-palette-title" className="sr-only">Command palette</h2>
                <input autoFocus className="palette-input" aria-label="Search governed views" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} placeholder="Search governed views…" />
                <div className="palette-list">
                    {actions.filter((item) => item.label.toLowerCase().includes(query.toLowerCase())).map((item) => (
                        <button className="palette-item" key={item.path} onClick={() => { navigate(item.path); onClose(); }}>{item.label}</button>
                    ))}
                </div>
            </div>
        </div>
    );
}

interface ArtifactRecord extends JsonRecord {
    artifact_id: string;
    digest: string;
    media_type: string;
    size_bytes: number;
    status: string;
}

interface EvidenceRecord extends JsonRecord {
    evidence_id: string;
    status: string;
    provenance?: JsonRecord;
    result?: JsonRecord;
    artifact_ref?: string | null;
}

interface AnalysisResponse extends JsonRecord {
    analysis_id: string;
    evidence: EvidenceRecord;
}

interface MeshViewerProps {
    artifact: ArtifactRecord;
    token: string;
}

function MeshViewer({ artifact, token }: MeshViewerProps) {
    const mountRef = useRef<HTMLDivElement | null>(null);
    const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');
    const [error, setError] = useState('');
    useEffect(() => {
        const mediaType = artifact.media_type;
        if (mediaType !== 'model/stl' && mediaType !== 'model/obj' && mediaType !== 'model/gltf-binary') {
            setStatus('unavailable');
            setError('This format is not browser-renderable in the reference viewer; measured evidence remains available below.');
            return undefined;
        }
        let disposed = false;
        const abortController = new AbortController();
        let disposeRenderer: (() => void) | undefined;
        setStatus('loading');
        setError('');
        const disposeObject = (object: import('three').Object3D): void => {
            object.traverse((child) => {
                const mesh = child as import('three').Mesh;
                if (!mesh.isMesh) return;
                mesh.geometry.dispose();
                if (Array.isArray(mesh.material)) mesh.material.forEach((item) => item.dispose());
                else mesh.material.dispose();
            });
        };
        const initialize = async (): Promise<void> => {
            const THREE = await import('three');
            if (disposed) return;
            const element = mountRef.current;
            if (!element) throw new Error('Mesh viewer mount is unavailable');
            const response = await fetch(`${API_ROOT}/api/v2/artifacts/${artifact.artifact_id}/content`, {
                headers: { Accept: mediaType, Authorization: `Bearer ${token}` },
                cache: 'no-store',
                signal: abortController.signal,
            });
            if (disposed) return;
            if (!response.ok) throw new Error(`Artifact content unavailable (${response.status})`);
            let object: import('three').Object3D;
            if (mediaType === 'model/stl') {
                const { STLLoader } = await import('three/examples/jsm/loaders/STLLoader.js');
                if (disposed) return;
                const source = await response.arrayBuffer();
                if (disposed) return;
                const parsedGeometry = new STLLoader().parse(source);
                if (disposed) {
                    parsedGeometry.dispose();
                    return;
                }
                parsedGeometry.computeVertexNormals();
                object = new THREE.Mesh(parsedGeometry, new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.15, roughness: 0.55, wireframe: false }));
            } else if (mediaType === 'model/obj') {
                const { OBJLoader } = await import('three/examples/jsm/loaders/OBJLoader.js');
                if (disposed) return;
                const loader = new OBJLoader();
                const source = await response.arrayBuffer();
                if (disposed) return;
                object = loader.parse(new TextDecoder().decode(source));
                if (disposed) {
                    disposeObject(object);
                    return;
                }
                object.traverse((child) => {
                    const mesh = child as import('three').Mesh;
                    if (!mesh.isMesh) return;
                    if (Array.isArray(mesh.material)) mesh.material.forEach((item) => item.dispose());
                    else mesh.material.dispose();
                    mesh.material = new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.15, roughness: 0.55 });
                });
            } else {
                const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js');
                if (disposed) return;
                const source = await response.arrayBuffer();
                if (disposed) return;
                const manager = new THREE.LoadingManager();
                manager.setURLModifier((url) => {
                    if (url.toLowerCase().startsWith('data:')) return url;
                    throw new Error('External glTF resources are disabled in the reference viewer');
                });
                const loader = new GLTFLoader(manager);
                object = await new Promise<import('three').Object3D>((resolve, reject) => {
                    loader.parse(source, '', (gltf) => resolve(gltf.scene), (reason) => reject(reason));
                });
                if (disposed) {
                    disposeObject(object);
                    return;
                }
            }
            if (disposed) {
                disposeObject(object);
                return;
            }
            const bounds = new THREE.Box3().setFromObject(object);
            if (bounds.isEmpty()) {
                disposeObject(object);
                throw new Error('Mesh contains no renderable geometry');
            }
            const center = bounds.getCenter(new THREE.Vector3());
            object.position.sub(center);
            const size = bounds.getSize(new THREE.Vector3());
            const scene = new THREE.Scene();
            const camera = new THREE.PerspectiveCamera(45, Math.max(element.clientWidth, 1) / Math.max(element.clientHeight, 1), 0.01, 100000);
            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            renderer.setSize(element.clientWidth, element.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            element.appendChild(renderer.domElement);
            scene.add(new THREE.AmbientLight(0xffffff, 1.7));
            const keyLight = new THREE.DirectionalLight(0x67e8f9, 2.2);
            keyLight.position.set(3, 5, 8);
            scene.add(keyLight);
            scene.add(new THREE.GridHelper(20, 20, 0x155e75, 0x0f172a));
            camera.position.set(0, 0, Math.max(size.length() * 1.8, 4));
            camera.lookAt(0, 0, 0);
            scene.add(object);
            const resize = () => {
                camera.aspect = Math.max(element.clientWidth, 1) / Math.max(element.clientHeight, 1);
                camera.updateProjectionMatrix();
                renderer.setSize(element.clientWidth, element.clientHeight);
            };
            let frame: number | undefined;
            const animate = () => {
                frame = requestAnimationFrame(animate);
                object.rotation.y += 0.004;
                renderer.render(scene, camera);
            };
            window.addEventListener('resize', resize);
            animate();
            setStatus('ready');
            disposeRenderer = () => {
                if (frame !== undefined) cancelAnimationFrame(frame);
                window.removeEventListener('resize', resize);
                disposeObject(object);
                renderer.dispose();
                if (element.contains(renderer.domElement)) element.removeChild(renderer.domElement);
            };
        };
        void initialize().catch((reason: unknown) => {
            if (!disposed) {
                setStatus('unavailable');
                setError(errorMessage(reason));
            }
        });
        return () => {
            disposed = true;
            abortController.abort();
            disposeRenderer?.();
        };
    }, [artifact.artifact_id, artifact.media_type, token]);
    return <div ref={mountRef} className="artifact-viewer" role="img" aria-label={`Read-only mesh viewer for ${artifact.artifact_id}`}>{status === 'loading' && <span className="muted">Loading source-backed mesh…</span>}{status === 'unavailable' && <span className="muted">{error || 'Mesh viewer unavailable; evidence remains authoritative.'}</span>}{status === 'ready' && <span className="viewer-badge">SOURCE DIGEST VERIFIED</span>}</div>;
}

function artifactMediaType(file: File): string {
    const declared = file.type.toLowerCase();
    if (['application/step', 'model/step', 'model/stl', 'model/obj', 'model/gltf+json', 'model/gltf-binary', 'image/png', 'image/jpeg'].includes(declared)) return declared;
    const extension = file.name.toLowerCase().split('.').pop() || '';
    return ({ stp: 'application/step', step: 'application/step', stl: 'model/stl', obj: 'model/obj', glb: 'model/gltf-binary', gltf: 'model/gltf+json', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' } as Record<string, string>)[extension] || 'application/octet-stream';
}

function EngineeringPage() {
    const { session } = useAuth();
    const { addToast } = useToast();
    const [file, setFile] = useState<File | null>(null);
    const [artifact, setArtifact] = useState<ArtifactRecord | null>(null);
    const [evidence, setEvidence] = useState<EvidenceRecord | null>(null);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState('');
    const submit = async (): Promise<void> => {
        const token = session?.access_token;
        if (!token || !file) return;
        setPending(true);
        setError('');
        setEvidence(null);
        const mediaType = artifactMediaType(file);
        try {
            const uploaded = await api.upload<ArtifactRecord>('/api/v2/artifacts', token, file, mediaType);
            setArtifact(uploaded);
            const image = mediaType === 'image/png' || mediaType === 'image/jpeg';
            const analyzed = await api.post<AnalysisResponse>(image ? '/api/v2/vision/analyze' : '/api/v2/cad/analyze', token, { artifact_id: uploaded.artifact_id, analysis_kind: image ? 'metadata' : 'geometry' });
            setEvidence(analyzed.evidence);
            addToast('Artifact analyzed with source provenance', 'success');
        } catch (reason: unknown) {
            setError(errorMessage(reason));
            addToast('Artifact was rejected or unavailable', 'error');
        } finally {
            setPending(false);
        }
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">🧩 Engineering / visual evidence</h2>
            <div className="notice">Uploads remain quarantined. Geometry facts are measured from source bytes; FEA, thermal safety, semantic labels, and manufacturing claims are not inferred.</div>
            <div className="card">
                <div className="card-header">SOURCE ARTIFACT</div>
                <div className="artifact-upload-row"><input aria-label="Choose CAD or image artifact" type="file" accept=".step,.stp,.stl,.obj,.glb,.gltf,.png,.jpg,.jpeg" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(''); }} /><button className="btn primary" disabled={!file || pending} onClick={submit}>{pending ? 'ANALYZING…' : 'UPLOAD + ANALYZE'}</button></div>
                {error && <p className="error-text" role="alert">{error}</p>}
                {artifact && <div className="artifact-meta"><StatusBadge status={artifact.status}>{artifact.status}</StatusBadge><span>{artifact.media_type}</span><span>{artifact.size_bytes} bytes</span><span>source digest: <code>{artifact.digest}</code></span></div>}
            </div>
            {artifact && (artifact.media_type === 'model/stl' || artifact.media_type === 'model/obj' || artifact.media_type === 'model/gltf-binary') && session?.access_token && <div className="card"><div className="card-header">READ-ONLY MESH VIEWER</div><MeshViewer artifact={artifact} token={session.access_token} /></div>}
            {evidence && <div className="card"><div className="card-header">IMMUTABLE ANALYSIS EVIDENCE · {evidence.evidence_id}</div><div className="state-row"><StatusBadge status={evidence.status}>{evidence.status}</StatusBadge><span className="muted">artifact: {evidence.artifact_ref || '—'}</span></div><p className="disclosure">{displayValue(evidence.provenance?.disclosure, 'Adapter disclosure unavailable.')}</p><pre className="code-out" aria-label="Analysis result">{JSON.stringify(evidence.result, null, 2)}</pre></div>}
        </div>
    );
}

function OverviewPage() {
    const { session } = useAuth();
    const snapshot = useTelemetry();
    const feed = useEventFeed();
    const { addToast } = useToast();
    const [capabilities, setCapabilities] = useState<Capability[]>([]);
    const [result, setResult] = useState<RunResponse | null>(null);
    useEffect(() => {
        const token = session?.access_token;
        if (!token) return undefined;
        void api.get<CapabilitiesResponse>('/api/v2/capabilities', token).then((data) => setCapabilities(data.capabilities ?? [])).catch(() => {});
        return undefined;
    }, [session?.access_token]);
    const observe = async (): Promise<void> => {
        const token = session?.access_token;
        if (!token) return;
        try {
            const intent = await api.post<IntentResponse>('/api/v2/intents', token, {
                source_kind: 'text', source_text: 'show system status',
                goal: { verb: 'observe', object: 'system.status', parameters: {} },
                requested_mode: 'observe', requested_risk_tier: 'R0',
            });
            const plan = await api.post<PlanResponse>(`/api/v2/intents/${intent.intent_id}/plan`, token);
            const run = await api.post<RunResponse>(`/api/v2/plans/${plan.plan_id}/run`, token, {}, { 'Idempotency-Key': `observe-${Date.now()}` });
            setResult(run);
            addToast('Read-only observation completed', 'success');
        } catch (error: unknown) {
            setResult({ status: 'unavailable', disclosure: errorMessage(error) });
            addToast('Observation unavailable', 'error');
        }
    };
    return (
        <div className="page route-fade">
            <div className="page-heading"><h2 className="page-title">⚡ Governed control-plane overview</h2><StatusBadge status={feed.status}>{feed.status.toUpperCase()}</StatusBadge></div>
            <div className="notice"><strong>Reference profile disclosure:</strong> this surface reports registry and evidence state. It does not claim that the legacy catalog is live, and it exposes no direct mutation controls.</div>
            <div className="telemetry-grid">
                <div className="tele-card"><div className="tele-label">TENANT</div><div className="tele-val">{session?.tenant_id ?? '—'}</div><div className="muted">scoped session</div></div>
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
            <div className="card"><div className="card-header">DURABLE EVENT FEED</div>{feed.events.length ? feed.events.slice(-8).map((event, index) => <div className="log-line" key={event.event_id ?? `${event.sequence ?? 'event'}-${index}`}>{displayValue(event.sequence)} · {displayValue(event.type)} · {displayValue(event.payload?.status ?? event.aggregate?.id)}</div>) : <p className="muted">No events received in this session.</p>}</div>
        </div>
    );
}

function JarvisPage() {
    const { session } = useAuth();
    const [messages, setMessages] = useState<Message[]>([{ speaker: 'J.A.R.V.I.S.', text: 'Authenticated. Observe and Assist are available; no external write is enabled.', cls: 'jarvis-msg' }]);
    const [input, setInput] = useState('');
    const [listening, setListening] = useState(false);
    const [voiceInput, setVoiceInput] = useState(false);
    const chatRef = useRef<HTMLDivElement | null>(null);
    const { addToast } = useToast();
    useEffect(() => { if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight; }, [messages]);
    const send = async (): Promise<void> => {
        const text = input.trim();
        if (!text) return;
        const token = session?.access_token;
        if (!token) return;
        setInput('');
        setMessages((items) => [...items, { speaker: 'USER', text, cls: 'user-msg' }]);
        try {
            const intent = await api.post<IntentResponse>('/api/v2/intents', token, {
                source_kind: voiceInput ? 'voice' : 'text', source_text: text,
                goal: { verb: 'observe', object: 'system.status', parameters: {} },
                requested_mode: 'assist', requested_risk_tier: 'R0',
            });
            const plan = await api.post<PlanResponse>(`/api/v2/intents/${intent.intent_id}/plan`, token);
            const run = await api.post<RunResponse>(`/api/v2/plans/${plan.plan_id}/run`, token, {}, { 'Idempotency-Key': `jarvis-${Date.now()}` });
            setMessages((items) => [...items, { speaker: 'J.A.R.V.I.S.', text: `Observation ${displayValue(run.status, 'unavailable')}. Evidence is ${displayValue(run.evidence?.status, 'unavailable')}. ${displayValue(run.evidence?.provenance?.disclosure, '')}`, cls: 'jarvis-msg' }]);
            addToast('Assistive observation recorded', 'success');
        } catch (error: unknown) {
            setMessages((items) => [...items, { speaker: 'J.A.R.V.I.S.', text: `Request not executed: ${errorMessage(error)}`, cls: 'jarvis-msg' }]);
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
        recognition.onresult = (event: SpeechRecognitionEventLike) => setInput(event.results[0][0].transcript);
        recognition.start();
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">🤖 J.A.R.V.I.S. Observe / Assist</h2>
            <div className="notice">Voice transcription is an input signal only. It does not establish identity or approval.</div>
            <div className="card">
                <div className="chat-window" ref={chatRef} role="log" aria-live="polite" aria-label="J.A.R.V.I.S. conversation">
                    {messages.map((message, index) => <div className={`chat-msg ${message.cls}`} key={`${message.speaker}-${index}`}><span className="speaker">{message.speaker}</span><span className="text">{message.text}</span></div>)}
                </div>
                <div className="chat-input-row"><input className="chat-input" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && send()} placeholder="Ask for a read-only observation…" /><button className={`btn secondary small ${listening ? 'listening' : ''}`} onClick={startVoiceInput}>{listening ? '🔴 Listening…' : '🎤 Voice input'}</button><button className="btn primary" onClick={send}>SUBMIT INTENT</button></div>
            </div>
        </div>
    );
}

function SubsystemsPage() {
    const { session } = useAuth();
    const [capabilities, setCapabilities] = useState<Capability[]>([]);
    useEffect(() => {
        const token = session?.access_token;
        if (!token) return undefined;
        void api.get<CapabilitiesResponse>('/api/v2/capabilities', token).then((data) => setCapabilities(data.capabilities ?? [])).catch(() => {});
        return undefined;
    }, [session?.access_token]);
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
    const [connectors, setConnectors] = useState<JsonRecord | null>(null);
    useEffect(() => {
        const token = session?.access_token;
        if (!token) return undefined;
        void api.get<JsonRecord>('/api/v2/connectors', token).then(setConnectors).catch(() => {});
        return undefined;
    }, [session?.access_token]);
    return (
        <div className="page route-fade">
            <h2 className="page-title">🛡 Safety cockpit</h2>
            <div className="card"><div className="card-header">HIGH-IMPACT CAPABILITIES</div><div className="safety-grid"><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>Physical actuation</h3><p className="disclosure">No actuator endpoint exists in the reference profile.</p></div><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>Research compiler / RSI</h3><p className="disclosure">No runtime code generation or hot swap is exposed.</p></div><div><StatusBadge status="disabled">DISABLED</StatusBadge><h3>External egress</h3><p className="disclosure">Connector calls require a separately configured egress broker.</p></div></div></div>
            <div className="card"><div className="card-header">CONNECTOR STATUS</div><pre className="code-out" aria-live="polite" aria-busy={!connectors}>{connectors ? JSON.stringify(connectors, null, 2) : 'Loading…'}</pre></div>
        </div>
    );
}

const DEFAULT_MCP = JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 1 }, null, 2);

function MCPPage() {
    const { session } = useAuth();
    const [input, setInput] = useState(DEFAULT_MCP);
    const [response, setResponse] = useState('');
    const { addToast } = useToast();
    const send = async (): Promise<void> => {
        try {
            const parsed: unknown = JSON.parse(input);
            if (!isJsonRecord(parsed)) throw new Error('MCP request must be a JSON object');
            const needsKey = parsed.method === 'tools/call';
            const token = session?.access_token;
            if (!token) throw new Error('Authenticated session is unavailable');
            const result = await api.post<JsonRecord>('/api/v2/mcp', token, parsed, needsKey ? { 'Idempotency-Key': `mcp-${Date.now()}` } : {});
            setResponse(JSON.stringify(result, null, 2));
            addToast('Governed MCP request completed', 'success');
        } catch (error: unknown) {
            setResponse(error instanceof ApiError ? JSON.stringify(error.payload, null, 2) : `Invalid request: ${errorMessage(error)}`);
            addToast('MCP request rejected', 'error');
        }
    };
    return <div className="page route-fade"><h2 className="page-title">🔌 Governed MCP JSON-RPC 2.0</h2><div className="notice">Discovery is read-only. Tool calls use the same identity, policy, idempotency, audit, and evidence path as REST.</div><div className="card"><div className="card-header"><label htmlFor="mcp-request">REQUEST</label></div><textarea id="mcp-request" className="mcp-textarea" value={input} onChange={(event) => setInput(event.target.value)} rows={8} /><button className="btn primary" onClick={send}>DISPATCH</button></div><div className="card"><div className="card-header">RESPONSE</div><pre className="code-out" aria-live="polite">{response || 'Awaiting dispatch…'}</pre></div></div>;
}

// =================================================================== AI Futures pages
interface AgentRecord {
    agent_id: string;
    name: string;
    description: string;
    status: string;
    created_at: string;
}

interface AgentVersionRecord {
    version_id: string;
    agent_id: string;
    version: string;
    status: string;
    system_prompt: string;
    allowed_tools: string[];
    model_policy: Record<string, unknown>;
    budget: Record<string, number>;
    digest: string;
    created_at: string;
    published_at: string | null;
}

interface AgentExecutionRecord {
    execution_id: string;
    tenant_id: string;
    principal_id: string;
    agent_id: string;
    agent_version_id: string;
    task: string;
    status: string;
    plan: { steps?: unknown[]; disclosures?: string[] } & Record<string, unknown>;
    model: { mode: string; model: string; status: string; disclosures?: string[] } & Record<string, unknown>;
    knowledge_run_id: string | null;
    ticket_run_id: string | null;
    result: Record<string, unknown>;
    error: Record<string, unknown>;
    created_at: string;
    finished_at: string | null;
}

interface AgentApprovalRecord {
    approval_id: string;
    execution_id: string;
    tool_id: string;
    tool_version: string;
    action_digest: string;
    decision: string;
    reason: string;
    approver_id: string | null;
    created_at: string;
    resolved_at: string | null;
    expires_at: string;
}

interface ModelStatus {
    mode: string;
    model: string;
    status: string;
    disclosures: string[];
}

function useAgentList(token: string | null) {
    return useApi<AgentRecord[]>('/api/v2/agents', token);
}

function useExecutions(token: string | null) {
    return useApi<AgentExecutionRecord[]>('/api/v2/agent-approvals?decision=pending', token);
}

function useApprovals(token: string | null) {
    return useApi<AgentApprovalRecord[]>('/api/v2/agent-approvals?decision=pending', token);
}

function useModelStatus(token: string | null) {
    return useApi<ModelStatus>('/api/v2/models/status', token);
}

function useAudit(token: string | null, filters: { execution_id?: string; event_type?: string; sensitivity?: string }) {
    const params = new URLSearchParams();
    if (filters.execution_id) params.set('execution_id', filters.execution_id);
    if (filters.event_type) params.set('event_type', filters.event_type);
    if (filters.sensitivity) params.set('sensitivity', filters.sensitivity);
    const path = params.toString() ? `/api/v2/audit?${params}` : '/api/v2/audit';
    return useApi<JsonRecord[]>(path, token);
}

function useApi<T>(path: string, token: string | null) {
    const [data, setData] = useState<T | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        if (!token) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        api.get<T>(path, token)
            .then((result) => { if (!cancelled) setData(result); })
            .catch((err) => { if (!cancelled) setError(errorMessage(err)); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [path, token]);
    return { data, error, loading };
}

function AgentsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const agents = useApi<AgentRecord[]>('/api/v2/agents', token);
    const [creating, setCreating] = useState(false);
    const [name, setName] = useState('demo');
    const [description, setDescription] = useState('Local deterministic agent');
    const { addToast } = useToast();
    const create = async () => {
        if (!token) return;
        try {
            await api.post('/api/v2/agents', token, { name: name, description: description });
            addToast('Agent created (initial draft)', 'success');
            setCreating(false);
            window.location.reload();
        } catch (error) {
            addToast(`Failed: ${errorMessage(error)}`, 'error');
        }
    };
    return <div className="page route-fade">
        <h2 className="page-title">🧠 AI Futures Agents</h2>
        <div className="notice">Agents are scoped to your tenant. The deterministic simulator is the default model. External services are disabled.</div>
        <div className="card">
            <div className="card-header">
                <span>Registered agents</span>
                <button className="btn primary small" onClick={() => setCreating((value) => !value)}>{creating ? 'Cancel' : 'New agent'}</button>
            </div>
            {creating && <div className="form-row">
                <label htmlFor="agent-name">Name</label>
                <input id="agent-name" value={name} onChange={(event) => setName(event.target.value)} />
                <label htmlFor="agent-desc">Description</label>
                <input id="agent-desc" value={description} onChange={(event) => setDescription(event.target.value)} />
                <button className="btn primary" onClick={create}>Create draft</button>
            </div>}
            {agents.loading && <div className="empty">Loading…</div>}
            {agents.error && <div className="error">{agents.error}</div>}
            {agents.data && agents.data.length === 0 && <div className="empty">No agents yet. Use “New agent” to create a draft.</div>}
            {agents.data && agents.data.length > 0 && <table className="data-table"><thead><tr><th>Name</th><th>Status</th><th>Description</th><th>Created</th></tr></thead><tbody>
                {agents.data.map((agent) => <tr key={agent.agent_id}><td>{agent.name}</td><td><StatusBadge status={agent.status}>{agent.status}</StatusBadge></td><td>{agent.description || '—'}</td><td>{agent.created_at}</td></tr>)}
            </tbody></table>}
        </div>
    </div>;
}

function ExecutionsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [executionId, setExecutionId] = useState('');
    const effectiveExecutionId = executionId.trim();
    const path = effectiveExecutionId ? `/api/v2/agent-executions/${encodeURIComponent(effectiveExecutionId)}` : '';
    const execution = useApi<AgentExecutionRecord>(path, (path && token ? token : null) as string | null);
    return <div className="page route-fade">
        <h2 className="page-title">⏱ Executions</h2>
        <div className="notice">Executions and approvals are tenant-scoped. Pending approvals and rejected runs are displayed alongside completed runs.</div>
        <div className="card">
            <div className="card-header">Inspect execution</div>
            <div className="form-row">
                <label htmlFor="exec-id">Execution id</label>
                <input id="exec-id" value={executionId} onChange={(event) => setExecutionId(event.target.value)} placeholder="aexec_…" />
            </div>
            {execution.data && <div className="execution-detail">
                <div><strong>Status:</strong> <StatusBadge status={execution.data.status}>{execution.data.status}</StatusBadge></div>
                <div><strong>Task:</strong> {execution.data.task}</div>
                <div><strong>Model:</strong> {String(execution.data.model.mode ?? '—')} · {String(execution.data.model.model ?? '—')}</div>
                <div><strong>Knowledge run:</strong> {execution.data.knowledge_run_id ?? '—'}</div>
                <div><strong>Ticket run:</strong> {execution.data.ticket_run_id ?? '—'}</div>
                <pre className="code-out">{JSON.stringify(execution.data.plan, null, 2)}</pre>
                {execution.data.error && Object.keys(execution.data.error).length > 0 && <div className="error">Error: {JSON.stringify(execution.data.error)}</div>}
                {execution.data.result && Object.keys(execution.data.result).length > 0 && <pre className="code-out">{JSON.stringify(execution.data.result, null, 2)}</pre>}
            </div>}
        </div>
        <div className="card">
            <div className="card-header">Recent pending approvals</div>
            <ApprovalsList token={token} onSelectExecution={(id) => setExecutionId(id)} />
        </div>
    </div>;
}

function ApprovalsList({ token, onSelectExecution }: { token: string | null, onSelectExecution?: (id: string) => void }) {
    const approvals = useApi<AgentApprovalRecord[]>('/api/v2/agent-approvals?decision=pending', token);
    if (approvals.data && approvals.data.length === 0) return <div className="empty">No pending approvals.</div>;
    if (!approvals.data) return <div className="empty">Loading…</div>;
    return <table className="data-table"><thead><tr><th>Approval</th><th>Execution</th><th>Tool</th><th>Action digest</th><th>Expires</th></tr></thead><tbody>
        {approvals.data.map((approval) => <tr key={approval.approval_id}>
            <td className="mono">{approval.approval_id}</td>
            <td>{onSelectExecution ? <button className="btn secondary small" onClick={() => onSelectExecution(approval.execution_id)}>{approval.execution_id}</button> : approval.execution_id}</td>
            <td>{approval.tool_id}@{approval.tool_version}</td>
            <td className="mono">{approval.action_digest.slice(0, 16)}…</td>
            <td>{approval.expires_at}</td>
        </tr>)}
    </tbody></table>;
}

function ApprovalsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const approvals = useApi<AgentApprovalRecord[]>('/api/v2/agent-approvals?decision=pending', token);
    const [reason, setReason] = useState('Operator-approved demo write');
    const { addToast } = useToast();
    const decide = async (approval: AgentApprovalRecord, decision: 'approved' | 'rejected') => {
        if (!token) return;
        const path = decision === 'approved'
            ? `/api/v2/agent-approvals/${approval.approval_id}/approve`
            : `/api/v2/agent-approvals/${approval.approval_id}/reject`;
        try {
            await api.post(path, token, { reason });
            addToast(`Approval ${decision}`, 'success');
            window.location.reload();
        } catch (error) {
            addToast(`Failed: ${errorMessage(error)}`, 'error');
        }
    };
    return <div className="page route-fade">
        <h2 className="page-title">🛂 Pending approvals</h2>
        <div className="notice">Each approval is bound to the exact tenant, execution, agent version, tool, version, and action digest. Replays return the original durable result.</div>
        <div className="form-row">
            <label htmlFor="approval-reason">Decision reason (mandatory)</label>
            <textarea id="approval-reason" rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
        {approvals.data && approvals.data.length === 0 && <div className="empty">No pending approvals. Start an execution to populate this queue.</div>}
        {approvals.data && approvals.data.length > 0 && <table className="data-table"><thead><tr><th>Approval</th><th>Execution</th><th>Tool</th><th>Action digest</th><th>Expires</th><th>Decision</th></tr></thead><tbody>
            {approvals.data.map((approval) => <tr key={approval.approval_id}>
                <td className="mono">{approval.approval_id}</td>
                <td className="mono">{approval.execution_id}</td>
                <td>{approval.tool_id}@{approval.tool_version}</td>
                <td className="mono">{approval.action_digest.slice(0, 16)}…</td>
                <td>{approval.expires_at}</td>
                <td>
                    <button className="btn primary small" onClick={() => decide(approval, 'approved')}>Approve</button>
                    {' '}
                    <button className="btn secondary small" onClick={() => decide(approval, 'rejected')}>Reject</button>
                </td>
            </tr>)}
        </tbody></table>}
    </div>;
}

function AuditPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [executionId, setExecutionId] = useState('');
    const [eventType, setEventType] = useState('');
    const [sensitivity, setSensitivity] = useState('');
    const audit = useAudit(token, { execution_id: executionId, event_type: eventType, sensitivity });
    return <div className="page route-fade">
        <h2 className="page-title">📜 Tenant audit</h2>
        <div className="notice">Filter the tenant audit stream. The transport is not read directly from the browser; this view uses the REST query projection.</div>
        <div className="form-row">
            <label htmlFor="audit-exec">Execution id</label>
            <input id="audit-exec" value={executionId} onChange={(event) => setExecutionId(event.target.value)} />
            <label htmlFor="audit-type">Event type</label>
            <input id="audit-type" value={eventType} onChange={(event) => setEventType(event.target.value)} placeholder="agent.execution.requested" />
            <label htmlFor="audit-sensitivity">Sensitivity</label>
            <input id="audit-sensitivity" value={sensitivity} onChange={(event) => setSensitivity(event.target.value)} placeholder="tenant" />
        </div>
        {audit.data && audit.data.length === 0 && <div className="empty">No matching audit records.</div>}
        {audit.data && audit.data.length > 0 && <table className="data-table"><thead><tr><th>Action</th><th>Target</th><th>Outcome</th><th>Execution</th><th>Created</th></tr></thead><tbody>
            {audit.data.map((record) => <tr key={String(record.audit_id)}>
                <td>{String(record.action ?? '—')}</td>
                <td className="mono">{String(record.target ?? '—')}</td>
                <td>{String(record.outcome ?? '—')}</td>
                <td className="mono">{String(record.execution_id ?? '—')}</td>
                <td>{String(record.created_at ?? '—')}</td>
            </tr>)}
        </tbody></table>}
    </div>;
}

function ModelsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const status = useModelStatus(token);
    return <div className="page route-fade">
        <h2 className="page-title">🤖 Model policy</h2>
        <div className="notice">The control plane never contacts a hosted model. A loopback Ollama endpoint may be enabled by the operator; model output is treated as an untrusted proposal.</div>
        {status.data && <div className="card">
            <div className="card-header"><StatusBadge status={status.data.status}>{status.data.status}</StatusBadge> {status.data.mode} · {status.data.model}</div>
            {(status.data.disclosures ?? []).map((line) => <div key={line} className="disclosure">• {line}</div>)}
        </div>}
        {!status.data && <div className="empty">Loading model status…</div>}
    </div>;
}

function MemoryPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [query, setQuery] = useState('');
    const [memoryType, setMemoryType] = useState('');
    const [limit] = useState(50);
    const [showCreate, setShowCreate] = useState(false);
    const [content, setContent] = useState('');
    const [scope, setScope] = useState('workspace');
    const [projectId, setProjectId] = useState('');
    const { addToast } = useToast();
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (memoryType) params.set('memory_type', memoryType);
    params.set('limit', String(limit));
    const memory = useApi<JsonRecord[]>(`/api/v2/memory/search?${params}`, token && (query || memoryType) ? token : null);
    const create = async (): Promise<void> => {
        if (!token || !content.trim()) return;
        try {
            await api.post('/api/v2/memory', token, { content: content.trim(), scope, project_id: projectId || undefined, memory_type: 'fact' });
            addToast('Memory created', 'success');
            setContent('');
            setProjectId('');
            setShowCreate(false);
        } catch (error) {
            addToast(`Failed: ${errorMessage(error)}`, 'error');
        }
    };
    const remove = async (memoryId: string): Promise<void> => {
        if (!token) return;
        try {
            await api.request(`/api/v2/memory/${memoryId}`, { token, method: 'DELETE' });
            addToast('Memory deleted', 'success');
        } catch (error) {
            addToast(`Failed: ${errorMessage(error)}`, 'error');
        }
    };
    return <div className="page route-fade">
        <h2 className="page-title">💾 Memory browser</h2>
        <div className="notice">Memory is tenant-scoped and scope-checked. Project memory requires project_id. Stale or expired entries are excluded from search results unless explicitly included by the backend.</div>
        <div className="card">
            <div className="card-header">Search memory</div>
            <div className="form-row">
                <label htmlFor="mem-query">Query</label>
                <input id="mem-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="search terms…" />
                <label htmlFor="mem-type">Type</label>
                <input id="mem-type" value={memoryType} onChange={(event) => setMemoryType(event.target.value)} placeholder="fact / conversation" />
                <button className="btn primary small" onClick={() => {}}>Search</button>
            </div>
            {memory.loading && <div className="empty">Loading…</div>}
            {memory.error && <div className="error">{memory.error}</div>}
            {memory.data && memory.data.length === 0 && <div className="empty">No memory items match the query.</div>}
            {memory.data && memory.data.length > 0 && <table className="data-table"><thead><tr><th>ID</th><th>Type</th><th>Content</th><th>Scope</th><th>Created</th><th></th></tr></thead><tbody>
                {memory.data.map((item) => <tr key={String(item.memory_id)}>
                    <td className="mono">{String(item.memory_id).slice(0, 16)}…</td>
                    <td>{String(item.memory_type ?? '—')}</td>
                    <td>{String(item.content ?? '').slice(0, 120)}</td>
                    <td>{String(item.scope ?? '—')}{item.project_id ? ` / ${String(item.project_id)}` : ''}</td>
                    <td>{String(item.created_at ?? '—')}</td>
                    <td><button className="btn secondary small" onClick={() => remove(String(item.memory_id))}>Delete</button></td>
                </tr>)}
            </tbody></table>}
        </div>
        <div className="card">
            <div className="card-header">Create memory</div>
            {showCreate ? <div className="form-row">
                <label htmlFor="mem-content">Content</label>
                <textarea id="mem-content" rows={3} value={content} onChange={(event) => setContent(event.target.value)} />
                <label htmlFor="mem-scope">Scope</label>
                <select id="mem-scope" value={scope} onChange={(event) => setScope(event.target.value)}>
                    <option value="workspace">workspace</option>
                    <option value="project">project</option>
                </select>
                {scope === 'project' && <><label htmlFor="mem-project">Project ID</label><input id="mem-project" value={projectId} onChange={(event) => setProjectId(event.target.value)} /></>}
                <button className="btn primary" onClick={create}>Create</button>
            </div> : <button className="btn secondary" onClick={() => setShowCreate(true)}>New memory item</button>}
        </div>
    </div>;
}

function GovernancePage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const policies = useApi<JsonRecord>('/api/v2/governance/policies', token);
    const approvals = useApi<JsonRecord>('/api/v2/governance/approvals', token);
    const policyList = (policies.data?.policies ?? []) as any[];
    const agentApprovals = (approvals.data?.agent_approvals ?? []) as any[];
    const legacyApprovals = (approvals.data?.legacy_approvals ?? []) as any[];
    return <div className="page route-fade">
        <h2 className="page-title">🛡 Governance</h2>
        <div className="notice">Policy, capability, and approval visibility. The control plane never bypasses policy; every tool call is mediated by the registry and policy engine.</div>
        <div className="card">
            <div className="card-header">Capability policies</div>
            {policyList.length === 0 && <div className="empty">No policies registered.</div>}
            {policyList.length > 0 && <table className="data-table"><thead><tr><th>Capability</th><th>Tool</th><th>Risk</th><th>Scopes</th><th>Egress</th><th>Side effects</th></tr></thead><tbody>
                {policyList.map((policy) => <tr key={String(policy.capability_id)}>
                    <td className="mono">{String(policy.capability_id)}</td>
                    <td>{String(policy.tool_id)}</td>
                    <td><StatusBadge status={String(policy.risk_tier)}>{String(policy.risk_tier)}</StatusBadge></td>
                    <td>{(policy.required_scopes ?? []).map((scope: string) => <code key={scope}>{scope}</code>)}</td>
                    <td>{String(policy.network_egress)}</td>
                    <td>{String(policy.side_effects?.join(', ') ?? '—')}</td>
                </tr>)}
            </tbody></table>}
            {policies.error && <div className="error">{policies.error}</div>}
        </div>
        <div className="card">
            <div className="card-header">Pending approvals</div>
            {agentApprovals.length === 0 && legacyApprovals.length === 0 && <div className="empty">No pending approvals.</div>}
            {(agentApprovals.length > 0 || legacyApprovals.length > 0) && <table className="data-table"><thead><tr><th>Type</th><th>ID</th><th>Execution / Plan</th><th>Status</th></tr></thead><tbody>
                {agentApprovals.map((approval) => <tr key={String(approval.approval_id)}>
                    <td>agent</td>
                    <td className="mono">{String(approval.approval_id)}</td>
                    <td className="mono">{String(approval.execution_id)}</td>
                    <td><StatusBadge status={String(approval.decision)}>{String(approval.decision)}</StatusBadge></td>
                </tr>)}
                {legacyApprovals.map((approval) => <tr key={String(approval.approval_id)}>
                    <td>legacy</td>
                    <td className="mono">{String(approval.approval_id)}</td>
                    <td className="mono">{String(approval.plan_id)}</td>
                    <td><StatusBadge status={String(approval.status)}>{String(approval.status)}</StatusBadge></td>
                </tr>)}
            </tbody></table>}
            {approvals.error && <div className="error">{approvals.error}</div>}
        </div>
    </div>;
}

function TelemetryPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const telemetry = useApi<JsonRecord>('/api/v2/telemetry', token);
    const data = telemetry.data as Record<string, any> | null;
    const processData = data?.process as Record<string, any> | undefined;
    const diskData = data?.disk as Record<string, any> | undefined;
    return <div className="page route-fade">
        <h2 className="page-title">📊 Telemetry</h2>
        <div className="notice">Local process and disk telemetry for the control-plane runtime. This is not public ingress telemetry.</div>
        {data && <div className="telemetry-grid">
            <div className="tele-card"><div className="tele-label">PID</div><div className="tele-val">{String(processData?.pid ?? '—')}</div></div>
            <div className="tele-card"><div className="tele-label">CPU %</div><div className="tele-val">{String(processData?.cpu_percent ?? '—')}</div></div>
            <div className="tele-card"><div className="tele-label">MEM RSS</div><div className="tele-val">{formatBytes(processData?.memory_rss_bytes ?? 0)}</div></div>
            <div className="tele-card"><div className="tele-label">MEM VMS</div><div className="tele-val">{formatBytes(processData?.memory_vms_bytes ?? 0)}</div></div>
            <div className="tele-card"><div className="tele-label">DISK TOTAL</div><div className="tele-val">{formatBytes(diskData?.total_bytes ?? 0)}</div></div>
            <div className="tele-card"><div className="tele-label">DISK FREE</div><div className="tele-val">{formatBytes(diskData?.free_bytes ?? 0)}</div></div>
        </div>}
        {!data && <div className="empty">Loading telemetry…</div>}
        {telemetry.error && <div className="error">{telemetry.error}</div>}
        <div className="disclosure">{String(data?.disclosure ?? '')}</div>
    </div>;
}

function SettingsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const settings = useApi<JsonRecord>('/api/v2/settings', token);
    const data = settings.data as Record<string, any> | null;
    return <div className="page route-fade">
        <h2 className="page-title">⚙️ Runtime settings</h2>
        <div className="notice">The reference profile exposes read-only runtime settings. Mutation requires operator-level configuration outside the cockpit.</div>
        {data && <div className="card">
            <div className="card-header">Configuration</div>
            <table className="data-table"><tbody>
                {Object.entries(data).filter(([key]) => key !== 'disclosure').map(([key, value]) => <tr key={key}>
                    <td><strong>{key}</strong></td>
                    <td>{String(value ?? '—')}</td>
                </tr>)}
            </tbody></table>
            <div className="disclosure">{String(data?.disclosure ?? '')}</div>
        </div>}
        {!data && <div className="empty">Loading settings…</div>}
        {settings.error && <div className="error">{settings.error}</div>}
    </div>;
}

function formatBytes(value: number): string {
    if (value <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    const scaled = value / Math.pow(1024, exponent);
    return `${scaled.toFixed(1)} ${units[exponent]}`;
}

function DoThisPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [planId, setPlanId] = useState('');
    const [idempotencyKey, setIdempotencyKey] = useState('');
    const [result, setResult] = useState<RunResponse | null>(null);
    const [plan, setPlan] = useState<JsonRecord | null>(null);
    const { addToast } = useToast();
    const loadPlan = async (): Promise<void> => {
        if (!token || !planId.trim()) return;
        try {
            const data = await api.get<JsonRecord>(`/api/v2/plans/${encodeURIComponent(planId.trim())}`, token);
            setPlan(data);
        } catch (error: unknown) {
            setPlan(null);
            addToast('Plan not found or unavailable', 'error');
        }
    };
    const runPlan = async (): Promise<void> => {
        if (!token || !planId.trim()) return;
        try {
            const key = idempotencyKey.trim() || `do-this-${Date.now()}`;
            const run = await api.post<RunResponse>(`/api/v2/plans/${encodeURIComponent(planId.trim())}/run`, token, {}, { 'Idempotency-Key': key });
            setResult(run);
            addToast('Plan run recorded', 'success');
        } catch (error: unknown) {
            setResult({ status: 'unavailable', disclosure: errorMessage(error) });
            addToast('Plan run rejected', 'error');
        }
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">🛠 Do This</h2>
            <div className="notice">Risk-bearing plans require an exact plan digest, approval when policy demands, and an idempotency key. The reference profile disables R2-R5 execution unless a separately governed worker exists.</div>
            <div className="card">
                <div className="card-header">REVIEW PLAN BEFORE ACTION</div>
                <div className="form-row">
                    <label htmlFor="plan-id">Plan ID</label>
                    <input id="plan-id" value={planId} onChange={(event) => { setPlanId(event.target.value); setPlan(null); setResult(null); }} placeholder="pln_…" />
                    <button className="btn secondary small" onClick={loadPlan} disabled={!planId.trim()}>LOAD PLAN</button>
                </div>
                {plan && <div className="state-row"><StatusBadge status={String(plan.status ?? 'unknown')}>{String(plan.status ?? 'unknown')}</StatusBadge><span className="muted">digest: {displayValue(plan.digest, '—')}</span></div>}
                {plan && <pre className="code-out">{JSON.stringify(plan, null, 2)}</pre>}
            </div>
            <div className="card">
                <div className="card-header">EXECUTE APPROVED PLAN</div>
                <div className="form-row">
                    <label htmlFor="idempotency-key">Idempotency key</label>
                    <input id="idempotency-key" value={idempotencyKey} onChange={(event) => setIdempotencyKey(event.target.value)} placeholder="client-generated unique key" />
                    <button className="btn primary" onClick={runPlan} disabled={!planId.trim()}>RUN PLAN</button>
                </div>
                {result && <div className="state-row"><StatusBadge status={String(result.status ?? 'unknown')}>{String(result.status ?? 'unknown')}</StatusBadge><span className="muted">evidence: {displayValue(result.evidence?.status, 'unavailable')}</span></div>}
                {result && <pre className="code-out">{JSON.stringify(result, null, 2)}</pre>}
            </div>
        </div>
    );
}

function AdvancedPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const capabilities = useApi<CapabilitiesResponse>('/api/v2/capabilities', token);
    const items = (capabilities.data?.capabilities ?? []) as Capability[];
    const disabled = items.filter((item) => item.availability === 'disabled' || item.runtime_state === 'offline');
    const research = items.filter((item) => item.availability === 'research_only');
    return (
        <div className="page route-fade">
            <h2 className="page-title">🧪 Advanced</h2>
            <div className="notice">Advanced mode does not grant implicit power. Disabled and research capabilities remain separated from verified runtime capabilities.</div>
            <div className="card">
                <div className="card-header">DISABLED CAPABILITIES · {disabled.length}</div>
                {disabled.length === 0 && <div className="empty">No disabled capabilities.</div>}
                {disabled.length > 0 && <table className="data-table"><thead><tr><th>Capability</th><th>Availability</th><th>Risk</th><th>Disclosure</th></tr></thead><tbody>
                    {disabled.map((capability) => <tr key={capability.capability_id}><td className="mono">{String(capability.capability_id)}</td><td><StatusBadge status={String(capability.availability)}>{String(capability.availability)}</StatusBadge></td><td>{String(capability.risk_tier)}</td><td>{String(capability.disclosure)}</td></tr>)}
                </tbody></table>}
            </div>
            <div className="card">
                <div className="card-header">RESEARCH CAPABILITIES · {research.length}</div>
                {research.length === 0 && <div className="empty">No research-only capabilities.</div>}
                {research.length > 0 && <table className="data-table"><thead><tr><th>Capability</th><th>Availability</th><th>Risk</th><th>Disclosure</th></tr></thead><tbody>
                    {research.map((capability) => <tr key={capability.capability_id}><td className="mono">{String(capability.capability_id)}</td><td><StatusBadge status={String(capability.availability)}>{String(capability.availability)}</StatusBadge></td><td>{String(capability.risk_tier)}</td><td>{String(capability.disclosure)}</td></tr>)}
                </tbody></table>}
            </div>
        </div>
    );
}

function HumanoidPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [simulation, setSimulation] = useState<JsonRecord | null>(null);
    useEffect(() => {
        if (!token) return undefined;
        void api.get<JsonRecord>('/api/v2/devices', token).then((data) => setSimulation({ ...data, disclosure: 'Humanoid mode is simulator-only in the reference profile. No actuator endpoint is exposed.' })).catch(() => setSimulation({ status: 'unavailable', disclosure: 'Humanoid simulator is unavailable in this runtime.' }));
        return undefined;
    }, [token]);
    return (
        <div className="page route-fade">
            <h2 className="page-title">🦾 Humanoid</h2>
            <div className="notice">Physical actuation is disabled in the reference profile. Humanoid mode exposes only visualization, telemetry fixtures, and simulation.</div>
            <div className="card">
                <div className="card-header">SIMULATOR / ADVISORY DISCLOSURE</div>
                <pre className="code-out">{simulation ? JSON.stringify(simulation, null, 2) : 'Loading…'}</pre>
            </div>
        </div>
    );
}

function MobileLinkPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [devices, setDevices] = useState<JsonRecord | null>(null);
    const [pairLabel, setPairLabel] = useState('');
    const [pairResult, setPairResult] = useState<JsonRecord | null>(null);
    const { addToast } = useToast();
    useEffect(() => {
        if (!token) return undefined;
        void api.get<JsonRecord>('/api/v2/devices', token).then(setDevices).catch(() => setDevices({ devices: [] }));
        return undefined;
    }, [token]);
    const pair = async (): Promise<void> => {
        if (!token || !pairLabel.trim()) return;
        try {
            const result = await api.post<JsonRecord>('/api/v2/devices', token, { device_label: pairLabel.trim() });
            setPairResult(result);
            addToast('Pairing challenge created', 'success');
            setPairLabel('');
        } catch (error: unknown) {
            addToast(`Pairing failed: ${errorMessage(error)}`, 'error');
        }
    };
    const revoke = async (deviceId: string): Promise<void> => {
        if (!token) return;
        try {
            await api.post(`/api/v2/devices/${encodeURIComponent(deviceId)}/revoke`, token);
            addToast('Device revoked', 'success');
            if (devices) setDevices({ ...devices, devices: (devices.devices as any[])?.filter((item: any) => item.device_id !== deviceId) ?? [] });
        } catch (error: unknown) {
            addToast(`Revoke failed: ${errorMessage(error)}`, 'error');
        }
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">📱 Mobile Link</h2>
            <div className="notice">Pairing uses a server-generated one-time challenge with short expiration. QR contents never contain reusable API secrets.</div>
            <div className="card">
                <div className="card-header">PAIR NEW DEVICE</div>
                <div className="form-row">
                    <label htmlFor="pair-label">Device label</label>
                    <input id="pair-label" value={pairLabel} onChange={(event) => setPairLabel(event.target.value)} placeholder="desk phone" />
                    <button className="btn primary" onClick={pair} disabled={!pairLabel.trim()}>CREATE CHALLENGE</button>
                </div>
                {pairResult && <pre className="code-out">{JSON.stringify(pairResult, null, 2)}</pre>}
            </div>
            <div className="card">
                <div className="card-header">REGISTERED DEVICES</div>
                {!devices && <div className="empty">Loading…</div>}
                {devices && (devices.devices as any[])?.length === 0 && <div className="empty">No registered devices.</div>}
                {devices && (devices.devices as any[])?.length > 0 && <table className="data-table"><thead><tr><th>Device</th><th>Status</th><th>Enrollment</th><th>Last seen</th><th></th></tr></thead><tbody>
                    {(devices.devices as any[]).map((device: any) => <tr key={device.device_id}><td className="mono">{device.device_id}</td><td><StatusBadge status={device.status}>{device.status}</StatusBadge></td><td className="mono">{device.enrollment_hash ? device.enrollment_hash.slice(0, 16) + '…' : '—'}</td><td>{device.last_seen_at ?? '—'}</td><td><button className="btn secondary small" onClick={() => revoke(device.device_id)}>Revoke</button></td></tr>)}
                </tbody></table>}
            </div>
        </div>
    );
}

const NAV: NavigationLink[] = [
    { to: '/', label: '⚡ Overview', end: true },
    { to: '/agents', label: '🧠 Agents' },
    { to: '/executions', label: '⏱ Executions' },
    { to: '/approvals', label: '🛂 Approvals' },
    { to: '/audit', label: '📜 Audit' },
    { to: '/models', label: '🤖 Models' },
    { to: '/memory', label: '💾 Memory' },
    { to: '/briefings', label: '📰 Briefings' },
    { to: '/governance', label: '🛡 Governance' },
    { to: '/telemetry', label: '📊 Telemetry' },
    { to: '/settings', label: '⚙️ Settings' },
    { to: '/jarvis', label: '🤖 J.A.R.V.I.S.' },
    { to: '/do-this', label: '🛠 Do This' },
    { to: '/advanced', label: '🧪 Advanced' },
    { to: '/humanoid', label: '🦾 Humanoid' },
    { to: '/mobile-link', label: '📱 Mobile Link' },
    { to: '/engineering', label: '🧩 Engineering' },
    { to: '/subsystems', label: '🔬 Registry' },
    { to: '/cockpit', label: '🛡 Safety' },
    { to: '/mcp', label: '🔌 MCP' },
];

function BriefingsPage() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const [briefings, setBriefings] = useState<JsonRecord[]>([]);
    const [selected, setSelected] = useState<JsonRecord | null>(null);
    const { addToast } = useToast();
    useEffect(() => {
        if (!token) return undefined;
        void api.get<JsonRecord>('/api/v2/briefings', token).then((data) => setBriefings((data.briefings as JsonRecord[]) ?? [])).catch(() => addToast('Failed to load briefings', 'error'));
        return undefined;
    }, [token]);
    const open = async (briefingId: string) => {
        if (!token) return;
        try {
            const data = await api.get<JsonRecord>(`/api/v2/briefings/${encodeURIComponent(briefingId)}`, token);
            setSelected(data);
        } catch {
            addToast('Failed to load briefing', 'error');
        }
    };
    return (
        <div className="page route-fade">
            <h2 className="page-title">📰 Morning brief</h2>
            <div className="notice">Every brief section carries source refs, observed time, freshness, and status. Missing data is rendered as missing or unavailable.</div>
            <div className="card">
                <div className="card-header">RECENT BRIEFS</div>
                {briefings.length === 0 && <div className="empty">No briefings yet. Generate one to start.</div>}
                {briefings.length > 0 && <table className="data-table"><thead><tr><th>ID</th><th>Generated</th><th></th></tr></thead><tbody>
                    {briefings.map((briefing) => <tr key={String(briefing.briefing_id)}><td className="mono">{String(briefing.briefing_id).slice(0, 16)}…</td><td>{String(briefing.generated_at ?? '—')}</td><td><button className="btn secondary small" onClick={() => open(String(briefing.briefing_id))}>View</button></td></tr>)}
                </tbody></table>}
            </div>
            {selected && <div className="card"><div className="card-header">BRIEF · {String(selected.briefing_id ?? '—')}</div><pre className="code-out">{JSON.stringify(selected, null, 2)}</pre></div>}
        </div>
    );
}

function RightRail() {
    const { session } = useAuth();
    const token = session?.access_token ?? null;
    const feed = useEventFeed();
    const approvals = useApi<JsonRecord>('/api/v2/governance/approvals', token);
    const agentApprovals = (approvals.data?.agent_approvals ?? []) as any[];
    const legacyApprovals = (approvals.data?.legacy_approvals ?? []) as any[];
    const pendingCount = agentApprovals.length + legacyApprovals.length;
    const recentEvents = feed.events.slice(-8);
    const latestPlanEvent = recentEvents.find((event) => event.type === 'plan.created' || event.type === 'plan.updated');
    const planPreview = latestPlanEvent ? (latestPlanEvent.payload as JsonRecord | undefined) : null;
    return (
        <aside className="right-rail" aria-label="Command stream and approvals">
            <div className="rail-card">
                <div className="rail-card-header">EVENT HEALTH</div>
                <div className="rail-event"><span className="rail-meta">status</span> <StatusBadge status={feed.status}>{feed.status}</StatusBadge></div>
                <div className="rail-event"><span className="rail-meta">cursor</span> {feed.cursor}</div>
                <div className="rail-event"><span className="rail-meta">events</span> {feed.events.length}</div>
            </div>
            <div className="rail-card">
                <div className="rail-card-header">PLAN PREVIEW</div>
                {!planPreview && <div className="rail-event">No active plan in this session.</div>}
                {planPreview && <div className="rail-event"><span className="rail-meta">status</span> <StatusBadge status={String(planPreview.status ?? 'unknown')}>{String(planPreview.status ?? 'unknown')}</StatusBadge></div>}
                {planPreview && <div className="rail-event"><span className="rail-meta">digest</span> <code>{String(planPreview.digest ?? '—').slice(0, 16)}…</code></div>}
                {planPreview && <pre className="code-out">{JSON.stringify(planPreview, null, 2).slice(0, 600)}</pre>}
            </div>
            <div className="rail-card">
                <div className="rail-card-header">COMMAND STREAM</div>
                {recentEvents.length === 0 && <div className="rail-event">No events received in this session.</div>}
                {recentEvents.map((event, index) => <div className="rail-event" key={event.event_id ?? `${event.sequence ?? 'event'}-${index}`}><span className="rail-meta">{displayValue(event.sequence)}</span> · {displayValue(event.type)} · {displayValue(event.payload?.status ?? event.aggregate?.id)}</div>)}
            </div>
            <div className="rail-card">
                <div className="rail-card-header">APPROVALS</div>
                <div className="rail-approval">Pending: <span className="rail-meta">{pendingCount}</span></div>
                {pendingCount > 0 && <NavLink to="/approvals" className="rail-link">Review approvals</NavLink>}
                {pendingCount === 0 && <div className="rail-event">No pending approvals.</div>}
            </div>
        </aside>
    );
}

function modeFromPath(pathname: string): string {
    if (pathname.startsWith('/do-this')) return 'Do This';
    if (pathname.startsWith('/advanced')) return 'Advanced';
    if (pathname.startsWith('/humanoid')) return 'Humanoid';
    if (pathname.startsWith('/mobile-link')) return 'Mobile Link';
    if (pathname.startsWith('/engineering')) return 'Engineering';
    if (pathname.startsWith('/jarvis')) return 'Assist';
    if (pathname.startsWith('/cockpit') || pathname.startsWith('/mcp')) return 'Safety';
    return 'Observe';
}

function Shell() {
    const { session, logout } = useAuth();
    const { theme, toggleTheme } = useTheme();
    const [paletteOpen, setPaletteOpen] = useState(false);
    const location = useLocation();
    const feed = useEventFeed();
    const settings = useApi<JsonRecord>('/api/v2/settings', session?.access_token ?? null);
    const settingsData = settings.data as Record<string, any> | null;
    const profile = settingsData?.profile ?? 'local';
    const deviceId = session?.device_id ?? '—';
    const mode = modeFromPath(location.pathname);
    return <div className="shell"><header className="top-bar"><div className="logo"><span className="logo-z">Z</span>ASI <span className="logo-version">{profile} · {mode} · {displayValue(deviceId)}</span></div><nav className="nav-links" aria-label="Primary navigation">{NAV.map((link) => <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => `nav-tab${isActive ? ' active' : ''}`}>{link.label}</NavLink>)}</nav><div className="header-actions"><StatusBadge status={feed.status}>{feed.status}</StatusBadge><span className="tenant-label">{session?.tenant_id ?? '—'}</span><button className="btn secondary small" onClick={() => setPaletteOpen(true)} title="Command palette" aria-label="Open command palette">⌘K</button><button className="btn secondary small" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>{theme === 'dark' ? '☀️' : '🌙'}</button><button className="btn secondary small" onClick={logout}>SIGN OUT</button></div></header><div className="shell-body"><main className="main-content"><Outlet /></main><RightRail /></div><footer className="footer">ZASI governed control plane · Observe / Assist · simulated and unavailable states are disclosed</footer><CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} /></div>;
}

function AuthenticatedApp() {
    const { session } = useAuth();
    if (!session) return <LoginPage />;
    return <Routes><Route path="/" element={<Shell />}><Route index element={<OverviewPage />} /><Route path="agents" element={<AgentsPage />} /><Route path="executions" element={<ExecutionsPage />} /><Route path="approvals" element={<ApprovalsPage />} /><Route path="audit" element={<AuditPage />} /><Route path="models" element={<ModelsPage />} /><Route path="memory" element={<MemoryPage />} /><Route path="briefings" element={<BriefingsPage />} /><Route path="governance" element={<GovernancePage />} /><Route path="telemetry" element={<TelemetryPage />} /><Route path="settings" element={<SettingsPage />} /><Route path="jarvis" element={<JarvisPage />} /><Route path="do-this" element={<DoThisPage />} /><Route path="advanced" element={<AdvancedPage />} /><Route path="humanoid" element={<HumanoidPage />} /><Route path="mobile-link" element={<MobileLinkPage />} /><Route path="engineering" element={<EngineeringPage />} /><Route path="subsystems" element={<SubsystemsPage />} /><Route path="cockpit" element={<CockpitPage />} /><Route path="mcp" element={<MCPPage />} /></Route></Routes>;
}

function App() {
    return <ThemeProvider><ToastProvider><AuthProvider><BrowserRouter basename={ROUTER_BASENAME}><AuthenticatedApp /></BrowserRouter></AuthProvider></ToastProvider></ThemeProvider>;
}

// Kept as the migrated cockpit implementation while app.tsx owns the typed entrypoint.
export default App;
