# ARIN Project Center Capability Matrix

This matrix records evidence-backed reuse decisions. A repository is not promoted because a roadmap says a feature exists; each assessment is pinned to an exact source commit and records the narrow integration mode ARIN may use.

## Status vocabulary

- `verified` — the claimed source capability and applicable CI/security evidence were verified at the recorded source commit. This does not by itself verify an ARIN integration.
- `partial` — useful implementation exists but required ARIN contracts/evidence are incomplete.
- `reference-only` — patterns may inform ARIN; no runtime dependency is approved.
- `missing` — the required capability was not evidenced at the assessed source commit.

## Capability ownership

| ARIN capability | Canonical owner | Source / adapter | Mode | Source status | Evidence / constraints |
|---|---|---|---|---|---|
| Governed control plane, policy, approvals, events | `cvsz/zasi` | native | core | `verified` | Canonical ARIN owner; existing ZASI release/security gates remain authoritative. |
| Long-term document knowledge / RAG | `cvsz/zknowbase` | `cvsz/zknowbase@c71da3da3277d3cdd5f37435b7274c6f8f595946` | `api-service` | `verified` | Source head is a verified GitHub merge commit; MIT licensed. Exact-head `CI` run 225 and `Security` run 105 completed successfully. Keep Qdrant/Ollama/backend credentials behind zknowbase; ARIN consumes scoped service contracts rather than copying the repository. |
| ARIN ↔ zknowbase contract adapter | `cvsz/zasi` | future bounded adapter | `api-service` | `missing` | Source service is evidenced, but ARIN contract tests, timeout/failure semantics, scoped credential handling and provenance mapping are not implemented/verified yet. Task 5 remains blocked on that bounded integration slice. |
| Voice/perception/action patterns | `cvsz/zasi` | `cvsz/zworkforce@634599e02f85d42a63535eb8c5410d6383f64d36/packages/zarvis` | `api-service` or `reference-only` | `verified` | Source commit is GitHub-signature verified and MIT licensed. Exact-head push workflows include successful `ZARVIS` run #143 and `CodeQL` run #785. Reuse service/contracts only; do not copy the package wholesale or treat source verification as ARIN integration verification. |
| ARIN ↔ ZARVIS voice/perception adapter | `cvsz/zasi` | future bounded adapter | `api-service` | `missing` | Requires ARIN consent/session tickets, retention/deletion semantics, interruption/disconnect tests, cross-session isolation and explicit no-action-authority contract before integration. |
| Bounded tools / MCP | `cvsz/zasi` | `cvsz/zcoder` | pending assessment | `partial` | Not yet promoted; containment and adapter contracts require exact-head evidence. |
| Mission-control UX / operations patterns | `cvsz/zasi` | `cvsz/zdash` | `reference-only` pending assessment | `reference-only` | No runtime dependency approved. License/dependency/component evidence still required. |
| Enterprise installer / release patterns | `cvsz/zasi` | `cvsz/zanything` | `reference-only` pending assessment | `reference-only` | Roadmap/ledger claims are not implementation evidence; exact source evidence is still required. |
| Infrastructure | `cvsz/zasi` | `cvsz/z-platform` | explicit dependency only | `missing` | No ARIN infrastructure gap has yet justified admission. |
| Deployment / edge | `cvsz/zasi` | `cvsz/zeaz-platform` | explicit dependency only | `missing` | No ARIN deployment gap has yet justified admission. |

## zknowbase assessment — 2026-09-15

- Exact source commit: `c71da3da3277d3cdd5f37435b7274c6f8f595946` (`main`).
- Commit provenance: GitHub-verified merge commit.
- License: MIT, copyright 2026 cvsz.
- Exact-head workflow evidence: `CI` run `32569233252` / run number 225 = success; `Security` run `32569233221` / run number 105 = success.
- Repository release-safety evidence names required CI contexts (`backend`, `retrieval-quality`, `performance`, `frontend`, `compose`) and security contexts (`python-dependencies`, `frontend-dependencies`, `secrets`, `dependency-review`).
- ARIN decision: retain zknowbase as an independently owned knowledge service. Do not copy its backend, Qdrant state, provider credentials or frontend into ZASI.
- Promotion boundary: this assessment promotes only the **source knowledge/RAG capability** to `verified`. The ARIN integration remains `missing` until Task 5 supplies contract tests and exact-head integration evidence.

## ZARVIS assessment — 2026-09-15

- Exact source commit: `634599e02f85d42a63535eb8c5410d6383f64d36` (`cvsz/zworkforce` `main`).
- Commit provenance: GitHub-signature verified commit.
- License: MIT, copyright 2026 cvsz.
- Exact-head workflow evidence: GitHub Actions reports six workflows for this SHA; confirmed successful `ZARVIS` run `34801287433` / run number 143 and successful `CodeQL` run `34801287496` / run number 785.
- Assessed scope is only `packages/zarvis`; the surrounding zWorkforce platform is not admitted as an ARIN dependency by this assessment.
- ARIN decision: keep ZARVIS independently owned. Prefer its service/versioned-contract boundary or use it as reference evidence. Do not wholesale-port voice, perception, task, action, or console code into ZASI.
- Safety boundary: source verification does not authorize physical actuation. Perception/voice output has no direct actuator authority in ARIN; any future robot path must terminate at the deterministic safety supervisor and satisfy simulator/HIL gates.
- Promotion boundary: source voice/perception/action patterns are `verified`; the ARIN adapter remains `missing` until Task 7 provides consent/session, retention, isolation, interruption/disconnect and no-action-authority contract tests with exact-head integration evidence.

## Next assessments

Assess `cvsz/zcoder`, then `cvsz/zdash` and `cvsz/zanything` using the same exact-head evidence standard. `z-platform` and `zeaz-platform` remain excluded unless an explicit ARIN infrastructure/deployment gap appears.
