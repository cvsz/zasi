# ZASI Planetary & Distributed Deployment Guide

This guide describes how to deploy, cluster, and run ZASI across local workstations, cloud instances, and distributed orbital networks.

---

## 1. Quickstart (Local Host)

```bash
# Clone and enter directory
cd /home/cvsz/zasi

# Automated installation & verification
./install.sh

# Run full sovereign runtime
python3 main.py

# Launch interactive CLI
zasi -i
```

---

## 2. Docker Container Deployment

```bash
# Build the Docker image
docker build -t zasi:5.0.0 .

# Run container with web visualizer exposed
docker run -d --name zasi-node -p 8080:8080 zasi:5.0.0

# View real-time telemetry dashboard
open http://localhost:8080
```

---

## 3. Distributed P2P Mesh Cluster Setup

To connect multiple ZASI nodes into a federated swarm:

1. **Configure `config.json` on each node**:
```json
{
  "system": { "name": "zasi-node-us-east" },
  "server": { "host": "0.0.0.0", "port": 8080 }
}
```

2. **Discover and Sync Swarm Peers**:
```python
from src import P2PGossipSwarm

swarm = P2PGossipSwarm(node_id="zasi-node-us-east")
swarm.discover_peer("zasi-node-eu-west", "10.0.1.20:8080")
swarm.discover_peer("zasi-node-ap-south", "10.0.2.30:8080")
```

---

## 4. Monitoring & Telemetry

- **Web Dashboard**: `http://<host>:8080/` (Real-time Three.js 3D node visualizer)
- **JSON Telemetry Endpoint**: `http://<host>:8080/api/status`
- **Unit & Integration Test Suite**:
  ```bash
  python3 -m unittest discover -s tests
  ```
