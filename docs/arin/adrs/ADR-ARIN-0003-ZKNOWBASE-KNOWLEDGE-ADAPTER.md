# ADR-ARIN-0003: zknowbase Knowledge Adapter

## Metadata

- ADR ID: `ADR-ARIN-0003`
- Status: `accepted`
- Date: 2026-09-17
- Owner: ARIN Project Center
- Related capability: knowledge / grounded RAG
- Source repository/service: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`
- Target ARIN component: `backend/arin/knowledge.py`, `backend/arin/knowledge_write.py`

## Capability gap

ARIN needs grounded knowledge retrieval with provenance while keeping the independently owned zknowbase service outside the ZASI trust boundary. The bounded adapter foundation is already verified by PRs #115 and #122-#125. The API/service integration decision was accepted through PR #165 at exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384`, which passed the repository's required workflow groups and merged as signed commit `6762e442df18709772d10b792e39c9286a31ec02`. `ARIN-MIG-0008` still cannot become canonical until consumer migration/rollback evidence is reviewed.

## Decision

Use `api-service`. ZASI remains the canonical owner of ARIN tenant/session identity, policy/approval decisions, evidence mapping and required-versus-optional knowledge semantics. zknowbase remains the independently deployed owner of ingestion, retrieval, vector/semantic knowledge and source provenance.

Do not copy or vendor zknowbase into ZASI. The adapter is a narrow authenticated service boundary. Read-only search/query is the only admitted transport in the verified foundation. Write/ingest authorization may be evaluated by policy, but no mutation transport is admitted by this ADR.

This ADR is accepted for the bounded API/service integration mode. Acceptance does not promote `ARIN-MIG-0008` to canonical and does not claim production readiness. Canonical promotion additionally requires explicit consumer migration and rollback evidence.

## Alternatives considered

### Build knowledge/RAG directly in ZASI

Rejected. It duplicates zknowbase ownership and expands ZASI's data, embedding and vector-store trust surface.

### Copy or selectively port zknowbase into ZASI

Rejected for the current capability. The existing service contract is sufficient and preserves repository history, provenance and independent lifecycle ownership.

### Direct client access to zknowbase

Rejected. Browser/mobile clients must not receive zknowbase service credentials or bypass ZASI tenant/session/policy enforcement.

### Do nothing / defer

Safe but leaves Task 5 canonical promotion incomplete. The verified adapter may remain bounded/non-canonical until the remaining evidence is produced.

## Canonical ownership

- ZASI owns ARIN authentication context, tenant/session binding, policy/approval, adapter configuration, required/optional semantics, evidence normalization and audit correlation.
- zknowbase owns knowledge ingestion/storage/indexing/retrieval and source provenance behind its service API.
- The ARIN adapter owns bounded request/response translation only.
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
6. PR #165 exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384` — ADR acceptance candidate passed the required workflow groups and merged as signed commit `6762e442df18709772d10b792e39c9286a31ec02`.

These establish an accepted, verified adapter foundation, not canonical promotion or production readiness.

## Consumer migration evidence required before canonical promotion

Before `ARIN-MIG-0008` moves to `canonical`, record an exact bounded inventory of ARIN consumers and prove each migrated consumer uses the ARIN adapter contract rather than direct zknowbase credentials/API calls. Evidence must cover tenant/session propagation, provenance preservation, required/optional failure behavior and absence of client-held service credentials.

If no runtime consumer exists yet, record that fact explicitly; do not invent a migration. Canonical promotion remains blocked until a real consumer can be migrated and tested or the Project Center formally decides that the adapter itself is the only canonical consumer boundary.

## Rollback plan and evidence required

Rollback is configuration/consumer routing back to the prior knowledge-disabled or prior bounded adapter state; it must not silently substitute a broader knowledge or tool path. Required knowledge operations fail closed when the configured service is unavailable. Optional knowledge may report normalized unavailability only under the already verified boundary.

Before canonical promotion, add evidence that disabling/removing zknowbase endpoint configuration does not leak credentials, mutate knowledge data, bypass tenant/session policy, or turn a required lookup into an apparent success. No persistent-data migration is authorized by this ADR.

## Migration plan

1. Review and accept this ADR through normal PR/CI. **Completed by PR #165; reconciliation records the accepted state.**
2. Inventory actual ARIN knowledge consumers and direct zknowbase call sites.
3. Add/extend tests first for the smallest real consumer migration.
4. Migrate that consumer to the existing ARIN adapter contract without expanding authority.
5. Prove rollback by disabling adapter endpoint/configuration and verifying required fail-closed and optional normalized-unavailable behavior.
6. Record exact-head evidence in the migration ledger.
7. Promote `ARIN-MIG-0008` to canonical only after consumer and rollback evidence is merged.

## Decommission plan

No repository or service is decommissioned by this ADR. If a prior direct consumer path is discovered, retain it only for the documented migration window, remove it after compatibility/rollback evidence is green, and revoke any superseded credentials. Archive/delete/rename/transfer of repositories is outside this decision.

## Decision evidence

- Source commit: `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`
- Existing bounded integration: PRs #115, #122, #123, #124, #125; `ARIN-MIG-0008`
- ADR acceptance: PR #165 exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384`; signed merge `6762e442df18709772d10b792e39c9286a31ec02`
- Canonical promotion: blocked on consumer migration and rollback evidence
- Physical actuation: disabled; no actuator authority admitted
