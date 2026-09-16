# ADR-ARIN-0002: Bounded ZCoder Tool Adapter

## Metadata

- ADR ID: `ADR-ARIN-0002`
- Status: `accepted`
- Date: 2026-09-16
- Owner: ARIN Project Center
- Related capability: bounded tools / MCP execution
- Source repository/service: `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab`
- Target ARIN component: ARIN tool adapter boundary

## Capability gap

ARIN has verified native capability descriptors, risk classes, and deny-by-default policy regressions, but intentionally has no runtime tool service. Task 6 requires a service/adapter-first integration path that can execute only capabilities already admitted by ARIN policy without inheriting ambient shell, filesystem, network, MCP, credential, tenant, or actuator authority.

## Decision

Use an `api-service` / narrow-adapter integration. ZASI remains the canonical owner of ARIN capability descriptors, policy decisions, approval evidence, tenant/session binding, resource bounds, and audit identity. A future adapter may translate an already-authorized ARIN execution request to a separately bounded ZCoder service contract.

The adapter MUST NOT import or copy the ZCoder repository wholesale. It MUST NOT expose a generic shell, arbitrary filesystem path, arbitrary URL, raw MCP passthrough, environment inheritance, or actuator API.

The first runtime slice must be disabled by default and may implement contract validation/fake transport before any real external service connection.

## Alternatives considered

### Build a new execution engine in ZASI

Rejected for now. It duplicates containment/execution work and increases the security surface. ARIN should own policy and contracts, not another unrestricted execution runtime.

### Port ZCoder libraries into ZASI

Rejected unless a later ADR proves service integration impractical and records file-level license/provenance. Library porting creates tighter lifecycle coupling and a larger trusted computing base.

### Direct MCP passthrough

Rejected. It would bypass ARIN capability descriptors and risks ambient tool/network/filesystem authority.

### Do nothing / defer

Safe but leaves Task 6 incomplete. The proposed adapter preserves the current deny-by-default state while defining a bounded path forward.

## Canonical ownership

- ZASI owns: ARIN capability IDs/versions, risk classification, tenant/session context, policy authorization, approval evidence, resource ceilings, audit correlation, cancellation intent, and the no-actuator invariant.
- ZCoder owns: its independently deployed execution containment/runtime implementation.
- Adapter owns: schema translation and bounded request/response normalization only.
- ZCoder source remains in `cvsz/zcoder`; no repository transfer or source copy is approved.

## Required adapter contract

Every execution request must carry an immutable ARIN capability descriptor reference/version plus tenant ID, session ID, operation class, bounded timeout/resource limits, policy decision identity, and approval evidence when required.

The adapter must reject:

- unknown or stale capability versions;
- missing/mismatched tenant or session context;
- requests whose policy is not explicitly allowed;
- privileged/critical requests lacking required approval evidence;
- filesystem access outside declared canonical roots;
- network access outside declared destinations;
- subprocess execution unless explicitly declared;
- caller-supplied ambient environment/secrets;
- raw shell command or raw MCP payload fields not represented by the approved capability schema;
- any robot/actuator/joint/torque/velocity/PWM authority.

Responses must be bounded, typed, attributable to the request/audit correlation ID, and must not return service credentials or inherited environment secrets.

## Security, privacy, and safety impact

Authentication and authorization remain server-side. The adapter is not an authority source and cannot upgrade a denied decision. Tenant/session isolation is mandatory on every request. Credentials are server-held and redacted from logs/representations. Network/filesystem/subprocess access is allowlisted from the descriptor, never inferred from model output.

Cancellation and timeout are fail-closed: after cancellation, deadline expiry, lost authorization context, or transport loss, ARIN must not treat the execution as successful. Retries of mutating operations require explicit idempotency semantics rather than blind replay.

This path cannot create physical actuation. Browser/mobile/LLM output cannot reach raw joint, torque, velocity, PWM, vendor actuator, ROS actuator, or equivalent APIs through this adapter. Physical humanoid execution remains a separate future path behind the deterministic safety supervisor and HIL gates.

## License and provenance

Pinned reference: `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab`. Existing Project Center evidence records MIT licensing and containment/MCP requirements. This ADR authorizes contract/service integration only; it does not authorize copying ZCoder source. Any later source port requires a separate provenance review.

## Test and CI evidence required before runtime enablement

1. Contract tests for unknown capability/version and malformed payload rejection.
2. Tenant/session mismatch tests.
3. Policy-denial tests across filesystem, network, subprocess, and tool operations.
4. Approval-required tests for privileged/critical capabilities.
5. Canonical filesystem-root and network-destination containment tests.
6. Secret/environment non-inheritance and redaction tests.
7. Timeout, cancellation, transport-loss, malformed-response, and bounded-output tests.
8. Mutating-operation idempotency/replay tests before any mutation is admitted.
9. Audit correlation tests.
10. Exact-head ZASI CI, security, CodeQL, rollback, backup/DR, and applicable integration evidence.

A real ZCoder endpoint is not required for the first contract slice; fake/local transport is preferred until these invariants are green.

## Migration plan

1. Accept this ADR through normal review/CI. **Completed by merged PR #129.**
2. Add ARIN-owned adapter request/response schemas and failing tests first. **Completed and verified by PR #130 exact head `7c45e8ab807d0451d30afd252b3a49285c224399`.**
3. Add fake/local transport proving deny-by-default behavior.
4. Add a disabled-by-default real service endpoint only after contract/security evidence is green.
5. Enable one low-risk read-only capability first.
6. Add privileged/mutating capabilities only through separate bounded evidence slices.
7. Promote ownership state only after consumer, operational, and rollback evidence is recorded in the migration ledger.

## Rollback plan

Disable/remove the adapter configuration and return to the current native descriptor/policy-only state. No source migration or persistent data migration is introduced by the contract phase. Runtime consumers must fail closed when the adapter is unavailable for a required operation; optional capabilities may be reported unavailable but must never be silently substituted with broader authority.

## Decommission plan

If the adapter is replaced, preserve capability IDs/version compatibility for the supported migration window, migrate consumers with contract tests, revoke service credentials, remove endpoint configuration, and retain audit evidence. Repository archive/delete/rename/transfer is outside this ADR.

## Decision evidence

- Source commit/tag: `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab`
- Existing ARIN evidence: PR #126 security requirements; PR #127 capability descriptors; PR #128 denial-policy regressions
- ADR acceptance: merged PR #129
- Adapter contract: merged PR #130, exact head `7c45e8ab807d0451d30afd252b3a49285c224399`
- CI/workflow evidence: all nine exact-head ZASI gates passed for PR #130
- Security review: capability ID/version/operation authority binding added before merge; exact-head CodeQL and Security Evidence passed
- Migration ledger entry: `ARIN-MIG-0012`
- Follow-up: fake/local transport and failure-boundary tests before any real endpoint
