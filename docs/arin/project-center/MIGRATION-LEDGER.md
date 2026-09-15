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
| Knowledge/RAG | `cvsz/zknowbase` | `api-service` | `assessed` | Source capability verified at `c71da3da3277d3cdd5f37435b7274c6f8f595946`; bounded ARIN read-contract work has started but is not verified until its PR head is green |
| Voice/perception/action patterns | `cvsz/zworkforce` → `packages/zarvis` | `api-service` or `reference-only` | `assessed` | Source patterns verified at `634599e02f85d42a63535eb8c5410d6383f64d36`; ARIN adapter remains unimplemented and no source copy is approved |
| Bounded tools/MCP | `cvsz/zcoder` | `api-service` / narrow adapter | `candidate` | Source is pinned and MIT licensed, but the assessment is incomplete: public contracts, alternatives/risks, and reproducible exact-head containment/MCP CI/security evidence still require review; ARIN adapter is missing |
| Mission-control UX/ops patterns | `cvsz/zdash` | `reference-only` | `candidate` | Source pinned at `1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` and MIT licensed, but exact-head CI/security and full dependency/permission/realtime risk evidence remain incomplete; no runtime dependency approved |
| Enterprise installer/release patterns | `cvsz/zanything` | `reference-only` | `assessed` | Source pinned at `21f84667137ead7c818c5bb3df7eecfe7b790b2a`, MIT licensed, with exact-head successful CodeQL #56 and Gold Master Evidence #8; reuse remains reference-only and does not confer ARIN release readiness |
| Infrastructure | `cvsz/z-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN infrastructure gap |
| Deployment/edge | `cvsz/zeaz-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN deployment gap |

## Migration records

Add one row per accepted/rejected integration decision. Every non-candidate state must link an ADR except bootstrap governance and evidence-only source assessments that do not add a runtime dependency.

| ID | Capability | Source ref | Target | ADR | State | Exact-head evidence | Rollback evidence | Notes |
|---|---|---|---|---|---|---|---|---|
| `ARIN-MIG-0001` | Project Center governance | `cvsz/zasi@b8c1438318b1fe6393c5061c98c02a624ff8ec63` | `docs/arin/project-center` | N/A (bootstrap governance) | `verified` | At exact PR head: Production GO Gate #100, Security Evidence Pack #110, Lint #389, Immutable Rollback #78, Docker #389, HA/Canary #76, Backup/DR #109, CodeQL #391, ZASI CI/CD #409 all succeeded; merged by PR #107 | Documentation-only changes can be reverted without runtime/data mutation | Governance evidence is now exact-head verified |
| `ARIN-MIG-0002` | Deterministic reference-corpus evidence contracts | `cvsz/zasi@8fb26fc3560631aebbb643586e369a052a577f4a` | `tests/corpus` | N/A (test/evidence hardening) | `verified` | At exact PR #108 head: Lint #391, Production GO Gate #102, Security Evidence Pack #112, Immutable Rollback #79, Docker #391, HA/Canary #77, CodeQL #393, Backup/DR #111, ZASI CI/CD #411 all succeeded | Test/corpus metadata only; revert PR #108 merge if evidence contract is incompatible | PR #108 merged as `b3f4161565577b0cfdebb038158bccce85e2d8bf` |
| `ARIN-MIG-0003` | Knowledge/RAG source assessment | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | future ZASI knowledge adapter | Pending integration ADR | `assessed` | Source commit GitHub-verified; MIT license; exact-head zknowbase `CI` run #225 and `Security` run #105 succeeded | No runtime dependency or source copy added; assessment can be dropped without system mutation | Source capability verified; ARIN adapter remains unimplemented and must not be called verified |
| `ARIN-MIG-0004` | Voice/perception/action source assessment | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | future bounded ZASI voice/perception adapter | Pending integration ADR | `assessed` | Source commit GitHub-signature verified; MIT license; exact-head `ZARVIS` run #143 and `CodeQL` run #785 succeeded | No runtime dependency or source copy added; remove this evidence-only assessment without runtime/data mutation | Source patterns verified only; ARIN integration remains missing and physical actuation stays disabled |
| `ARIN-MIG-0005` | Bounded tools/MCP source assessment | `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab` | future bounded ZASI tool adapter | Pending integration ADR | `candidate` | Source commit GitHub-signature verified and MIT licensed; source contains pinned CodeQL/release/container/SBOM workflow dependencies, but public contract/alternatives review and reproducible exact-head containment/MCP CI/security evidence are not yet complete | No runtime dependency/source copy added; remove evidence-only candidate without runtime/data mutation | Source remains `partial`; retain candidate until the ledger's assessed-state requirements are actually satisfied |
| `ARIN-MIG-0006` | Mission-control UX/operations source assessment | `cvsz/zdash@1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` | future ARIN mission-control implementation | Pending integration ADR if source components are ever ported | `candidate` | Source commit GitHub-signature verified and MIT licensed; exact-SHA PR workflow query returned no runs, so exact-head CI/security is not claimed | Evidence-only documentation can be reverted; no zDash runtime dependency or source copy added | Keep `reference-only`; dependency provenance, permission/stale/reconnection behavior and ARIN Task 14 tests remain required |
| `ARIN-MIG-0007` | Enterprise installer/release source assessment | `cvsz/zanything@21f84667137ead7c818c5bb3df7eecfe7b790b2a` | future ARIN installer/release implementation | N/A (evidence-only reference assessment) | `assessed` | Source commit GitHub-signature verified; MIT license; exact-head `CodeQL` run #56 and `Gold Master Evidence` run #8 succeeded; provenance write permissions are isolated to the attestation job | Evidence-only documentation can be reverted; no zAnything runtime dependency or source copy added | Reference-only: source release/provenance patterns are evidenced, but ARIN must produce its own installer/update/rollback/offline and Gold Master evidence |
| `ARIN-MIG-0008` | ARIN ↔ zknowbase read-contract foundation | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | `backend/app/arin/knowledge.py` | Pending integration ADR before runtime transport is enabled | `integrating` | Contract tests added on PR branch; exact-head GitHub Actions evidence required before promotion | Delete/disable the ARIN contract module; no network transport, write scope, data migration, credential store, or source copy is introduced by this slice | Read-only search/query request construction only; tenant context, scoped key and bounded timeout fail closed; physical actuation unaffected |

## Promotion rules

An entry can move to `verified` only when evidence is attached to the exact integration head. An entry can move to `canonical` only when its ADR is accepted, consumers have migrated, compatibility/rollback behavior is tested, and the prior owner/path has an explicit deprecation decision.

Physical humanoid integrations additionally require deterministic safety-supervisor evidence and hardware-in-the-loop evidence for the exact supported adapter before any physical actuation can be considered canonical.

## Portfolio boundary

ARIN work must not archive, delete, rename, transfer, or mass-copy unrelated repositories. Portfolio cleanup is a separate approved program with its own inventory, migration evidence and rollback process.
