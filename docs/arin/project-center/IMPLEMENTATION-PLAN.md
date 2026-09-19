# ARIN Project Center Implementation Plan

> **For agentic workers:** Execute task-by-task using bounded, exact-head-evidenced changes. Checkboxes record verified slices, not aspirational roadmap state.

**Goal:** Establish `cvsz/zasi` as the curated ARIN Project Center, integrate only repositories ARIN truly needs, and deliver ARIN incrementally without collapsing the `cvsz` portfolio into a monolith.

**Architecture:** ZASI is the canonical governed control plane. Prefer API/service contracts and narrow adapters. Physical humanoid actuation remains behind a deterministic fail-closed safety boundary and is disabled until simulator, deterministic safety and HIL release gates pass.

**Spec:** `docs/arin/ARIN_MASTER_ARCHITECTURE_SPECIFICATION.md`

## Global Constraints

- Curated set: `zasi`, `zknowbase`, `zworkforce/packages/zarvis`, `zcoder`, `zdash`, `zanything`; `z-platform` and `zeaz-platform` only for explicit demonstrated infrastructure/deployment gaps.
- Preserve repository history and ownership. Do not wholesale-copy repositories.
- Browser/mobile clients never receive provider secrets or unrestricted service credentials.
- LLM/mobile/web/tool output never directly controls raw actuators.
- Physical actuation remains disabled until deterministic safety and exact supported-adapter HIL gates pass.

### Task 1: Establish Project Center governance — `verified`

- [x] ADR template with capability gap, alternatives, owner, integration mode, security/privacy/safety, license/provenance, evidence, migration, rollback and decommission requirements.
- [x] Migration state machine: `candidate -> assessed -> approved -> integrating -> verified -> canonical`, plus rejected/rolled-back.
- [x] Exact PR #107 head evidence recorded by `ARIN-MIG-0001`.
- [x] Governance files merged without runtime behavior change.

### Task 2: Build exact repository capability/evidence matrix — `verified foundation; continuously maintained`

- [x] Assess curated repository source heads, licenses, CI/security evidence and reuse boundaries.
- [x] Record one canonical ARIN owner per capability and narrow source/adapter modes.
- [x] Classify evidence as `verified`, `partial`, `reference-only`, or `missing`.
- [x] Pin source/integration commit and PR evidence in `CAPABILITY-MATRIX.md`, `EVIDENCE-MATRIX.md`, and `MIGRATION-LEDGER.md`.
- [x] Keep production-readiness claims independent from roadmap/checklist state.

### Task 3: ARIN compatibility and identity migration — `verified`

- [x] Inventory user-visible and API-stable JARVIS/ZARVIS names in ZASI and selected ZARVIS scope (`docs/arin/ARIN_IDENTITY_AND_COMPATIBILITY.md`; `ARIN-MIG-0015` verified at PR #136).
- [x] Define stable IDs versus ARIN display/product names (stable/machine vs display identity policy recorded in `ARIN_IDENTITY_AND_COMPATIBILITY.md`).
- [x] Define compatibility aliases and deprecation windows before public-contract changes (rules 1–7 in `ARIN_IDENTITY_AND_COMPATIBILITY.md`; no calendar deadline invented).
- [x] Add regression tests before executable/API identifier renames (`tests/test_arin_identity_compatibility.py`; 22 tests pass; merged into main via `arin/task3-identity-regression-tests`, `ARIN-MIG-0017` verified).

### Task 4: Canonical ARIN contracts — `verified`

- [x] Write schema tests first for tenant/session isolation and incompatible payload rejection (`tests/test_arin_session_schema.py`; 19 tests pass; `ARIN-MIG-0018` verified).
- [x] Define stable versioned sessions, intents, plans, approvals contracts independent of UI/vendor SDKs (`src/control_plane/contracts/contracts.py`: Session, Plan, Approval contracts v1.0.0; `ARIN-MIG-0019` verified; 33 tests pass).
- [x] Generate OpenAPI/client artifacts using repository conventions (PR #141 exact head `1caebc064cbd644770ae5bc2503fad6c5c52415a` passed all nine required gates; `ARIN-MIG-0020` verified).
- [x] Add backward-compatibility tests for supported versions (`tests/test_arin_contract_compatibility.py`; PR #145 exact head `c5114c33076328cc94d0f6aee2c005fae76eafae` passed required gates and merged as signed commit `23a57fbe7fd2c1b3e1d5c7c40284b53e796a7aac`; `ARIN-MIG-0021` verified).

### Task 5: zknowbase integration — `canonical bounded integration`

- [x] Contract foundation and fake/local boundary tests established (PR #115).
- [x] Read-only search/query transport uses scoped credentials and bounded timeouts (PR #122).
- [x] Provenance/citation mapping into ARIN evidence (PR #123).
- [x] Write/ingest authorization gate requires explicit scope/policy/approval; mutation transport remains absent (PR #124).
- [x] Required knowledge fails closed while optional knowledge degrades only for normalized transport unavailability; malformed/cross-tenant/provenance failures remain hard failures (PR #125).
- [x] Accept API/service integration ADR (PR #165 exact head `2ef5d9072d5c9eb2b4fd0b84a1fe1340c41cb384`; signed merge `6762e442df18709772d10b792e39c9286a31ec02`).
- [x] Inventory actual ARIN knowledge consumers/direct zknowbase call sites (PR #168; no separate production consumer existed at inventory time).
- [x] Verify the bounded server-side runtime consumer in `backend/arin/knowledge_runtime.py` (PR #169 exact head `c6b2761dc9ca14e438ea7fb053ee4f8a70db6444` passed all nine required gates; signed merge `bd939aa95caeaf63783678b10d824410a03bbd5e`). Service credentials remain server-held, tenant mismatch fails before I/O, session/provenance is preserved, required reads fail closed and optional degradation is limited to normalized unavailability.
- [x] Verify additive compatibility/rollback regressions proving the pre-existing read contract remains usable without data/schema/write migration (PR #170 exact head `37fa1d3258ccc0cc462d144d3572fe344f19f1cb` passed all nine required gates; signed merge `38b27696d9d5feaaf6d8a8b85e1540e4f9bb16e8`).
- [x] Merge the explicit prior-path decision: PR #171 exact head `561fdcd7a265396ef812db394cea0cdbcc18b7d1` passed all nine required workflow groups and merged signed as `af0791341e7b214132d34e91a2db9682cc21eecd`. `knowledge_runtime.py` is canonical for new ARIN runtime consumers; direct `KnowledgeClient` reads are rollback-only compatibility with no new feature/authority growth. `ARIN-MIG-0008` is canonical.

### Task 6: Tool/MCP execution boundary — `verified bounded foundation; live endpoint disabled`

- [x] Extract fail-closed ZCoder containment/MCP/network/security requirements (PR #126 / `ARIN-MIG-0009`).
- [x] Define ARIN capability descriptors and risk classes (PR #127 / `ARIN-MIG-0010`).
- [x] Prove server-side policy denial remains authoritative for filesystem/network/subprocess authority (PR #128 / `ARIN-MIG-0011`).
- [x] Accept service-first narrow-adapter ADR and verify transport-neutral request/response contract (PRs #129-#130 / `ARIN-MIG-0012`).
- [x] Verify bounded fake/local transport: capability validation, timeout, cancellation, response identity, result bounds, normalized failures and token non-inheritance (PR #132 / `ARIN-MIG-0013`).
- [ ] Admit any live ZCoder service endpoint only as a separate bounded slice with transport/policy/negative-test/rollback/exact-head evidence. This is not required merely to preserve the verified fake/local foundation.

### Task 7: Voice and perception — `verified bounded foundation`

- [x] Define short-lived consent-bound voice/perception session tickets and retention/deletion rules. PR #173 exact head `a4218750961d440c3518b1bb681ac36cc7f122e7` merged as `f8edbfe2a6c76616703f79d5978c9aec74b4030c`; ticket issuance requires explicit consent, tenant/session binding, TTL <= 300 seconds, opt-in durable retention, and grants no action/actuator authority. ZARVIS remains reference/API-contract input only; no source is copied.
- [x] Implement local-first STT/TTS before optional cloud providers. PR #177 exact head `2cacd152f6061d2612ca04d12a794ef02a59f910` passed all nine required workflow groups and merged as `c091de6ab2521200da4a0354352e858f7a502597`; the ARIN-owned boundary requires an active tenant/session-bound VOICE ticket, fails closed when a local engine is unavailable, has no implicit cloud fallback, and grants no tool/device/actuator authority.
- [x] Add camera/vision evidence contracts with no action/actuator authority. PR #179 exact head `ae19ae4b046e6f5714597290256353a78457df21` passed all nine required workflow groups and merged signed as `f24d133f55882f6045edc5af9c6dcd586f19a1e6`; PR #180 exact head `9064572572fdda16d2ee7260ce961f41a0e9e0d6` passed all nine required workflow groups and merged signed as `fa2ee4d2b66b011aeac408b258708ec25e3027c3`, recording the evidence without changing runtime authority. Camera evidence remains descriptive only and grants no command/tool/device/motion/actuator authority.
- [x] Test interruption, disconnect, deletion, unauthenticated access, cross-session and cross-tenant isolation. PR #174 exact head `7a197738c129bb4fe02688bea58e3cbe39446ce6` merged as `2408d04471b849dd6216cb0201437da8ed8c3002`, verifying fail-closed revocation/disconnect lifecycle and tenant/session isolation. PR #175 exact head `c2cadae14e9638bad4ce32ee8c13981d886fa4bf` passed all nine required workflow groups and merged signed as `2065bf7ea138718bfbd4469b5f659207a51788a5`, verifying authenticated durable-content deletion, cross-tenant/cross-session denial, repeated-deletion denial, timestamp validation and tombstone state without raw perception payload or actuator authority.

### Task 8: Cross-platform desktop and Web/PWA — `incomplete`

- [x] Preserve packaged-runtime validation and writable-state protections. PR #182 exact head `99c4a2aa4a4bd6daa498e8553f825f54f1479a30` passed all nine required workflow groups and merged as `98f4360a1e286b223518b3e55358b354a97e23ae`; packaged DB/artifact overrides must remain absolute and contained beneath Electron `userData`, while existing bundled-runtime validation and source-checkout behavior remain intact.
- [ ] Add ARIN onboarding, providers, voice/vision, knowledge, devices and telemetry surfaces incrementally.
- [x] Ensure Web/PWA never persists provider/service secrets client-side. PR #184 exact head `08cf60ba8d1f3291a89e7a99bff2b952b2ec3b08` passed all nine required workflow groups and merged signed as `a2724f09d0ceaab357b5cd3ad2dbc3409a9ded8a`; the regression allowlists browser persistence to the non-secret theme preference, rejects credential-like local/session storage writes and ungoverned IndexedDB persistence, preserves password-typed credential input, and adds no device/tool/actuator authority.
- [ ] Add responsive/accessibility/E2E tests. Responsive/accessibility regression evidence is verified by PR #186 exact head `9fa07f0e30dc2ccd3e411547070950c2b9788d11`, which passed all nine required workflow groups and merged as `6e774235e890d8cdb07223ccfff84afed4e30c71`; E2E evidence remains incomplete, so this combined checklist item stays open.

### Task 9: Mobile client ADR and implementation — `incomplete`

- [ ] Compare React Native/Expo, Flutter and native Kotlin/Swift against ARIN contracts/offline/audio/camera/background-notification requirements.
- [ ] Choose stack by ADR before scaffolding.
- [ ] Implement short-lived QR/device pairing.
- [ ] Enforce no-secret and no-raw-actuation invariants.
- [ ] Add Android/iOS CI build and smoke tests.

### Task 10: Device and edge fabric — `incomplete`

- [ ] Define device identity/pairing threat model.
- [ ] Add registration/revocation/heartbeat tests first.
- [ ] Implement capability advertisements and authenticated telemetry.
- [ ] Add offline/LAN reconnect and replay/deduplication behavior.

### Task 11: Humanoid simulator reference body — `incomplete`

- [ ] Define schema-validated high-level skills: stand, sit, stop, navigate-to, follow, look-at, execute-approved-skill.
- [ ] Build simulator tests before ROS/vendor integration.
- [ ] Record deterministic telemetry/evidence for every simulated skill.
- [ ] Fail explicitly for unsupported skills.

### Task 12: Deterministic safety supervisor — `incomplete`

- [ ] Specify independent state machine, E-stop, watchdog, dead-man, motion envelopes, velocity/torque/joint limits and recovery semantics.
- [ ] Write exhaustive transition and property/fuzz tests before robot adapters.
- [ ] Require freshness/sequence checks.
- [ ] Reject direct LLM/browser/mobile/tool raw actuator commands by schema and transport boundary.
- [ ] Loss of auth/heartbeat/control-plane connectivity enters documented safe state.

### Task 13: ROS 2 gateway and vendor adapter SDK — `incomplete`

- [ ] Define ROS 2 topic/service/action mapping from simulator contract.
- [ ] Test simulation-only gateway first.
- [ ] Define isolated vendor adapter SDK with declared capabilities/safety constraints.
- [ ] Add physical vendor only after simulator and deterministic safety gates are green; require adapter-specific HIL evidence.

### Task 14: Mission control and diagnostics — `incomplete`

- [ ] Define hierarchy around critical safety state, incidents, device health and active tasks.
- [ ] Reuse zDash patterns only with clean provenance/dependency ownership.
- [ ] Test realtime reconnect, stale state and permissions.
- [ ] Produce redacted diagnostic bundle.

### Task 15: Installer, updater and offline profile — `incomplete`

- [ ] Windows clean install/repair/upgrade/rollback/uninstall first.
- [ ] Linux/macOS packaging after Windows contract stabilizes.
- [ ] Backup-before-upgrade, compatibility preflight, migration and rollback.
- [ ] Air-gapped package/model metadata and no-external-telemetry profile.
- [ ] Clean-host installer matrix.

### Task 16: Gold Master release evidence — `incomplete`

- [ ] Unit/integration/contract/E2E/accessibility/security/load/chaos/backup/restore/upgrade/rollback evidence.
- [ ] SBOM, dependency/source provenance and signed artifacts where supported.
- [ ] Simulator safety evidence and HIL evidence for every supported physical adapter.
- [ ] No untreated Critical/High security or safety blockers.
- [ ] Archive reproducible release evidence before Gold Master declaration.

## Portfolio Boundary

Portfolio cleanup is separate from ARIN. Do not archive, delete, rename or transfer unrelated repositories as an ARIN side effect.
