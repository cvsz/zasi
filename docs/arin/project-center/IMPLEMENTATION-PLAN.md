# ARIN Project Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish `cvsz/zasi` as the curated ARIN Project Center, integrate only the repositories ARIN truly needs, and deliver ARIN incrementally without collapsing the full `cvsz` portfolio into one monolith.

**Architecture:** ZASI remains the canonical governed control plane. External capabilities are integrated by API or narrow adapters where possible; selective code ports require provenance and ownership review. Physical humanoid actuation remains behind a deterministic fail-closed safety boundary.

**Tech Stack:** Python/FastAPI, React/TypeScript/Electron, PostgreSQL/SQLite, Redis where justified, Ollama/LM Studio/local providers, zknowbase/Qdrant, WebSocket/SSE, ROS 2, mobile client stack to be selected by ADR, GitHub Actions.

**Spec:** `docs/arin/ARIN_MASTER_ARCHITECTURE_SPECIFICATION.md`

## Global Constraints

- Do not merge or copy all `cvsz` repositories into ZASI.
- Curated initial set: `zasi`, `zknowbase`, `zworkforce/packages/zarvis`, `zcoder`, `zdash`, `zanything`, with `z-platform` and `zeaz-platform` only for explicit infrastructure needs.
- Preserve repository history and ownership; consolidation requires ADR + migration + rollback evidence.
- Prefer API/service contracts over source copying.
- ARIN must remain cross-platform and local-first/offline-capable.
- Browser/mobile clients never receive provider secrets or unrestricted service credentials.
- LLM/mobile/web output never directly controls raw actuators.
- Physical actuation stays disabled until deterministic safety and HIL release gates pass.

---

### Task 1: Establish Project Center governance

**Files:**
- Existing: `docs/arin/ARIN_MASTER_ARCHITECTURE_SPECIFICATION.md`
- Existing: `docs/arin/project-center/REPOSITORY-MAP.md`
- Create later during execution: `docs/arin/project-center/ADR-TEMPLATE.md`
- Create later during execution: `docs/arin/project-center/MIGRATION-LEDGER.md`

**Produces:** repository admission/removal rules, ADR template, migration ledger format.

- [ ] Add an ADR template requiring capability gap, alternatives, owner, integration mode, security/privacy/safety impact, license/provenance, test evidence, migration, rollback and decommission plan.
- [ ] Add migration ledger states: `candidate -> assessed -> approved -> integrating -> verified -> canonical`, plus `rejected` and `rolled-back`.
- [ ] Add tests/lint or docs validation if the repository already provides documentation validation hooks.
- [ ] Commit as a standalone governance change.

### Task 2: Build exact repository capability matrix

**Files:**
- Create later: `docs/arin/project-center/CAPABILITY-MATRIX.md`
- Create later: `docs/arin/project-center/EVIDENCE-MATRIX.md`

**Consumes:** repository map.
**Produces:** evidence-backed build/reuse/integrate decisions.

- [ ] Inspect the current heads, licenses, CI state, public contracts and release evidence for each curated repository.
- [ ] For every ARIN capability, record exactly one canonical owner and zero or more adapters/references.
- [ ] Mark every claimed reusable capability as `verified`, `partial`, `reference-only`, or `missing`.
- [ ] Record version/commit references so later implementation is reproducible.
- [ ] Do not infer production readiness from roadmap checkboxes alone.

### Task 3: ARIN compatibility and identity migration

**Files:**
- Create later: `docs/arin/ARIN_IDENTITY_AND_COMPATIBILITY.md`
- Modify later: relevant ZASI docs/UI strings after compatibility review.

**Produces:** J.A.R.V.I.S./ZARVIS-to-ARIN naming and API compatibility policy.

- [ ] Inventory user-visible and API-stable JARVIS/ZARVIS names in ZASI and the selected ZARVIS package.
- [ ] Define which stable IDs remain unchanged and which display/product names become ARIN.
- [ ] Define deprecation aliases and migration windows before changing public contracts.
- [ ] Add regression tests before renaming executable/API identifiers.

### Task 4: Canonical ARIN contracts

**Files:**
- Create/modify later under the existing ZASI API/domain contract locations.
- Create later: `docs/arin/CONTRACTS.md`.

**Produces:** versioned schemas for sessions, intents, plans, approvals, events, skills, devices, perception, knowledge, telemetry, robot capabilities and high-level motion skills.

- [ ] Write schema tests first for tenant/session isolation and incompatible payload rejection.
- [ ] Define stable versioned contracts independent of UI and vendor SDKs.
- [ ] Generate OpenAPI/client artifacts using repository conventions.
- [ ] Add backward-compatibility tests for supported contract versions.

### Task 5: zknowbase integration

**Files:**
- Create later: ZASI knowledge adapter module and tests in existing adapter locations.
- Create later: `docs/arin/integrations/ZKNOWBASE.md`.

**Consumes:** zknowbase scoped API key model and search/query/ingest contracts.
**Produces:** ARIN long-term knowledge interface.

- [ ] Write failing contract tests against a fake/local zknowbase endpoint.
- [ ] Implement read-only search/query first with scoped credentials and bounded timeouts.
- [ ] Add provenance/citation mapping into ZASI evidence.
- [ ] Add write/ingest only behind explicit scopes and policy.
- [ ] Test unavailable/degraded zknowbase behavior fail-closed where knowledge is required and degrade safely where it is optional.

### Task 6: Tool/MCP execution boundary

**Files:**
- Create later: bounded ARIN tool adapter interfaces/tests.
- Create later: `docs/arin/integrations/ZCODER.md`.

**Produces:** allowlisted, approval-aware ARIN tools without unrestricted shell/file/network inheritance.

- [ ] Extract verified security requirements from ZCoder containment, MCP and network boundaries.
- [ ] Define ARIN tool capability descriptors and per-tool risk classes.
- [ ] Add policy tests proving denied filesystem/network/tool operations stay denied.
- [ ] Integrate via service/adapter first; only port a library after ADR approval.

### Task 7: Voice and perception

**Files:**
- Create later: `docs/arin/VOICE_AND_PERCEPTION.md` and bounded runtime modules/tests.

**Consumes:** verified ZARVIS voice/perception patterns; existing ZASI local speech adapters.
**Produces:** consent-bound audio/vision sessions and realtime events.

- [ ] Define short-lived voice/perception session tickets and retention rules.
- [ ] Implement local-first STT/TTS path before optional cloud providers.
- [ ] Add camera/vision evidence contracts without granting action authority to perception output.
- [ ] Test interruption, disconnect, retention deletion, unauthenticated access and cross-session leakage.

### Task 8: Cross-platform desktop and Web/PWA

**Files:**
- Modify later: existing ZASI Electron/web surfaces following current patterns.
- Create later: `docs/arin/CLIENTS.md`.

**Produces:** ARIN desktop shell for Windows/Linux/macOS and authenticated Web/PWA surface.

- [ ] Preserve packaged-runtime validation and writable-state path protections.
- [ ] Add ARIN onboarding, provider setup, voice/vision, knowledge, devices and telemetry surfaces incrementally.
- [ ] Ensure Web/PWA never persists provider/service secrets client-side.
- [ ] Add responsive/accessibility/E2E tests.

### Task 9: Mobile client ADR and implementation

**Files:**
- Create later: `docs/arin/adrs/ADR-MOBILE-STACK.md`.
- Create later: mobile workspace only after ADR approval.

**Produces:** Android/iOS client for chat, voice, camera, pairing, notifications, telemetry, approved high-level skills and E-stop.

- [ ] Compare React Native/Expo, Flutter and native Kotlin/Swift against existing contracts, offline needs, camera/audio/background notifications and maintenance cost.
- [ ] Choose one stack in ADR before scaffolding.
- [ ] Implement QR/device pairing using short-lived credentials.
- [ ] Add client-side no-secret and no-raw-actuation invariants.
- [ ] Add Android/iOS CI build and smoke tests.

### Task 10: Device and edge fabric

**Produces:** registered devices/edge nodes with capability discovery, heartbeat, revocation and local/LAN operation.

- [ ] Define device identity and pairing threat model.
- [ ] Add registration/revocation/heartbeat tests first.
- [ ] Implement capability advertisements and authenticated telemetry.
- [ ] Add offline/LAN reconnection and replay/deduplication behavior.

### Task 11: Humanoid simulator reference body

**Produces:** vendor-neutral simulator implementing ARIN's robot capability contract.

- [ ] Define high-level skills such as stand, sit, stop, navigate-to, follow, look-at and execute-approved-skill as schema-validated intents.
- [ ] Build simulator tests before ROS/vendor integration.
- [ ] Record deterministic telemetry/evidence for every simulated skill.
- [ ] Ensure unsupported skills fail explicitly rather than falling through.

### Task 12: Deterministic safety supervisor

**Produces:** process/service independent from the cognitive runtime.

- [ ] Specify state machine, E-stop, watchdog, dead-man, allowed motion envelopes, velocity/torque/joint limits and recovery semantics.
- [ ] Write exhaustive state-transition and property/fuzz tests before enabling robot adapters.
- [ ] Require explicit freshness/sequence checks for commands.
- [ ] Reject direct LLM/browser/mobile raw actuator commands by schema and transport boundary.
- [ ] Make loss of auth/heartbeat/control-plane connectivity enter a documented safe state.

### Task 13: ROS 2 gateway and vendor adapter SDK

**Produces:** generic ROS 2 integration plus isolated vendor plugins.

- [ ] Define ROS 2 topic/service/action mapping from the simulator contract.
- [ ] Test gateway with simulation only first.
- [ ] Define vendor adapter SDK with declared capabilities and safety constraints.
- [ ] Add one physical vendor only after simulator and safety gates are green.

### Task 14: Mission control and diagnostics

**Consumes:** zDash patterns.
**Produces:** ARIN fleet/device/provider/queue/incident/audit health center.

- [ ] Define dashboard information hierarchy around critical state, device health, active tasks, safety and incidents.
- [ ] Reuse patterns/components only when licensing/dependency ownership is clean.
- [ ] Add realtime reconnection, stale-state and permission-state tests.
- [ ] Produce a redacted diagnostic bundle.

### Task 15: Installer, updater and offline profile

**Consumes:** existing ZASI packaging contract and verified zanything installer/upgrade patterns.
**Produces:** clean install, repair, upgrade, rollback, uninstall and offline bundle across supported platforms.

- [ ] Windows first: validate prerequisites, bundled runtime, writable paths, local provider options, service startup and uninstall preservation.
- [ ] Add Linux and macOS packaging after Windows contract stabilizes.
- [ ] Add backup-before-upgrade, compatibility preflight, migration and rollback.
- [ ] Add air-gapped packages/models metadata and no-external-telemetry profile.
- [ ] Run clean-host installer matrix in CI or dedicated runners.

### Task 16: Gold Master release evidence

**Produces:** ARIN 1.0 release gate.

- [ ] Require unit/integration/contract/E2E/accessibility/security/load/chaos/backup/restore/upgrade/rollback tests.
- [ ] Require SBOM, dependency/provenance checks and signed release artifacts where supported.
- [ ] Require simulator safety evidence and physical hardware-in-the-loop evidence for each supported robot adapter.
- [ ] Require no untreated Critical/High security or safety blockers.
- [ ] Archive reproducible release evidence before declaring Gold Master.

## Portfolio Cleanup Program — Separate from ARIN implementation

The `cvsz` account may contain roughly 143 repositories, but ARIN does not need them all. After the Project Center capability matrix is complete, create a separate portfolio-cleanup plan that classifies repositories as `active-product`, `shared-platform`, `reference/fork`, `archive-candidate`, or `keep-private`. Do not archive, delete, rename or transfer repositories as a side effect of ARIN work. Portfolio cleanup requires its own approval and rollback-safe batch process.
