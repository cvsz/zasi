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
- Exact inspected head before this evidence refresh: `e61252930a725efb8e304140c63f67afdbcf7001`
- Exact-head workflow result: 9/9 successful.
- Successful groups: ZASI CI/CD Pipeline, Production GO Gate Contract, Security Evidence Pack, Lint & Code Style, Docker Container Image Build & Publish, CodeQL Security Analysis, HA and Canary Rehearsal Evidence, Backup Restore and DR Evidence, and Immutable Rollback Evidence.
- Runtime hardening now validates the delete identifier against the issued `mem_...` contract before route construction and encodes the validated identifier with `encodeURIComponent()` before inserting it into the governed `/api/v2/memory/<id>` route.
- The fail-closed regression also rejects JavaScript character escapes and unprovable mutation authorization expressions rather than weakening the governed memory boundary.
- This evidence refresh changes the PR head, so the refreshed head must independently pass all required exact-head CI/review gates before ARIN-MIG-0025 can advance to `verified`.
- Canonical identifier contract: backend memory creation uses `issue_id("mem")`; `issue_id` returns `${prefix}_${secrets.token_urlsafe(16)}`.
- Do not mark this migration verified until the refreshed evidence head and its review state are green.

## Verified boundary

The existing MemoryPage browser surface derives its authority from the authenticated session token and is bounded to governed `/api/v2/memory` routes. The regression requires authenticated authority for memory create/delete mutations, audits `api.*` and `useApi` call paths fail-closed, rejects unprovable or escaping API paths, and rejects browser-side service/provider credential handling.

This slice adds no provider/service secret persistence, infrastructure dependency, live tool authority, device/motion/ROS authority, or actuator authority. It does not redefine the canonical zknowbase runtime and copies no source from another repository.

## Safety / rollback

Physical actuation remains disabled. Browser/mobile/LLM/tool paths remain unable to directly control raw actuators. Deterministic safety-supervisor and exact supported-adapter hardware-in-the-loop release evidence are still required before any physical actuation can be admitted.

Rollback is removal/reversion of the regression/evidence slice; no data/schema migration or external service migration is required.

## Ledger reconciliation

The implementation evidence record remains `integrating`. Do not advance the authoritative migration ledger to `verified` while any refreshed exact-head required gate or required review is red. After the refreshed evidence head passes the repository's required exact-head CI/review gates, reconcile `ARIN-MIG-0025` into `docs/arin/project-center/MIGRATION-LEDGER.md` as `verified`, recording the final evidence PR exact head and merge SHA.
