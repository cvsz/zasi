# ZASI system architecture and ownership

This page is the short operational summary. The normative contract is
[ZASI_IMPLEMENTATION_SPECIFICATION.md](ZASI_IMPLEMENTATION_SPECIFICATION.md),
and the product/system vision is
[ZASI_FULL_ARCHITECTURE.md](ZASI_FULL_ARCHITECTURE.md).

## Runtime ownership

`backend.app` is the only authoritative application entry point. It owns the
ASGI lifecycle, authenticated session, tenant scope, policy evaluation, typed
tool registry, SQLite repository, audit/event/outbox records, SSE replay, and
the bundled cockpit fallback. `main.py` and `backend.server.py` are not
production owners; their explicit compatibility/demo commands are quarantined.

```text
browser / Electron
        |
        | authenticated JSON + bearer SSE
        v
backend.app (ASGI)
  identity -> policy -> intent/plan -> broker -> evidence
        |                    |
        +---- SQLite ---------+---- events + durable outbox
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

Local uses loopback-oriented configuration and SQLite. Staging and production
configuration require an explicit PostgreSQL URL, external secret provider,
and managed backup policy; the current reference binary intentionally refuses
to start those profiles until the production repository adapter exists. This is
a deliberate NO-GO boundary, not a claim of PostgreSQL readiness.
