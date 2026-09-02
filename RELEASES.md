# Release evidence and known status

## v32.0.0 — governed reference transition

This repository revision transitions the runtime contract from a historical
prototype cockpit to an authenticated, scoped ASGI control plane. It includes:

- one authoritative `backend.app` lifecycle and authenticated v2 API;
- SQLite state, tenant-scoped audit/events, durable outbox, rate limits,
  idempotency, approvals, evidence provenance, device pairing, and sequences;
- a bundled React cockpit with safe rendering and authenticated event replay;
- loopback-supervised Electron startup and non-root, constrained container
  packaging;
- fail-closed sandbox/self-compilation boundaries and brokered egress helpers;
- a tag-release signing gate that requires a protected GPG key/fingerprint and
  publishes verified signatures for artifacts, SBOM, and checksums;
- explicit unavailable/disabled disclosures for hardware, external connectors,
  live telemetry, formal/cryptographic proof, and self-evolution.

## Release decision

The reference profile is `CONDITIONAL READ-ONLY/ASSISTIVE`, not a production
control-plane certification. Local tests and a successful build do not prove
staging deployment, PostgreSQL multi-process operation, managed secrets,
encrypted/restorable backups, external delivery, hardware safety, formal or
cryptographic assurance, or AGI/ASI capability.

The release is `NO-GO` for public production use until the remaining mandatory
H5/H7/H8 evidence is supplied: managed production repository operations and
multi-process migration/crash-recovery evidence, encrypted managed backup/restore,
external egress worker and
dead-letter integration, hosted release provenance, vulnerability/container
scans, staging canary, rollback observation, and independent verification.
Local wheel, sdist, SBOM, checksum, and GPG-signature verification now exists
for the implementation branch, and the hosted workflow now stages the same
verification behind a protected signing environment, but no production tag
has been exercised and this is not a production release certificate.

## Evidence bundle requirement

Each future release must record commit SHA, artifact digests, schema/migration
version, dependency-lock digest, SBOM, signer and signature verification,
test/security results, container user, deployment profile, observed readiness
response, rollback reference, and skipped/unknown gates. “All systems online”
is not a valid substitute for per-capability evidence.
