# ARIN Master Architecture Specification

## Purpose

ARIN is the universal, cross-platform humanoid and embodied-AI product direction built on top of ZASI. ZASI remains the governed control-plane and safety-boundary owner. ARIN adds desktop, web, mobile, multimodal, knowledge, device, simulator, ROS 2, and humanoid capabilities through explicit contracts rather than by merging every related repository into one monolith.

## Product boundary

ARIN must support Windows, Linux, macOS, Web/PWA, Android, and iOS; local-first and offline-capable operation; local AI providers such as Ollama and LM Studio with optional cloud providers; voice, vision, memory, knowledge, skills, tools, device pairing, and telemetry; simulator-first humanoid development; ROS 2 as the generic robotics contract; pluggable physical-humanoid adapters; and a deterministic fail-closed safety supervisor between AI intent and physical actuation.

ARIN must not require Obsidian. Obsidian may be supported as a Markdown knowledge import/export adapter.

## Curated repository set

Only repositories with a clear ARIN ownership or integration role belong in the ARIN Project Center. Repositories outside this set remain untouched unless a later migration record explicitly adds them.

| Repository | Role | Integration mode |
|---|---|---|
| `cvsz/zasi` | Canonical ARIN control plane and product owner | Core |
| `cvsz/zknowbase` | Long-term knowledge/RAG boundary | Service API |
| `cvsz/zworkforce` (`packages/zarvis`) | Voice, perception, action/task-gateway source/reference | Selective port/contracts |
| `cvsz/zcoder` | Bounded tools, MCP, workspace and execution-security source/reference | Adapter/selective port |
| `cvsz/zdash` | Mission-control and realtime operations UX source/reference | UI/ops patterns |
| `cvsz/zanything` | Enterprise platform, installer, governance and Gold Master reference ledger | Architecture/release reference |
| `cvsz/z-platform` | Shared local/platform deployment conventions where compatible | Infrastructure reference |
| `cvsz/zeaz-platform` | Production edge/deployment ownership where explicitly required | Infrastructure integration |

Candidate repositories such as `open-webui`, `adk-python`, `agent-harness-generator`, `zagents-generator`, `opencode`, or `ComfyUI` are not core dependencies. They may be evaluated later through ADRs. They must not be pulled into ARIN merely because they contain adjacent AI functionality.

## Ownership

### ZASI
Own authenticated sessions, typed intents, immutable plans, policy decisions, approvals, brokered actions, audit/events, ARIN orchestration, provider-neutral cognitive contracts, device registry, humanoid skill-intent contracts, simulator/robot-gateway contracts, desktop packaging, safety integration, and release evidence.

Physical actuation remains disabled until dedicated hardware safety gates pass.

### zknowbase
Use by authenticated service API. Do not copy the service into ZASI. It owns secure ingestion, semantic/vector knowledge, grounded RAG, Qdrant access, Ollama-backed local embeddings/generation, document provenance, scoped service keys, and knowledge audit.

### zworkforce/packages/zarvis
Selectively reuse browser/Windows/voice assistant patterns, command validation, tool allowlisting, approval-scoped action gateways, memory/perception/proactive boundaries, consent/retention controls, voice-ticket pipelines, and shared event/API schemas.

### zcoder
Selectively reuse bounded agent execution, filesystem/workspace containment, MCP trust policy, network/WebFetch security, subagent/session/skill lifecycle patterns, secret isolation, and approval boundaries. ARIN must not inherit unrestricted shell, file, or network capabilities.

### zdash
Reuse mission-control information architecture, realtime health and telemetry patterns, incident UX, fleet/device views, queue/worker/provider health, audit timelines, RBAC-aware operations, and dry-run/approval-gated controls. zDash remains a separate product; it is not the ARIN backend owner.

### zanything
Use as the enterprise implementation and release reference for IAM, durable data, workers/queues, provider routing, integrations, secret management, confirmation/policy engines, observability, SLO/DR, plugin SDK, installers, offline profiles, upgrade/rollback, and Gold Master evidence. Roadmap checkboxes are not accepted as implementation evidence without repository verification.

## Logical architecture

```text
Desktop / Web / Mobile
        |
        v
ARIN API + Realtime Event Gateway
        |
        v
ZASI Control Plane
  |- Identity / Sessions
  |- Intent / Planner
  |- Policy / Approval
  |- Audit / Events
  |- Provider Router
  |- Skill Registry
  |- Device Registry
  |- Artifact / Evidence Model
  |
  +--> Knowledge Adapter ----> zknowbase / Qdrant / Ollama
  +--> Tool Adapters --------> ZCoder / MCP / bounded integrations
  +--> Perception -----------> Voice / Vision / Sensor sessions
  +--> Humanoid Orchestrator -> high-level skill intent only
                                  |
                                  v
                         Deterministic Safety Supervisor
                                  |
                    Simulator / ROS 2 / Vendor Adapters
                                  |
                             Physical Humanoid
```

## Safety boundary

ARIN/LLM output may express only high-level, schema-validated intent. Raw torque, PWM, low-level joint commands, and equivalent actuator primitives may not originate from the LLM, mobile client, browser, or generic tool runtime. The safety supervisor owns limits, watchdogs, dead-man behavior, E-stop handling, allowed motion envelopes, state transitions, and fail-safe behavior.

## Cross-platform surfaces

- Desktop: Windows, Linux, macOS. Reuse ZASI's existing Electron/runtime-packaging contract initially.
- Web/PWA: authenticated API and realtime-event client; no provider/service secrets in browser storage.
- Mobile: Android/iOS companion for chat, voice, camera, notifications, device pairing, telemetry, high-level approved skills, and emergency stop. Mobile is never the low-level motor controller.
- Edge: Linux/Jetson-class robot node for ROS 2/vendor integration and local safety runtime.

## Memory model

- Working memory: current interaction/task/sensor context; ZASI-owned and short-lived.
- Episodic memory: consent-bound user/task history with retention and deletion controls.
- Knowledge memory: documents, manuals, repositories, notes, skills and grounded RAG through zknowbase.
- Obsidian: optional Markdown source/sink only.

## Delivery tracks

1. Product identity and JARVIS-to-ARIN compatibility map.
2. Canonical shared API/event contracts.
3. Provider-neutral ARIN brain/runtime.
4. zknowbase knowledge adapter and memory governance.
5. Voice runtime.
6. Vision/perception runtime.
7. Skills, MCP and bounded tools.
8. Cross-platform desktop client.
9. Web/PWA client.
10. Android/iOS mobile client.
11. Device pairing and edge-node fabric.
12. Humanoid simulator reference body.
13. ROS 2 gateway and vendor-adapter SDK.
14. Independent deterministic safety supervisor.
15. Mission control, telemetry, diagnostics and incident operations.
16. Cross-platform installer, updater, repair, rollback, uninstall and offline bundles.
17. Security, supply-chain, DR, HIL, cross-platform installation and Gold Master release evidence.

## Release sequence

ARIN 0.1 identity/contracts; 0.2 brain/provider runtime; 0.3 knowledge/memory; 0.4 voice; 0.5 vision/perception; 0.6 skills/tools; 0.7 web/PWA; 0.8 mobile; 0.9 device/edge; 0.10 simulator; 0.11 ROS 2; 0.12 safety supervisor; 0.13 vendor SDK; 0.14 installer/updater/offline; 0.15 operations/security/DR hardening; 1.0 only after hardware, safety, installer, upgrade/rollback, restore and HIL evidence pass.

## Repository consolidation policy

GitHub repositories are not moved into filesystem folders. `cvsz/zasi` is the ARIN Project Center and records the curated dependency set under `docs/arin/project-center/`. Source repositories retain independent history and ownership. A repository may only be archived, renamed, transferred, vendored, submoduled, or otherwise consolidated after an ADR records ownership, dependency consumers, migration steps, license implications, CI replacement, rollback, and evidence that no active consumer is broken.

The default integration preference is: API/service contract > package/library dependency > generated client/contract > selective port with provenance > submodule. Whole-repository copy is prohibited without an explicit ADR.

## Definition of done

ARIN 1.0 requires a clean user journey from installation through initialization, AI-provider setup, voice/vision, knowledge, device pairing, simulator, robot connection, approved high-level skill execution, deterministic safety enforcement, mission-control observation, E-stop, backup/restore, upgrade/rollback and uninstall. Security, privacy, supply-chain, cross-platform, simulator and physical HIL evidence must be archived. No Critical/High safety or security blocker may remain untreated.
