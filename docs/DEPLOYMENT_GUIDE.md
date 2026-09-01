# 🚀 ZASI Production Deployment & Operations Guide v32.0.0

## 1. Zero-Touch Installation
```bash
./install.sh
```
Installs dependencies, runs the 172-test suite and React verification, builds distribution wheels, and registers the global `zasi` CLI.

---

## 2. Running the Full-Stack J.A.R.V.I.S. Command Cockpit

### Local Python Server
```bash
make server  # Access at http://localhost:8080
```

### Docker Container Deployment
```bash
make docker-build
make docker-run
```
Or via Docker Compose:
```bash
docker compose up -d
```

### Electron Desktop App
```bash
npm install
npm run electron
```

---

## 3. Package Registry Deployments

### Python Package Index (PyPI)
```bash
pip install zasi
```
Or publish a release:
```bash
git tag v32.0.0
git push origin v32.0.0
```

### npm Registry (`zasi-cockpit`)
```bash
npm install zasi-cockpit
```

---

## 4. Environment Variables Reference

| Variable | Default | Purpose |
|---|---|---|
| `ZASI_PORT` | `8080` | Server listening port |
| `ZASI_API_KEY` | *(empty)* | Optional API key authentication header (`X-API-Key`) |
| `GEMINI_API_KEY` | *(empty)* | Optional Google Gemini 2.0 Flash API key for neural grounding |
| `ZASI_ENV` | `production` | Environment mode (`development` / `production`) |
| `ZASI_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 5. Model Context Protocol (MCP) Integration

Add ZASI to Claude Desktop or VS Code MCP configuration:
```json
{
  "mcpServers": {
    "zasi": {
      "command": "python3",
      "args": ["-m", "src.mcp_stdio_transport"]
    }
  }
}
```
