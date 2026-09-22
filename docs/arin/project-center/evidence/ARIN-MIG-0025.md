# ARIN-MIG-0025 — Authenticated Memory Surface Authority Evidence

State: `integrating`

## Scope

Record the exact-head evidence for the bounded ARIN Task 8 MemoryPage authority regression merged by PR #197. This record does not expand runtime authority and must not be treated as a claim that Task 8 or ARIN is complete until reconciled into the authoritative migration ledger after this evidence change itself passes required gates.

## Exact integration evidence

- Integration PR: #197 (`test(arin): bound Task 8 memory surface authority`)
- Exact integration head: `f46f20aa300df83cff51c2cf5ca7565e1a0930d7`
- Signed merge commit on `main`: `8e51e574f85fc67d3de248c1bb35c028849d59a0`
- Exact-head required workflow groups: 9/9 successful
  - ZASI CI/CD Pipeline
  - Production GO Gate Contract
  - Security Evidence Pack
  - Lint & Code Style
  - Docker Container Image Build & Publish
  - CodeQL Security Analysis
  - HA and Canary Rehearsal Evidence
  - Backup Restore and DR Evidence
  - Immutable Rollback Evidence

## Current evidence-PR gate

- Evidence PR: #198 (`docs(arin): record Task 8 memory surface evidence`)
- Last inspected pre-hardening head: `3e5f03171dddcd891cbfd55e00165038851c7e29`
- Pre-hardening workflow result: 8/9 successful; `ZASI CI/CD Pipeline` failed in unit tests because the fail-closed route regression correctly rejects the current raw dynamic delete segment.
- Current hardening head includes `e548e7f127cac5508f5ce5d7ee78c6a13aed66a0`, which closes two additional proof gaps without weakening assertions: JavaScript `\\x`/`\\u`/octal route escapes are rejected before URL containment checks, and positional mutation authorization now validates the complete second-argument expression rather than its first whitespace-delimited token.
- Runtime blocker: `MemoryPage` still constructs the DELETE route as `/api/v2/memory/${memoryId}`.
- Canonical identifier contract: backend memory creation uses `issue_id("mem")`; `issue_id` returns `${prefix}_${secrets.token_urlsafe(16)}`.
- Required GREEN fix: validate the browser-side delete identifier against the issued `mem_...` contract before route construction, reject any non-conforming identifier fail-closed, and only then encode the validated segment for the governed `/api/v2/memory/<id>` route. `encodeURIComponent()` alone is not accepted as the proof because dot-only input is not encoded by it.
- Do not resolve the associated review/security gate or mark this migration verified until the runtime fix and its exact-head CI/review evidence are green.

## Verified boundary

The existing MemoryPage browser surface derives its authority from the authenticated session token and is bounded to governed `/api/v2/memory` routes. The regression requires authenticated authority for memory create/delete mutations, audits `api.*` and `useApi` call paths fail-closed, rejects unprovable or escaping API paths, and rejects browser-side service/provider credential handling.

This slice adds no provider/service secret persistence, infrastructure dependency, live tool authority, device/motion/ROS authority, or actuator authority. It does not redefine the canonical zknowbase runtime and copies no source from another repository.

## Safety / rollback

Physical actuation remains disabled. Browser/mobile/LLM/tool paths remain unable to directly control raw actuators. Deterministic safety-supervisor and exact supported-adapter hardware-in-the-loop release evidence are still required before any physical actuation can be admitted.

Rollback is removal/reversion of the regression/evidence slice; no data/schema migration or external service migration is required.

## Ledger reconciliation

After this evidence record passes the repository's required exact-head CI/review gates, reconcile `ARIN-MIG-0025` into `docs/arin/project-center/MIGRATION-LEDGER.md` as `verified`, recording this evidence PR's exact head/merge SHA. Until then the authoritative ledger remains unchanged.