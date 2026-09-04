# ZASI system architecture and ownership

This page is the short operational summary. The normative contract is
[ZASI_IMPLEMENTATION_SPECIFICATION.md](ZASI_IMPLEMENTATION_SPECIFICATION.md),
and the product/system vision is
[ZASI_FULL_ARCHITECTURE.md](ZASI_FULL_ARCHITECTURE.md).

## Runtime ownership

`backend.app` is the only authoritative application entry point. It owns the
ASGI lifecycle, authenticated session, tenant scope, policy evaluation, typed
tool registry, SQLite/PostgreSQL repository, Redis-backed shared rate limits,
audit/event/outbox records, SSE replay, and the bundled cockpit fallback.
`main.py` and `backend.server.py` are not production owners; their explicit
compatibility/demo commands are quarantined.

```text
browser / Electron
        |
        | authenticated JSON + bearer SSE
        v
backend.app (ASGI)
  identity -> policy -> intent/plan -> broker -> durable action queue
                                      -> worker -> evidence
        |                    |
        +---- PostgreSQL/SQLite ---- events + durable outbox
              |
              +---- Redis (authenticated shared rate limits)
```

The control plane is server-authoritative. A UI route, model response, voice
signal, or MCP payload cannot grant a capability or bypass the broker.

## Capability truth model

The historical 176-entry catalog is inventory only. Runtime responses expose
implementation state, runtime state, evidence state, allowed risk tiers,
verification references, and operator disclosure separately. The reference
profile has one locally verified read-only system-status tool; external
connectors, research execution, runtime hot swap, physical actuation, and
unverified formal/cryptographic claims remain disabled or unavailable.

## State and event flow

State-changing operations commit domain state, audit metadata, an append-only
tenant event, and an outbox row in one transaction. SSE cursors are tenant
scoped. A cursor outside retention emits `resync.required`; clients must fetch
`/api/v2/snapshot` before reconnecting. Event delivery is replay-safe and does
not imply that a capability is live.

## Profiles

Local defaults remain portable, while this checkout can use the authenticated
shared PostgreSQL and Redis services through its private generated `.env`.
Staging and production configuration require explicit PostgreSQL and Redis
URLs, an external secret provider, and a managed backup policy. The repository
adapter is implemented and locally smoke-tested; staging deployment, managed
secrets/backups, and rollback evidence remain release gates.

## Agent platform trust zone

The agent platform adds two bounded, code-owned tools:

- `knowledge.search` (R0) is a read-only, tenant-scoped local memory search.
  It never returns another tenant's data and makes no external calls.
- `ticket.update` (R2) is an approval-gated deterministic local simulator. Its
  response always carries `simulated=true` and `external_write=false`; no
  connector or external write system is ever contacted.

The default model is the deterministic simulator. An operator may configure a
loopback-only Ollama endpoint (`ZASI_OLLAMA_BASE_URL` and `ZASI_OLLAMA_MODEL`);
model output is treated as an untrusted proposal and never executed without
planner whitelist and policy verification. Hosted model fallback is explicitly
disabled.

The agent platform keeps real-world side effects disabled: no credentials,
browser automation, arbitrary code execution, robotics, financial actions,
live SaaS writes, or external connector calls. Research-only capabilities
(recursive self-improvement, neural-symbolic verification, architecture search,
kernel generation, self-deployment, and distributed memory topology) are typed
disabled/research-only projections with no executable mutation hooks.
