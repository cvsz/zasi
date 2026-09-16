# ARIN Project Center Evidence Matrix

This matrix reconciles the evidence-backed ARIN Project Center state against merged implementation. It is intentionally conservative: source capability evidence does not imply ARIN runtime admission, and a verified bounded contract does not imply a live external service is enabled.

## Evidence rules

- Pin reusable source claims to an exact repository commit.
- Pin ARIN integration claims to exact pull-request heads and required workflow evidence.
- Treat `verified`, `partial`, `reference-only`, and `missing` as evidence states, not product-readiness labels.
- Never infer production readiness from roadmap or checklist state alone.
- Never promote physical actuation from documentation or simulator evidence alone; deterministic safety and HIL gates remain mandatory.

## Current evidence

| Capability | Canonical owner | Source / implementation evidence | ARIN evidence state | Runtime admission | Remaining promotion requirement |
|---|---|---|---|---|---|
| Project Center governance | `cvsz/zasi` | PR #107; `ARIN-MIG-0001` | `verified` | native/core | Keep governance and ledger synchronized with exact-head evidence. |
| Deterministic reference corpus | `cvsz/zasi` | PR #108 head `8fb26fc3560631aebbb643586e369a052a577f4a`; `ARIN-MIG-0002` | `verified` | test/evidence only | Extend corpus only for bounded regression needs. |
| Knowledge/RAG source | `cvsz/zknowbase` | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946`; source CI/security recorded in capability matrix | `verified` | independent service | Source remains independently owned. |
| ARIN knowledge contract/read/provenance/policy boundary | `cvsz/zasi` | PRs #115, #122, #123, #124, #125; `ARIN-MIG-0008` | `verified` | bounded ARIN adapter foundation | Integration ADR plus consumer migration/rollback evidence before canonical promotion. Write transport remains absent. |
| Voice/perception source patterns | `cvsz/zworkforce/packages/zarvis` | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis`; source ZARVIS/CodeQL evidence | `verified` | source/reference only | Task 7 ARIN-owned consent/session, retention, isolation and no-action-authority contracts. |
| ARIN voice/perception adapter | `cvsz/zasi` | No bounded ARIN adapter evidence yet | `missing` | disabled | Task 7 implementation and exact-head evidence. |
| ZCoder containment/MCP requirements | `cvsz/zasi` | PR #126 head `a8c4bc8b9f3700f96e8146e7064f6452b3dabb4e`; `ARIN-MIG-0009` | `verified` | policy/documentation boundary | Preserve fail-closed requirements in future transports. |
| ARIN tool capability descriptors/risk classes | `cvsz/zasi` | PR #127 head `c2f4ec7aa2c4f507bab6fadd2a8abc7f95d6acfb`; `ARIN-MIG-0010` | `verified` | native contract | No ambient authority; privileged/critical capabilities remain approval/policy bound. |
| Denied tool-authority regressions | `cvsz/zasi` | PR #128 head `bf08f733ce29573359bcff4c6b8935ebd68bd9d2`; `ARIN-MIG-0011` | `verified` | tests | Server-side denial remains authoritative. |
| ZCoder service-first adapter decision/contract | `cvsz/zasi` | ADR-ARIN-0002; PRs #129-#130; `ARIN-MIG-0012` | `verified` | transport-neutral contract only | Live service endpoint requires separate bounded admission. |
| ZCoder fake/local transport | `cvsz/zasi` | PR #132 head `5d01b318cd415e9b0f484eb0bec2467e6392e393`; PR #133 ledger reconciliation; `ARIN-MIG-0013` | `verified` | in-process fake/local only | Do not infer live ZCoder runtime authority. |
| Live ZCoder service endpoint | `cvsz/zasi` | No admitted endpoint evidence | `missing` | disabled | Separate service-endpoint contract, policy, transport, negative tests, rollback and exact-head evidence. |
| Mission-control patterns | `cvsz/zdash` | `cvsz/zdash@1c5c6b856cc3caeddefc90c9fb99a8449e4d35c5` | `reference-only` | none | Task 14 ARIN-owned implementation, permission/stale/reconnect tests and redacted diagnostics. |
| Installer/release patterns | `cvsz/zanything` | `cvsz/zanything@21f84667137ead7c818c5bb3df7eecfe7b790b2a`; source CodeQL/Gold Master evidence | `reference-only` | none | Task 15 ARIN-owned install/update/rollback/offline evidence. |
| Infrastructure | `cvsz/zasi` | No demonstrated gap requiring `z-platform` | `missing` | no external infra admitted | Admit only after an explicit ARIN infrastructure gap and ADR/evidence. |
| Deployment/edge | `cvsz/zasi` | No demonstrated gap requiring `zeaz-platform` | `missing` | no external deployment dependency admitted | Admit only after an explicit ARIN deployment gap and ADR/evidence. |
| Physical humanoid actuation | deterministic safety boundary | No simulator+safety+HIL release evidence proving physical enablement | `missing` | **DISABLED** | Tasks 11-13 and Task 16 safety/HIL release gates. |

## Task truth reconciliation

The implementation plan contains stale unchecked items for bounded work that has already been merged and evidenced. The migration ledger is authoritative for those completed slices until the plan is reconciled in a dedicated documentation change.

- Task 1 governance is verified by `ARIN-MIG-0001`.
- Task 2 curated source assessment sweep has evidence for the admitted source set, but this matrix and the capability matrix must remain synchronized as integrations advance.
- Task 5 bounded knowledge integration through required/optional degraded-mode behavior is verified by `ARIN-MIG-0008`; canonical promotion remains incomplete.
- Task 6 requirements, capability/risk contract, denial regressions, service-first ADR/contract, and fake/local transport are verified through `ARIN-MIG-0009` to `ARIN-MIG-0013`; a live ZCoder endpoint is not enabled or implied.
- Tasks 3-4 and 7-16 remain incomplete unless separately evidenced by later ledger entries.

## Safety invariant

Physical actuation is disabled. No evidence in this matrix authorizes direct LLM, browser, mobile, generic tool, MCP, raw joint, torque, velocity, PWM, or vendor-actuator control. Any future physical path must terminate at the deterministic safety supervisor and satisfy simulator and HIL release gates.