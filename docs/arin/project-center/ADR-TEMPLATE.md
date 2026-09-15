# ARIN Project Center Architecture Decision Record

Use this template for every proposal to add, remove, replace, consolidate, port, or materially change an ARIN repository/service dependency.

## Metadata

- ADR ID: `ADR-ARIN-XXXX`
- Status: `proposed | accepted | rejected | superseded | rolled-back`
- Date:
- Owner:
- Reviewers:
- Related capability:
- Source repository/service:
- Target ARIN component:

## Capability gap

Describe the concrete ARIN requirement that is not satisfied by the current canonical owner. Include user/runtime impact and evidence. A roadmap checkbox or feature name alone is not evidence.

## Decision

State the proposed integration mode and why it is the smallest sufficient change:

- `api-service` — preferred for independently deployable services.
- `package-library` — for stable, versioned libraries with compatible ownership/licensing.
- `selective-port` — only when API/package integration is impractical and provenance is preserved.
- `reference-only` — architecture/pattern evidence; no runtime dependency.
- `reject` — no ARIN integration.

Whole-repository copying into `cvsz/zasi` is not an accepted default.

## Alternatives considered

For each alternative record benefits, costs, operational ownership, and why it was not selected. Always include `build in zasi` and `do nothing/defer` where meaningful.

## Canonical ownership

Identify exactly one canonical owner for the capability. List adapters/references separately. Define API/schema/version boundaries and which repository owns migrations.

## Security, privacy, and safety impact

Document authentication, authorization, tenant/session isolation, secret handling, data retention, network/filesystem access, audit requirements, and failure behavior.

For humanoid/robot capabilities explicitly answer:

- Can this path create physical actuation? If yes, it MUST terminate at the deterministic safety supervisor.
- Can browser/mobile/LLM output reach raw joint, torque, velocity, PWM, or vendor actuator APIs? The required answer is **no**.
- What safe state is entered on stale commands, lost authentication, heartbeat loss, or control-plane loss?
- What simulator and HIL evidence is required before enabling physical actuation?

## License and provenance

Record repository license, dependency licenses, source commit/tag, copied/derived files if any, required notices, and provenance evidence. Unknown or incompatible licensing blocks selective source porting.

## Test and CI evidence

Record exact commit SHA and evidence for applicable unit, integration, contract, E2E, security, packaging, upgrade/rollback, simulator, and HIL checks. Do not infer production readiness from documentation or roadmap state.

## Migration plan

1. Establish contract and compatibility tests.
2. Add integration behind a disabled/default-safe configuration where appropriate.
3. Migrate bounded consumers.
4. Verify telemetry/audit and failure behavior.
5. Promote canonical ownership only after evidence is recorded in the migration ledger.

## Rollback plan

Describe how to disable the integration, restore the previous canonical path/data/schema, and verify recovery. Include compatibility/version constraints and backup requirements.

## Decommission plan

If this replaces an existing ARIN path, define the deprecation window, compatibility aliases, consumer migration evidence, and conditions for removal. Repository archive/delete/rename/transfer is outside this ADR unless separately approved as portfolio cleanup.

## Decision evidence

- Source commit/tag:
- Target commit/PR:
- CI/workflow evidence:
- Security review:
- Migration ledger entry:
- Follow-up issues:
