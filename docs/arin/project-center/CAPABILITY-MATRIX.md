# ARIN Project Center Capability Matrix

This matrix records evidence-backed reuse decisions. A repository is not promoted because a roadmap says a feature exists; each assessment is pinned to an exact source commit and records the narrow integration mode ARIN may use.

## Status vocabulary

- `verified` — the claimed source capability or bounded ARIN integration has exact evidence at the recorded commit/PR head. This does not imply broader production readiness.
- `partial` — useful implementation exists but required ARIN contracts/evidence are incomplete.
- `reference-only` — patterns may inform ARIN; no runtime dependency is approved.
- `missing` — the required capability was not evidenced at the assessed source commit.

## Capability ownership

| ARIN capability | Canonical owner | Source / adapter | Mode | Status | Evidence / constraints |
|---|---|---|---|---|---|
| Governed control plane, policy, approvals, events | `cvsz/zasi` | native | core | `verified` | Canonical ARIN owner; existing ZASI release/security gates remain authoritative. |
| Long-term document knowledge / RAG | `cvsz/zknowbase` | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | `api-service` | `verified` | Source exact-head CI/security verified. Keep Qdrant/Ollama/backend credentials behind zknowbase. |
| ARIN ↔ zknowbase bounded adapter foundation | `cvsz/zasi` | `backend/arin/knowledge.py`, `backend/arin/knowledge_write.py` | `api-service` | `verified` | PRs #115, #122-#125 and `ARIN-MIG-0008` verify read contract/transport, provenance, explicit write authorization gate and required/optional degraded behavior. Write transport remains absent; canonical promotion still requires ADR plus consumer/rollback evidence. |
| Voice/perception/action source patterns | `cvsz/zasi` | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | `api-service` or `reference-only` | `verified` | Source ZARVIS/CodeQL evidence verified. Reuse service/contracts only; no wholesale source copy. |
| ARIN ↔ ZARVIS voice/perception adapter | `cvsz/zasi` | future bounded adapter | `api-service` | `missing` | Requires consent/session tickets, retention/deletion, interruption/disconnect, isolation and explicit no-action-authority contract. |
| Bounded tools / MCP source patterns | `cvsz/zasi` | `cvsz/zcoder@7153e8b7a48e9d7f9f1976fae2b23f270ac44dab` | `api-service` / narrow adapter | `partial` | Source assessment remains conservative; ARIN extracted containment/security requirements without inheriting ambient authority. |
| ARIN ↔ ZCoder bounded adapter foundation | `cvsz/zasi` | `backend/arin/tools.py`, `backend/arin/zcoder_adapter.py` | narrow adapter | `verified` | PRs #126-#132 and `ARIN-MIG-0009`-`0013` verify containment requirements, capability/risk contracts, policy-denial regressions, service-first ADR/contract and fake/local transport. No live ZCoder endpoint or runtime authority is enabled. |
| Live ZCoder service endpoint | `cvsz/zasi` | future separately admitted endpoint | `api-service` | `missing` | Requires separate transport/policy/negative-test/rollback admission. |
| Mission-control UX / operations patterns | `cvsz/zasi` | `cvsz/zdash@1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` | `reference-only` | `reference-only` | Reuse information hierarchy/operations patterns only; no runtime dependency approved. |
| Enterprise installer / release patterns | `cvsz/zasi` | `cvsz/zanything@21f84667137ead7c818c5bb3df7eecfe7b790b2a` | `reference-only` | `reference-only` | Source CodeQL/Gold Master evidence verified; no ARIN readiness inheritance. |
| Infrastructure | `cvsz/zasi` | `cvsz/z-platform` | explicit dependency only | `missing` | No ARIN infrastructure gap has justified admission. |
| Deployment / edge | `cvsz/zasi` | `cvsz/zeaz-platform` | explicit dependency only | `missing` | No ARIN deployment gap has justified admission. |
| Physical humanoid actuation | deterministic safety boundary | none admitted | disabled | `missing` | Physical actuation remains disabled until simulator, deterministic safety and exact supported-adapter HIL release gates pass. |

## Source assessment pins

- zknowbase: `c71da3da3277d3cdd5f37435b7274c6f8f595946`; MIT; exact-head CI run 225 and Security run 105 succeeded.
- ZARVIS scope only: `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis`; MIT; ZARVIS run #143 and CodeQL run #785 succeeded.
- ZCoder: `7153e8b7a48e9d7f9f1976fae2b23f270ac44dab`; MIT; source remains independently owned and its source assessment remains conservative. ARIN-native bounded boundary evidence is recorded separately in `ARIN-MIG-0009`-`0013`.
- zDash: `1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5`; MIT; reference-only because exact-head CI/security and dependency/permission/realtime evidence remain incomplete.
- zAnything: `21f84667137ead7c818c5bb3df7eecfe7b790b2a`; MIT; exact-head CodeQL #56 and Gold Master Evidence #8 succeeded; reference-only.

## Promotion boundaries

A verified source capability does not verify an ARIN integration. A verified bounded ARIN contract/transport does not make the external service canonical or authorize additional authority. Canonical promotion follows the migration ledger requirements for accepted ADRs, consumer migration, compatibility/rollback evidence and deprecation decisions.

The initial curated evidence-only source sweep is complete. `z-platform` and `zeaz-platform` remain excluded unless an explicit ARIN infrastructure/deployment gap appears.

Physical actuation is disabled. No entry here authorizes direct LLM, browser, mobile, generic tool/MCP, raw joint, torque, velocity, PWM or vendor-actuator control.