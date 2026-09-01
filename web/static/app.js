// ZASI Advanced Full-Feature Cockpit Client v25.0.0
let scene, camera, renderer, nodesGroup, activeTab = 'overview';

// 1. Tab Switcher
function switchTab(tabId) {
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    const tabBtn = Array.from(document.querySelectorAll('.nav-tab')).find(b => b.innerText.toLowerCase().includes(tabId));
    if (tabBtn) tabBtn.classList.add('active');

    const targetContent = document.getElementById(`tab-${tabId}`);
    if (targetContent) targetContent.classList.add('active');
    activeTab = tabId;

    if (tabId === 'subsystems') {
        loadSubsystemsCatalog();
    }
}

// 2. Three.js Multiverse 3D Hypergraph
function initThreeJS() {
    const container = document.getElementById('canvas-container');
    if (!container) return;

    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030712, 0.02);

    camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.z = 24;

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    nodesGroup = new THREE.Group();
    const geometry = new THREE.SphereGeometry(0.35, 16, 16);
    const material = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xf43f5e });

    // Center Singularity Omega Core
    const apexMesh = new THREE.Mesh(new THREE.SphereGeometry(1.2, 32, 32), coreMat);
    nodesGroup.add(apexMesh);

    // 128 Orbiting Subsystem Nodes
    for (let i = 0; i < 128; i++) {
        const phi = Math.acos(-1 + (2 * i) / 128);
        const theta = Math.sqrt(128 * Math.PI) * phi;
        const radius = 8 + (i % 6) * 1.8;

        const x = radius * Math.cos(theta) * Math.sin(phi);
        const y = radius * Math.sin(theta) * Math.sin(phi);
        const z = radius * Math.cos(phi);

        const node = new THREE.Mesh(geometry, material);
        node.position.set(x, y, z);
        nodesGroup.add(node);
    }

    scene.add(nodesGroup);

    window.addEventListener('resize', () => {
        if (!container) return;
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    animate();
}

function animate() {
    requestAnimationFrame(animate);
    if (nodesGroup) {
        nodesGroup.rotation.y += 0.0025;
        nodesGroup.rotation.x += 0.001;
    }
    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}

// 3. Telemetry & Real-Time Poller
async function fetchTelemetry() {
    try {
        const res = await fetch('/api/telemetry');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('cpu-val').innerText = `${data.cpu_load.toFixed(1)}%`;
            document.getElementById('cpu-fill').style.width = `${Math.min(100, data.cpu_load)}%`;

            document.getElementById('ram-val').innerText = `${data.memory_used_mb.toLocaleString()} MB / ${data.memory_total_mb.toLocaleString()} MB`;
            document.getElementById('ram-fill').style.width = `${(data.memory_used_mb / data.memory_total_mb) * 100}%`;

            if (data.gpus && data.gpus.length > 0) {
                const g = data.gpus[0];
                document.getElementById('gpu-val').innerText = `${g.utilization.toFixed(1)}% | ${g.temp_c}°C | ${g.power_w}W`;
                document.getElementById('gpu-fill').style.width = `${g.utilization}%`;
            }

            document.getElementById('energy-val').innerText = `${data.arc_reactor_gw.toFixed(1)} GW`;
            document.getElementById('phi-val').innerText = `${data.global_phi.toLocaleString()}`;

            // Render live logs
            if (data.logs) {
                const logBox = document.getElementById('log-lines');
                logBox.innerHTML = data.logs.map(l => `<div class="log-line">[${l.timestamp}] [${l.level}] ${l.message}</div>`).join('');
                logBox.scrollTop = logBox.scrollHeight;
            }
        }
    } catch (e) {
        console.warn('Telemetry fetch error:', e);
    }
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('state-display').innerText = JSON.stringify(data.state);
            document.getElementById('active-version-display').innerText = data.rsi_version;
        }
    } catch (e) {
        console.warn('Status fetch error:', e);
    }
}

// 4. Interactive Cognitive Actions
async function triggerDaemonTick() {
    try {
        const res = await fetch('/api/tick');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('state-display').innerText = JSON.stringify(data.state);
            fetchTelemetry();
        }
    } catch (e) {
        alert('Tick error');
    }
}

async function mutateState(variable, delta) {
    try {
        const res = await fetch('/api/mutate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ variable, delta })
        });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('state-display').innerText = JSON.stringify(data.state);
            fetchTelemetry();
        }
    } catch (e) {
        alert('Mutation error');
    }
}

async function triggerRSIUpgrade() {
    try {
        const res = await fetch('/api/rsi/upgrade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: 'v25.0.0-apex-omega' })
        });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('rsi-speedup').innerText = `${data.speedup.toFixed(1)}x`;
            fetchTelemetry();
            fetchStatus();
        }
    } catch (e) {
        alert('RSI Upgrade failed');
    }
}

// 5. Subsystem Catalog & Remote Runners
async function loadSubsystemsCatalog() {
    try {
        const res = await fetch('/api/subsystems');
        if (res.ok) {
            const data = await res.json();
            const grid = document.getElementById('subsystems-catalog');
            grid.innerHTML = data.catalog.map(s => `
                <div class="subsystem-card">
                    <h4>#${s.id} ${s.name}</h4>
                    <div class="meta">Module: ${s.module}</div>
                    <div class="meta">Category: ${s.category}</div>
                    <button class="btn secondary" onclick="alert('Subsystem #${s.id} operational')">DIAGNOSTIC PROBE</button>
                </div>
            `).join('');
        }
    } catch (e) {
        console.warn('Subsystems fetch error:', e);
    }
}

async function runSubsystem(key) {
    try {
        const res = await fetch(`/api/execute/${key}`);
        if (res.ok) {
            const data = await res.json();
            let targetId = 'qec-output';
            if (key === 'drug_discovery') targetId = 'drug-output';
            if (key === 'interstellar') targetId = 'interstellar-output';
            if (key === 'omega_singularity') targetId = 'omega-output';

            document.getElementById(targetId).innerText = JSON.stringify(data, null, 2);
        }
    } catch (e) {
        alert('Execution failed');
    }
}

// 6. MCP Protocol Console
async function sendMCPRequest() {
    try {
        const input = document.getElementById('mcp-input').value;
        const res = await fetch('/api/mcp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: input
        });
        const json = await res.json();
        document.getElementById('mcp-response').innerText = JSON.stringify(json, null, 2);
    } catch (e) {
        document.getElementById('mcp-response').innerText = `Error: ${e.message}`;
    }
}

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initThreeJS();
    fetchTelemetry();
    fetchStatus();
    setInterval(fetchTelemetry, 2000);
    setInterval(fetchStatus, 3000);
});
