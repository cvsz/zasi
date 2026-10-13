# ARIN-MIG-0024 — Authenticated read-only provider-status surface evidence

## Scope

This record captures the bounded Task 8 provider-status regression slice merged through PR #194. It verifies the existing ARIN Models/provider-status browser surface boundary; it does not add or expand provider runtime behavior.

## Exact-head evidence

- Integration PR: #194
- Exact integration head: `5339385c6ecb58b3eb485568e236c5ea4f23bc45`
- Merge commit: `2587b80312a98c7758551aac803d9c212d519bcd`
- Required workflow groups at the exact integration head: 9/9 succeeded — ZASI CI/CD Pipeline, Production GO Gate Contract, Security Evidence Pack, Lint & Code Style, Docker Container Image Build & Publish, HA and Canary Rehearsal Evidence, Backup Restore and DR Evidence, Immutable Rollback Evidence, and CodeQL Security Analysis.
- All three inline review threads were resolved before merge. The final regression accepts the existing nullish-coalescing token derivation while requiring the derived authenticated session token to flow into `useModelStatus(...)`, and rejects generic typed mutation calls.

## Verified boundary

- The existing Models/provider-status surface remains bound to the authenticated session token.
- The browser surface remains read-only.
- Provider/service credentials and secrets are not handled or persisted by this surface.
- No persistence authority, live tool authority, device/motion authority, actuator authority, or infrastructure dependency is admitted by this evidence slice.
- Physical actuation remains disabled pending deterministic safety-supervisor and exact supported-adapter hardware-in-the-loop evidence.

## Rollback

This slice is regression/evidence-only. Rollback is removal of the provider-surface regression/evidence changes; no data, schema, provider configuration, credential, or runtime migration is required.

## Remaining Task 8 work

Task 8 remains incomplete. This record verifies only the bounded provider-status sub-surface. Onboarding, voice/vision, additional knowledge/device surfaces, and any remaining composite Task 8 acceptance evidence must be completed independently. Telemetry is separately evidenced by `ARIN-MIG-0023`. No later ARIN task is marked complete by this record.
