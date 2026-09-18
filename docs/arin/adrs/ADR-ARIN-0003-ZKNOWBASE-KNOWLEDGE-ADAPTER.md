# ADR-ARIN-0003: zknowbase Knowledge Adapter

## Metadata

- ADR ID: `ADR-ARIN-0003`
- Status: `accepted`
- Date: 2026-09-17
- Owner: ARIN Project Center
- Related capability: knowledge / grounded RAG
- Source repository/service: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`
- Target ARIN component: `backend/arin/knowledge.py`, `backend/arin/knowledge_write.py`, `backend/arin/knowledge_runtime.py`

## Capability gap

ARIN needs grounded knowledge retrieval with provenance while keeping the independently owned zknowbase service outside the ZASI trust boundary. The bounded adapter foundation is verified by PRs #115 and #122-#125. The API/service integration decision was accepted through PR #165 at exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384`, which passed the repository's required workflow groups and merged as signed commit `6762e442df18709772d10b792e39c9286a31ec02`. The bounded runtime consumer was verified by PR #169 and compatibility/rollback regressions by PR #170.

## Decision

Use `api-service`. ZASI remains the canonical owner of ARIN tenant/session identity, policy/approval decisions, evidence mapping and required-versus-optional knowledge semantics. zknowbase remains the independently deployed owner of ingestion, retrieval, vector/semantic knowledge and source provenance.

Do not copy or vendor zknowbase into ZASI. The adapter is a narrow authenticated service boundary. Read-only search/query is the only admitted transport in the verified foundation. Write/ingest authorization may be evaluated by policy, but no mutation transport is admitted by this ADR.

## Prior-path deprecation decision

The pre-existing direct `KnowledgeClient` read path is retained as a **rollback-only compatibility path**, not as a second canonical runtime consumer. New ARIN runtime consumers must enter through `backend/arin/knowledge_runtime.py`, which owns server-side tenant/session propagation and required-versus-optional failure semantics while delegating the same bounded read contract to `KnowledgeClient`.

No calendar removal deadline is invented. The compatibility path may be removed only after a later bounded change proves there are no remaining direct runtime consumers, preserves deterministic rollback through an equivalent tested mechanism, and passes exact-head CI. Until then it must not receive new product features, browser/mobile credentials, mutation authority, tool authority, or actuator authority.

This decision does not decommission zknowbase, revoke the read adapter, authorize write transport, or claim ARIN production readiness. It only resolves which ARIN runtime path is canonical and which path is retained for rollback compatibility.

## Alternatives considered

### Build knowledge/RAG directly in ZASI

Rejected. It duplicates zknowbase ownership and expands ZASI's data, embedding and vector-store trust surface.

### Copy or selectively port zknowbase into ZASI

Rejected for the current capability. The existing service contract is sufficient and preserves repository history, provenance and independent lifecycle ownership.

### Direct client access to zknowbase

Rejected. Browser/mobile clients must not receive zknowbase service credentials or bypass ZASI tenant/session/policy enforcement.

### Do nothing / defer

Safe but would leave Task 5 canonical promotion incomplete despite merged runtime and rollback evidence.

## Canonical ownership

- ZASI owns ARIN authentication context, tenant/session binding, policy/approval, adapter configuration, required/optional semantics, evidence normalization and audit correlation.
- zknowbase owns knowledge ingestion/storage/indexing/retrieval and source provenance behind its service API.
- `backend/arin/knowledge_runtime.py` is the canonical ARIN runtime consumer boundary.
- `KnowledgeClient` remains the bounded read adapter and rollback-only compatibility entry point; it is not a browser/mobile/public credential boundary.
- Source remains in `cvsz/zknowbase`; no repository consolidation is authorized.

## Security, privacy and safety impact

Service credentials remain server-side and scoped. Cross-tenant/session or malformed identity/provenance responses fail closed. Required knowledge fails closed on service unavailability; optional knowledge may degrade only for normalized transport unavailability and must not convert malformed, provenance or isolation failures into success.

No browser/mobile/service caller can use this adapter to gain provider credentials, filesystem/network authority, tool execution or physical actuation. The knowledge path has no raw actuator, ROS actuator, joint, torque, velocity or PWM authority. Physical actuation remains disabled independently of this decision.

## License and provenance

Pinned source: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`. Existing Project Center capability/evidence records remain the source of truth for source licensing and CI/security evidence. This ADR authorizes API/service integration only and does not authorize source copying.

## Existing test and CI evidence

The bounded foundation is recorded by `ARIN-MIG-0008`:

1. PR #115 — contract foundation and fake/local boundary tests.
2. PR #122 — read-only transport with scoped credentials and bounded timeouts.
3. PR #123 — provenance/citation mapping into ARIN evidence.
4. PR #124 — explicit scope/policy/approval gate for write/ingest authorization; mutation transport remains absent.
5. PR #125 — required knowledge fail-closed behavior and narrowly normalized optional degradation.
6. PR #165 exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384` — ADR acceptance passed required workflow groups and merged as signed commit `6762e442df18709772d10b792e39c9286a31ec02`.
7. PR #168 — exact consumer inventory; no separate production consumer existed at inventory time.
8. PR #169 exact head `c6b2761dc9ca14e438ea7fb053ee4f8a70db6444` — bounded server-side runtime consumer passed all nine required workflow groups and merged signed as `bd939aa95caeaf63783678b10d824410a03bbd5e`.
9. PR #170 exact head `37fa1d3258ccc0cc462d144d3572fe344f19f1cb` — additive compatibility/rollback regressions passed all nine required workflow groups and merged signed as `38b27696d9d5feaaf6d8a8b85e1540e4f9bb16e8`.

These establish the evidence required to make the prior-path decision explicit. Canonical promotion remains contingent on this decision change itself passing exact-head CI and merging.

## Consumer migration evidence

PR #168 recorded that no separate production runtime consumer existed at inventory time. PR #169 introduced the bounded server-side runtime consumer through the accepted adapter contract and proved server-side tenant/session propagation, provenance preservation, required/optional failure behavior and absence of client-held service credentials.

## Rollback plan and evidence

Rollback routes the bounded runtime consumer back to the existing `KnowledgeClient` read contract or disables endpoint configuration; it does not substitute a broader knowledge/tool path. Required knowledge operations fail closed when the configured service is unavailable. Optional knowledge may report normalized unavailability only under the verified boundary.

PR #170 proves the pre-existing read contract remains usable without data, schema or write migration. No persistent-data migration is authorized by this ADR.

## Migration plan

1. Review and accept this ADR through normal PR/CI. **Completed by PR #165.**
2. Inventory actual ARIN knowledge consumers and direct zknowbase call sites. **Completed by PR #168.**
3. Add/extend tests first for the smallest real consumer migration. **Completed by PR #169.**
4. Migrate that consumer to the existing ARIN adapter contract without expanding authority. **Completed by PR #169.**
5. Prove rollback/compatibility without data/schema/write migration. **Completed by PR #170.**
6. Make the prior-path deprecation decision explicit. **This ADR retains the direct read path as rollback-only compatibility.**
7. Record exact-head evidence in the migration ledger and promote `ARIN-MIG-0008` only after this decision passes CI and merges.

## Decommission plan

No repository or service is decommissioned by this ADR. The pre-existing direct read path is retained as rollback-only compatibility and may not gain new runtime consumers. Removal requires a separate bounded, exact-head-evidenced change proving no active consumer depends on it and preserving an equivalent tested rollback mechanism. Archive/delete/rename/transfer of repositories is outside this decision.

## Decision evidence

- Source commit: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`
- Existing bounded integration: PRs #115, #122, #123, #124, #125; `ARIN-MIG-0008`
- ADR acceptance: PR #165 exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384`; signed merge `6762e442df18709772d10b792e39c9286a31ec02`
- Runtime consumer: PR #169 exact head `c6b2761dc9ca14e438ea7fb053ee4f8a70db6444`; signed merge `bd939aa95caeaf63783678b10d824410a03bbd5e`
- Compatibility/rollback: PR #170 exact head `37fa1d3258ccc0cc462d144d3572fe344f19f1cb`; signed merge `38b27696d9d5feaaf6d8a8b85e1540e4f9bb16e8`
- Prior path: retained rollback-only; no new consumers or authority
- Canonical promotion: pending exact-head CI/merge of this reconciliation
- Physical actuation: disabled; no actuator authority admitted
