# ARIN Project Center — Repository Map

This map deliberately includes only repositories required or strongly justified for ARIN. The rest of the `cvsz` portfolio is out of scope unless a later ADR adds it.

## Core

- `cvsz/zasi` — canonical ARIN product, control plane, contracts, desktop packaging, policy/approval/audit, device and humanoid orchestration.

## Required integrations

- `cvsz/zknowbase` — knowledge/RAG service.
- `cvsz/zworkforce` / `packages/zarvis` — voice, perception, proactive-context, action/task gateway and client patterns.
- `cvsz/zcoder` — bounded tools/MCP/workspace and execution-security patterns.

## Required references

- `cvsz/zdash` — mission-control UX, realtime operations, telemetry and incident patterns.
- `cvsz/zanything` — enterprise architecture, IAM/provider/integration/installer/upgrade/Gold Master reference ledger.

## Infrastructure references

- `cvsz/z-platform` — shared development/deployment conventions where compatible.
- `cvsz/zeaz-platform` — production edge/deployment integration only when ARIN has an explicit deployment requirement.

## Deferred candidates — not dependencies

These repositories may contain useful ideas but are not part of the ARIN dependency graph today:

- `cvsz/open-webui`
- `cvsz/adk-python`
- `cvsz/agent-harness-generator`
- `cvsz/zagents-generator`
- `cvsz/opencode`
- `cvsz/ComfyUI`

Adding one requires an ADR with a concrete missing capability, ownership decision, security review and removal/rollback path.

## Consolidation rule

Do not copy repositories into `zasi` merely to make the portfolio appear smaller. The Project Center is the curated control point. Portfolio cleanup (archive/rename/transfer) is a separate migration program and must not be mixed with ARIN feature implementation.
