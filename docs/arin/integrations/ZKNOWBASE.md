# ARIN ↔ zknowbase integration

## Bounded first slice

ARIN consumes zknowbase as an independently owned service. The first integration slice is deliberately **read-only contract construction** for `/api/v1/search` and non-streaming `/api/v1/query`.

The contract requires a server-side, tenant-scoped service key with `knowledge:read`, an explicit tenant context, and a bounded timeout. Missing credentials/context, invalid endpoints, empty queries, and unbounded result counts fail before a request can be issued.

ARIN does not copy zknowbase, Qdrant state, provider credentials, ingestion code, or service-key administration. Browser/mobile clients must never receive the service key.

## Source contract

Pinned source: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`.

The source exposes authenticated `POST /api/v1/search` and `POST /api/v1/query` under `/api/v1`; read routes require `knowledge:read` and zWorkforce tenant-context validation. Write/ingest routes are intentionally outside this slice.

## Safety and failure behavior

Knowledge output is evidence/input to ARIN cognition only. It grants no action or physical-actuation authority. A later transport implementation must distinguish required-knowledge operations (fail closed on unavailable/degraded zknowbase) from optional enrichment (explicit safe degradation), and must map source provenance/citations into ZASI evidence.

## Remaining Task 5 work

- Implement the HTTP transport behind this contract using bounded timeouts and redacted errors.
- Add fake/local endpoint contract tests for success, authentication failure, timeout/unavailable, tenant isolation, and malformed responses.
- Map zknowbase result provenance/citations into ZASI evidence.
- Consider ingest/write only in a separate policy-gated slice with explicit `knowledge:write` scope.
