# ARIN Project Center Migration Ledger

This is the evidence ledger for repository/service admission and consolidation into ARIN. It is not a portfolio archive list.

## State machine

`candidate -> assessed -> approved -> integrating -> verified -> canonical`, with `rejected` and `rolled-back` terminal alternatives. No entry may skip directly from `candidate` to `canonical`.

A `verified` entry requires exact integration-head evidence. `canonical` additionally requires accepted ownership/ADR where applicable, consumer migration, compatibility/rollback evidence and an explicit prior-path deprecation decision.

## Current curated ARIN set

| Capability | Repository / scope | Intended mode | State | Canonical decision |
|---|---|---|---|---|
| ARIN governed control plane | `cvsz/zasi` | native/core | `canonical` | ZASI owns ARIN policy, approvals, events and core contracts. |
| Knowledge/RAG | `cvsz/zknowbase` | `api-service` | `assessed` | Source verified; bounded ARIN adapter foundation is separately `verified` as `ARIN-MIG-0008`; canonical promotion requires ADR + consumer/rollback evidence. |
| Voice/perception patterns | `cvsz/zworkforce/packages/zarvis` | `api-service` / reference | `assessed` | Source verified; ARIN Task 7 adapter is not implemented. |
| Bounded tools/MCP | `cvsz/zcoder` | narrow adapter | `approved` | ADR accepted; ARIN contract/fake-local transport verified through `ARIN-MIG-0013`; live endpoint disabled. |
| Mission-control patterns | `cvsz/zdash` | reference-only | `candidate` | No runtime dependency approved. |
| Installer/release patterns | `cvsz/zanything` | reference-only | `assessed` | Source release evidence verified; no ARIN readiness inheritance. |
| Infrastructure | `cvsz/z-platform` | explicit dependency only | `candidate` | No demonstrated ARIN gap. |
| Deployment/edge | `cvsz/zeaz-platform` | explicit dependency only | `candidate` | No demonstrated ARIN gap. |

## Migration records

| ID | Capability | Source ref | Target | State | Exact-head evidence / boundary |
|---|---|---|---|---|---|
| `ARIN-MIG-0001` | Project Center governance | `cvsz/zasi@b8c1438318b1fe6393c5061c98c02a624ff8ec63` | `docs/arin/project-center` | `verified` | PR #107 exact head passed required gates; documentation-only rollback. |
| `ARIN-MIG-0002` | Deterministic reference corpus | `cvsz/zasi@8fb26fc3560631aebbb643586e369a052a577f4a` | `tests/corpus` | `verified` | PR #108 exact head passed required gates. |
| `ARIN-MIG-0003` | Knowledge/RAG source assessment | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | ZASI knowledge adapter | `assessed` | Source CI/security evidenced; source remains independently owned. |
| `ARIN-MIG-0004` | Voice/perception source assessment | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | future bounded adapter | `assessed` | Source ZARVIS/CodeQL evidence recorded; no runtime dependency/source copy; physical actuation disabled. |
| `ARIN-MIG-0005` | Bounded tools/MCP source assessment | `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab` | bounded tool adapter | `approved` | `ADR-ARIN-0002` accepted; no live runtime authority. |
| `ARIN-MIG-0006` | Mission-control source assessment | `cvsz/zdash@1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` | future ARIN mission control | `candidate` | Reference-only; exact-head readiness not claimed. |
| `ARIN-MIG-0007` | Installer/release source assessment | `cvsz/zanything@21f84667137ead7c818c5bb3df7eecfe7b790b2a` | future ARIN installer/release | `assessed` | Exact-head CodeQL and Gold Master Evidence succeeded; reference-only. |
| `ARIN-MIG-0008` | ARIN ↔ zknowbase bounded integration | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | `backend/arin/knowledge.py`, `backend/arin/knowledge_write.py` | `verified` | PRs #115, #122-#125 verify contract/read transport/provenance/write-policy gate/degraded behavior. Write transport absent; canonical promotion blocked on ADR + consumer/rollback evidence. |
| `ARIN-MIG-0009` | Tool/MCP security requirements | `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab` | `docs/arin/integrations/ZCODER.md` | `verified` | PR #126 head `a8c4bc8b9f3700f96e8146e7064f6452b3dabb4e`, nine gates. No actuator authority. |
| `ARIN-MIG-0010` | Tool capability/risk contract | same ZCoder source | `backend/arin/tools.py` | `verified` | PR #127 head `c2f4ec7aa2c4f507bab6fadd2a8abc7f95d6acfb`, nine gates; omitted authority defaults denied. |
| `ARIN-MIG-0011` | Denied-authority regressions | `cvsz/zasi@397583d7afdd7085409610d08ce357cc94d959e7` | tool tests | `verified` | PR #128 head `bf08f733ce29573359bcff4c6b8935ebd68bd9d2`, nine gates; policy denial remains authoritative. |
| `ARIN-MIG-0012` | ZCoder service-first adapter decision/contract | pinned ZCoder source | `backend/arin/zcoder_adapter.py` | `verified` | ADR accepted; PR #130 head `7c45e8ab807d0451d30afd252b3a49285c224399`, nine gates. Transport-neutral only. |
| `ARIN-MIG-0013` | ZCoder fake/local transport | `cvsz/zasi@5d01b318cd415e9b0f484eb0bec2467e6392e393` | `backend/arin/zcoder_adapter.py` | `verified` | PR #132 exact head passed nine gates; validates capability/identity/timeout/cancellation/result bounds/failure normalization/token non-inheritance. Live endpoint disabled. |
| `ARIN-MIG-0014` | Project Center evidence/checklist truth reconciliation | `cvsz/zasi@10fb2fa7bb3b12cd1cd75626d47f70de945e9099` | `docs/arin/project-center` | `verified` | PR #135 head `d2b624918a4d3aec76916eda3e00616dff91bead` passed all nine required gates and merged as signed main `b0f5a5725fbcfaea53fb3e0135b35f5ca483d596`. Documentation truth now reflects bounded verified work without claiming live ZCoder runtime or later ARIN tasks. |
| `ARIN-MIG-0015` | ARIN legacy identity/compatibility inventory | `cvsz/zasi@3a5dc16fa2eebdbd2d8d67da442c5a771bddf49a`; `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | `docs/arin/ARIN_IDENTITY_AND_COMPATIBILITY.md` | `verified` | PR #136 exact head `4a211f2f7701f9dcd9f0a01c9fbe43147455e38b` passed all nine required gates before merge. Inventory separates ARIN display identity from stable legacy machine identifiers, preserves retired `/api/jarvis/*` fail-closed semantics. Documentation-only; no runtime dependency, source copy, alias authority, or actuation path. |
| `ARIN-MIG-0016` | Legacy JARVIS stable-route regression contract | `cvsz/zasi@04760b42f4f46ad4950e2982e444b713e99872e3` | `tests/test_api.py` | `verified` | PR #137 exact head `04760b42f4f46ad4950e2982e444b713e99872e3` passed all nine required gates before merge: Production GO, Lint, Security Evidence, HA/Canary, Immutable Rollback, CodeQL, Docker, Backup/DR and ZASI CI/CD. Both `/api/jarvis/chat` and `/api/jarvis/stream` remain HTTP 410; no endpoint or alias execution authority was enabled. |
| `ARIN-MIG-0017` | ARIN identity compatibility regression tests | `cvsz/zasi@086bc8a030b69043b46fbd11501013ac83ad8f2a` | `tests/test_arin_identity_compatibility.py` | `verified` | 22 regression tests covering all 8 JARVIS/ZARVIS stable machine identifiers from ARIN-MIG-0015: retired HTTP 410 routes, persona key, default fallback, OpenAPI spec, UI route provenance, container image name, acoustic profile, package keyword non-authority, and alias authority isolation. All 22 tests pass. Merged via `arin/task3-identity-regression-tests` into main. |
| `ARIN-MIG-0018` | Tenant/session schema isolation tests | `cvsz/zasi@2bc5a53` | `tests/test_arin_session_schema.py` | `verified` | 19 tests covering session tenant isolation (ScopeViolation on cross-tenant access), authentication tenant matching, and contract payload rejection (unknown keys, missing fields, invalid enums). All 19 tests pass. Exact-head evidence for Task 4 first bounded slice. |
| `ARIN-MIG-0019` | Versioned canonical contracts (Session, Plan, Approval) | `cvsz/zasi@beb3488` | `src/control_plane/contracts/contracts.py` | `verified` | Versioned v1.0.0 contracts for SessionCreateRequest, SessionRenewRequest, SessionResponse, PlanCreateRequest, PlanStep, ApprovalSubmitRequest, ApprovalResponse. All contracts use StrictModel (extra='forbid') to reject incompatible payloads. 33 contract validation tests pass. |
| `ARIN-MIG-0020` | Canonical v1 OpenAPI/client artifact generator | `cvsz/zasi@1caebc064cbd644770ae5bc2503fad6c5c52415a` | `scripts/generate_arin_contract_artifacts.py`, `tests/test_arin_contract_artifacts.py` | `verified` | PR #141 exact head passed all nine required gates: Security Evidence, Production GO, Lint, Docker, CodeQL, Backup/DR, HA/Canary, Immutable Rollback and ZASI CI/CD. Generator derives schema-only OpenAPI 3.1 components and a dependency-free TypeScript type surface from canonical v1.0.0 contracts; no runtime route, provider credential, live tool authority, infrastructure dependency or actuator path was admitted. |

## Safety and portfolio boundary

Physical actuation remains disabled. No source assessment, bounded adapter, simulator, documentation or cognitive/tool output authorizes raw joint, torque, velocity, PWM or vendor-actuator commands. Physical integration additionally requires deterministic safety-supervisor and exact supported-adapter HIL evidence.

ARIN work must not archive, delete, rename, transfer or mass-copy unrelated repositories. Portfolio cleanup is a separate approved program.