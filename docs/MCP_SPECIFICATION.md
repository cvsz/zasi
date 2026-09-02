# ZASI Model Context Protocol (MCP) & Transports Specification

> **Status — 2026-09-02:** This page preserves the historical MCP transport and
> tool design. Its module names and tool list are not proof of a live MCP
> service. The authoritative reference profile exposes only authenticated
> `POST /api/v2/mcp` with `initialize`, `tools/list`, and governed
> `tools/call`; calls are resolved through the code-owned registry, policy,
> idempotency, audit, and evidence path. The legacy stdio/SSE modules below are
> compatibility/research surfaces until separately tested and deployed.

## 1. Overview
The original design targets the **Model Context Protocol (MCP) JSON-RPC 2.0
Specification** (2024-11-05), enabling compatible clients to interact with a
governed ZASI control-plane adapter. The reference profile does not grant an
external model, IDE, or agent swarm direct access to the cognitive core or to
arbitrary tools.

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

The current durable browser stream is `/api/v2/events`, not an unauthenticated
generic `/events` endpoint. It requires a session bearer token, tenant-scoped
cursor handling, and authoritative resync after a retention gap.

---

## 3. Registered Tools

| Tool Name | Description | Required Parameters |
| :--- | :--- | :--- |
| `verify_invariant` | Verifies a proposed state mutation against dynamic AST/SMT invariants | `variables`, `invariants` |
| `query_hypergraph` | Searches persistent CXL hypergraph memory for semantic entities | `query_key` |

The table above is a historical registry proposal. The current reference
registry exposes only `registry.system.status` as an enabled R0 observation;
unavailable or future tools must be represented as disabled, simulated,
research-only, or unavailable and cannot be invoked merely by naming them.

## 4. Current safety contract

- `tools/list` is read-only metadata discovery.
- `tools/call` requires an authenticated session and an idempotency key.
- Tool identifiers, input schemas, risk, scopes, and evidence methods come from
  the server-side registry; request payloads cannot register or supply a
  callable.
- Risk-bearing tools require a plan and exact approval; the reference profile
  has no enabled external or physical tool.
- JSON-RPC errors do not expose stack traces, secrets, SQL, or filesystem paths.

See [the implementation specification](ZASI_IMPLEMENTATION_SPECIFICATION.md)
and [the API reference](API_REFERENCE.md) for the authoritative contract.
