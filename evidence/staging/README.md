# External staging evidence

`evidence/staging/latest.json` is intentionally **not** committed until a real non-production staging deployment has been exercised. Local Docker/CI rehearsals do not satisfy this contract.

A production release tag is allowed only when `scripts/production_go_gate.py` validates all of the following against the exact release commit:

- `main` is protected by GitHub branch/ruleset governance.
- `candidate_commit` is the exact 40-character release commit SHA.
- `candidate_image` and `previous_image` are immutable `ghcr.io/...@sha256:...` references and are different.
- `observed_at` is a real RFC3339 UTC timestamp no more than **6 hours old** at release time. Future timestamps and stale evidence are rejected.
- `staging_url`, readiness, World Room, canary, and rollback endpoints use HTTPS and the same staging origin.
- `/health/ready` reports `release_identity.commit` and `release_identity.image`; staging/production readiness is degraded when those values are missing or malformed.
- `health.observed_commit` and `health.observed_image` are copied verbatim from that live readiness response and must equal the exact `candidate_commit` and `candidate_image`.
- World Room and canary evidence identify the exact `candidate_image` digest.
- controlled canary evidence contains at least 20 requests, error rate <= 1%, and p95 <= 2000 ms.
- rollback redeployed the exact `previous_image` digest in <= 300 seconds on that same staging origin.
- health and World Room checks passed again after rollback.

The deployment must provide `ZASI_RELEASE_COMMIT=<40-hex-sha>` and `ZASI_RELEASE_IMAGE=ghcr.io/...@sha256:<64-hex-digest>` to the candidate process. These are non-secret release identity values. Do not populate the evidence record from intended deployment inputs alone: fetch `/health/ready` from the externally reachable staging origin and record the values actually returned in `release_identity`.

## Required JSON shape

```json
{
  "schema_version": 1,
  "candidate_commit": "<40-hex-sha>",
  "candidate_image": "ghcr.io/cvsz/zasi@sha256:<64-hex-digest>",
  "previous_image": "ghcr.io/cvsz/zasi@sha256:<64-hex-digest>",
  "staging_url": "https://<real-staging-host>",
  "observed_at": "2026-09-13T00:00:00Z",
  "health": {
    "status": "passed",
    "ready_url": "https://<real-staging-host>/health/ready",
    "observed_commit": "<commit returned by /health/ready release_identity.commit>",
    "observed_image": "ghcr.io/cvsz/zasi@sha256:<digest returned by /health/ready release_identity.image>"
  },
  "world_room": {
    "status": "passed",
    "smoke_case": "join room, establish realtime session, exchange audio, receive response",
    "endpoint_url": "https://<real-staging-host>/world-room",
    "image": "ghcr.io/cvsz/zasi@sha256:<candidate-64-hex-digest>"
  },
  "canary": {
    "status": "passed",
    "endpoint_url": "https://<real-staging-host>/health/ready",
    "image": "ghcr.io/cvsz/zasi@sha256:<candidate-64-hex-digest>",
    "request_count": 100,
    "error_rate": 0.0,
    "p95_ms": 250
  },
  "rollback": {
    "status": "passed",
    "endpoint_url": "https://<real-staging-host>/health/ready",
    "image": "ghcr.io/cvsz/zasi@sha256:<previous-64-hex-digest>",
    "health_status": "passed",
    "world_room_status": "passed",
    "duration_seconds": 45
  }
}
```

Do not copy placeholder values into `latest.json`. Evidence must come from an actual deployment/recovery exercise, must match the release candidate being tagged, and must be regenerated when it becomes older than six hours.

## Release behavior

`.github/workflows/release.yml` verifies that the tag commit is contained in `origin/main`, queries live GitHub rulesets, validates `evidence/staging/latest.json`, and uploads the resulting `production-go-decision.json` with the release artifacts. Missing, stale, future-dated, mutable, cross-origin, wrong-identity, failed, or mismatched evidence causes the release to stop with `NO-GO`.
