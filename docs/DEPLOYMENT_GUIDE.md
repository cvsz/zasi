# ZASI Production Deployment & Operations Guide v26.0.0

## 1. Zero-Touch Installation
```bash
./install.sh
```

## 2. Running the Full-Stack J.A.R.V.I.S. Command Cockpit
```bash
make server  # Access at http://localhost:8080
```

## 3. High-Performance Hardware Environment Variables
```bash
export ZASI_PORT=8080
export NVIDIA_VISIBLE_DEVICES=all
export ZASI_ENV=production
export ZASI_LOG_LEVEL=INFO
```

## 4. MCP JSON-RPC 2.0 Integration
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
