# ARIN Project Center Migration Ledger

This is the evidence ledger for repository/service admission and consolidation into ARIN. It is not a portfolio archive list.

## State machine

```text
candidate -> assessed -> approved -> integrating -> verified -> canonical
     |          |           |             |           |
     +----------+-----------+-------------+-----------> rejected
                            |
                            +-------------------------> rolled-back
```

### State requirements

| State | Required evidence |
|---|---|
| `candidate` | Concrete ARIN capability gap and proposed source owner |
| `assessed` | Current source commit, license/provenance, contracts, CI/security evidence, alternatives and risks reviewed |
| `approved` | Accepted ADR naming canonical owner, integration mode, migration and rollback plan |
| `integrating` | Bounded implementation PR with tests; default-safe behavior preserved |
| `verified` | Required unit/contract/integration/security/operational evidence green at the exact integration head |
| `canonical` | Consumer migration complete, ownership documented, rollback proven, old path deprecation recorded |
| `rejected` | Reason and evidence retained; no runtime dependency added |
| `rolled-back` | Rollback trigger, recovery evidence, resulting canonical owner and follow-up recorded |

No entry may skip directly from `candidate` to `canonical`.

## Current curated ARIN set

The following entries are admitted only for assessment. Inclusion here does **not** claim production readiness or authorize source copying.

| Capability | Repository / scope | Intended mode | State | Canonical decision |
|---|---|---|---|---|
| ARIN governed control plane | `cvsz/zasi` | native/core | `canonical` | ZASI owns ARIN policy, approvals, events and core contracts |
| Knowledge/RAG | `cvsz/zknowbase` | `api-service` | `assessed` | Source capability verified at `c71da3da3277d3cdd5f37435b7274c6f8f595946`; bounded ARIN read transport/provenance, fail-closed write authorization, and explicit required/optional degraded-mode policy are integrating and remain non-canonical until exact-head evidence and ADR requirements pass |
| Voice/perception/action patterns | `cvsz/zworkforce` → `packages/zarvis` | `api-service` or `reference-only` | `assessed` | Source patterns verified at `634599e02f85d42a63535eb8c5410d6383f64d36`; ARIN adapter remains unimplemented and no source copy is approved |
| Bounded tools/MCP | `cvsz/zcoder` | `api-service` / narrow adapter | `candidate` | Source is pinned and MIT licensed, but the assessment is incomplete: public contracts, alternatives/risks, and reproducible exact-head containment/MCP CI/security evidence still require review; ARIN adapter is missing |
| Mission-control UX/ops patterns | `cvsz/zdash` | `reference-only` | `candidate` | Source pinned at `1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` and MIT licensed, but exact-head CI/security and full dependency/permission/realtime risk evidence remain incomplete; no runtime dependency approved |
| Enterprise installer/release patterns | `cvsz/zanything` | `reference-only` | `assessed` | Source pinned at `21f84667137ead7c818c5bb3df7eecfe7b790b2a`, MIT licensed, with exact-head successful CodeQL #56 and Gold Master Evidence #8; reuse remains reference-only and does not confer ARIN release readiness |
| Infrastructure | `cvsz/z-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN infrastructure gap |
| Deployment/edge | `cvsz/zeaz-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN deployment gap |

## Migration records

| ID | Capability | Source ref | Target | ADR | State | Exact-head evidence | Rollback evidence | Notes |
|---|---|---|---|---|---|---|---|---|
| `ARIN-MIG-0001` | Project Center governance | `cvsz/zasi@b8c1438318b1fe6393c5061c98c02a624ff8ec63` | `docs/arin/project-center` | N/A (bootstrap governance) | `verified` | Exact PR #107 head passed required gates | Documentation-only changes can be reverted | Governance evidence verified |
| `ARIN-MIG-0002` | Deterministic reference-corpus evidence contracts | `cvsz/zasi@8fb26fc3560631aebbb643586e369a052a577f4a` | `tests/corpus` | N/A | `verified` | Exact PR #108 head passed required gates | Revert PR #108 merge | Evidence contract verified |
| `ARIN-MIG-0003` | Knowledge/RAG source assessment | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | ZASI knowledge adapter | Pending integration ADR | `assessed` | Source commit verified; source CI/Security evidenced | Drop integration without system mutation | Source assessment only |
| `ARIN-MIG-0004` | Voice/perception/action source assessment | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | future bounded adapter | Pending integration ADR | `assessed` | Source signature and ZARVIS/CodeQL evidence recorded | No runtime dependency/source copy | Physical actuation disabled |
| `ARIN-MIG-0005` | Bounded tools/MCP source assessment | `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab` | future bounded tool adapter | Pending integration ADR | `candidate` | Assessment incomplete | No runtime dependency/source copy | Remains candidate |
| `ARIN-MIG-0006` | Mission-control UX/operations source assessment | `cvsz/zdash@1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` | future ARIN mission control | Pending if source ported | `candidate` | Exact-head CI/security not claimed | Evidence-only documentation reversible | Reference-only |
| `ARIN-MIG-0007` | Enterprise installer/release source assessment | `cvsz/zanything@21f84667137ead7c818c5bb3df7eecfe7b790b2a` | future ARIN installer/release | N/A | `assessed` | Exact-head CodeQL and Gold Master Evidence succeeded | Evidence-only documentation reversible | Reference-only |
| `ARIN-MIG-0008` | ARIN ↔ zknowbase integration | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | `backend/arin/knowledge.py`, `backend/arin/knowledge_write.py` | Pending integration ADR before production enablement | `integrating` | PR #115 contract foundation, PR #122 read transport, PR #123 provenance mapping, and PR #124 write-policy gate passed exact-head gates; current required/optional degraded-mode slice requires its own exact-head evidence | Disable/remove ARIN knowledge clients; no data migration, credential store, or source copy | Required reads fail closed on zknowbase unavailability; optional reads may explicitly degrade only for transport unavailability and never mask authorization, malformed-response, tenant, or provenance failures. Write transport remains absent; physical actuation unaffected |

## Promotion rules

An entry can move to `verified` only when evidence is attached to the exact integration head. An entry can move to `canonical` only when its ADR is accepted, consumers have migrated, compatibility/rollback behavior is tested, and the prior owner/path has an explicit deprecation decision.

Physical humanoid integrations additionally require deterministic safety-supervisor evidence and hardware-in-the-loop evidence for the exact supported adapter before any physical actuation can be considered canonical.

## Portfolio boundary

ARIN work must not archive, delete, rename, transfer, or mass-copy unrelated repositories. Portfolio cleanup is a separate approved program with its own inventory, migration evidence and rollback process.
