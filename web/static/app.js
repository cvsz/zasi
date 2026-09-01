// ZASI 3D Multiverse Hypergraph & Real-Time Telemetry Client
let scene, camera, renderer, nodesGroup;

function initThreeJS() {
    const container = document.getElementById('canvas-container');
    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x030712, 0.02);

    camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.z = 24;

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Create 128-Subsystem Hypergraph Network Nodes
    nodesGroup = new THREE.Group();
    const geometry = new THREE.SphereGeometry(0.35, 16, 16);
    const material = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    const coreMat = new THREE.MeshBasicMaterial({ color: 0xf43f5e });

    // Center Singularity Apex Core
    const apexMesh = new THREE.Mesh(new THREE.SphereGeometry(1.2, 32, 32), coreMat);
    nodesGroup.add(apexMesh);

    // 128 Orbiting Subsystem Nodes
    for (let i = 0; i < 128; i++) {
        const phi = Math.acos(-1 + (2 * i) / 128);
        const theta = Math.sqrt(128 * Math.PI) * phi;
        const radius = 8 + (i % 5) * 1.8;

        const x = radius * Math.cos(theta) * Math.sin(phi);
        const y = radius * Math.sin(theta) * Math.sin(phi);
        const z = radius * Math.cos(phi);

        const node = new THREE.Mesh(geometry, material);
        node.position.set(x, y, z);
        nodesGroup.add(node);
    }

    scene.add(nodesGroup);

    // Window Resize Hook
    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    animate();
}

function animate() {
    requestAnimationFrame(animate);
    if (nodesGroup) {
        nodesGroup.rotation.y += 0.003;
        nodesGroup.rotation.x += 0.001;
    }
    renderer.render(scene, camera);
}

// Telemetry Poller
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
        }
    } catch (e) {
        console.warn('Telemetry poll failed:', e);
    }
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('state-display').innerText = JSON.stringify(data.state);
        }
    } catch (e) {
        console.warn('Status poll failed:', e);
    }
}

async function triggerDaemonTick() {
    try {
        const res = await fetch('/api/tick');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('state-display').innerText = JSON.stringify(data.state);
            document.getElementById('last-action').innerText = data.action ? `${data.action} (${data.status})` : data.status;
            document.getElementById('dynamic-log').innerText = `[TICK] ${data.status} | Action: ${data.action}`;
        }
    } catch (e) {
        alert('Tick execution failed');
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
            document.getElementById('dynamic-log').innerText = `[MUTATE] ${variable} += ${delta}`;
        }
    } catch (e) {
        alert('Mutation failed');
    }
}

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    initThreeJS();
    fetchTelemetry();
    fetchStatus();
    setInterval(fetchTelemetry, 2000);
    setInterval(fetchStatus, 3000);
});
