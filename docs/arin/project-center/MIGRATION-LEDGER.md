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
| Knowledge/RAG | `cvsz/zknowbase` | `api-service` | `assessed` | Source capability verified at `c71da3da3277d3cdd5f37435b7274c6f8f595946`; ARIN adapter still requires ADR + contract tests before integration |
| Voice/perception/action patterns | `cvsz/zworkforce` → `packages/zarvis` | `api-service` or `reference-only` | `candidate` | Pending capability matrix; no wholesale port |
| Bounded tools/MCP | `cvsz/zcoder` | `api-service` / narrow adapter | `candidate` | Pending containment and contract evidence |
| Mission-control UX/ops patterns | `cvsz/zdash` | `reference-only` / selective compatible components | `candidate` | Pending license/dependency/evidence review |
| Enterprise installer/release patterns | `cvsz/zanything` | `reference-only` | `candidate` | Roadmap claims require implementation evidence before reuse |
| Infrastructure | `cvsz/z-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN infrastructure gap |
| Deployment/edge | `cvsz/zeaz-platform` | explicit dependency only | `candidate` | Admit only for a demonstrated ARIN deployment gap |

## Migration records

Add one row per accepted/rejected integration decision. Every non-candidate state must link an ADR except bootstrap governance and evidence-only source assessments that do not add a runtime dependency.

| ID | Capability | Source ref | Target | ADR | State | Exact-head evidence | Rollback evidence | Notes |
|---|---|---|---|---|---|---|---|---|
| `ARIN-MIG-0001` | Project Center governance | `cvsz/zasi@b8c1438318b1fe6393c5061c98c02a624ff8ec63` | `docs/arin/project-center` | N/A (bootstrap governance) | `verified` | At exact PR head: Production GO Gate #100, Security Evidence Pack #110, Lint #389, Immutable Rollback #78, Docker #389, HA/Canary #76, Backup/DR #109, CodeQL #391, ZASI CI/CD #409 all succeeded; merged by PR #107 | Documentation-only changes can be reverted without runtime/data mutation | Governance evidence is now exact-head verified |
| `ARIN-MIG-0002` | Deterministic reference-corpus evidence contracts | `cvsz/zasi@8fb26fc3560631aebbb643586e369a052a577f4a` | `tests/corpus` | N/A (test/evidence hardening) | `verified` | At exact PR #108 head: Lint #391, Production GO Gate #102, Security Evidence Pack #112, Immutable Rollback #79, Docker #391, HA/Canary #77, CodeQL #393, Backup/DR #111, ZASI CI/CD #411 all succeeded | Test/corpus metadata only; revert PR #108 merge if evidence contract is incompatible | PR #108 merged as `b3f4161565577b0cfdebb038158bccce85e2d8bf` |
| `ARIN-MIG-0003` | Knowledge/RAG source assessment | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | future ZASI knowledge adapter | Pending integration ADR | `assessed` | Source commit GitHub-verified; MIT license; exact-head zknowbase `CI` run #225 and `Security` run #105 succeeded | No runtime dependency or source copy added; assessment can be dropped without system mutation | Source capability verified; ARIN adapter remains unimplemented and must not be called verified |

## Promotion rules

An entry can move to `verified` only when evidence is attached to the exact integration head. An entry can move to `canonical` only when its ADR is accepted, consumers have migrated, compatibility/rollback behavior is tested, and the prior owner/path has an explicit deprecation decision.

Physical humanoid integrations additionally require deterministic safety-supervisor evidence and hardware-in-the-loop evidence for the exact supported adapter before any physical actuation can be considered canonical.

## Portfolio boundary

ARIN work must not archive, delete, rename, transfer, or mass-copy unrelated repositories. Portfolio cleanup is a separate approved program with its own inventory, migration evidence and rollback process.
