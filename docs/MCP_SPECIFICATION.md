# ZASI Model Context Protocol (MCP) & Transports Specification

## 1. Overview
ZASI implements the standard **Model Context Protocol (MCP) JSON-RPC 2.0 Specification** (2024-11-05), enabling external LLMs (Claude, Gemini, OpenAI), developer IDEs (Cursor, VS Code, Antigravity CLI), and distributed agent swarms to interact directly with the ZASI Cognitive Superintelligence Core.

---

## 2. Supported Transports

### A. Standard I/O (`MCPStdioTransport`)
- **Module**: `src/mcp_stdio_transport.py`
- **Use Case**: Local CLI tools, Claude Desktop, and local subprocess execution.
- **Protocol**: Newline-delimited JSON-RPC 2.0 over `stdin` and `stdout`.

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize"}
```

### B. Server-Sent Events (`MCPSSETransport`)
- **Module**: `src/mcp_sse_transport.py`
- **Use Case**: Real-time browser web clients, microservices, and distributed streaming agents.
- **Protocol**: HTTP SSE (`/events`) with HTTP POST endpoints for JSON-RPC messages.

---

## 3. Registered Tools

| Tool Name | Description | Required Parameters |
| :--- | :--- | :--- |
| `verify_invariant` | Verifies a proposed state mutation against dynamic AST/SMT invariants | `variables`, `invariants` |
| `query_hypergraph` | Searches persistent CXL hypergraph memory for semantic entities | `query_key` |
