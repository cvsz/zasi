# External staging evidence

`evidence/staging/latest.json` is intentionally **not** committed until a real non-production staging deployment has been exercised. Local Docker/CI rehearsals do not satisfy this contract.

A production release tag is allowed only when `scripts/production_go_gate.py` validates all of the following against the exact release commit:

- `main` is protected by GitHub branch/ruleset governance.
- `candidate_commit` is the exact 40-character release commit SHA.
- `candidate_image` and `previous_image` are immutable `ghcr.io/...@sha256:...` references and are different.
- `observed_at` is a real RFC3339 UTC timestamp no more than **6 hours old** at release time. Future timestamps and stale evidence are rejected.
- `staging_url`, readiness, World Room, canary, and rollback endpoints use HTTPS and the same staging origin.
- the container artifact contains `/app/.zasi-release-commit`, baked at image build time from the exact Git commit; `/health/ready` reports that value as `release_identity.commit` with `release_identity.source=artifact`.
- the running candidate container digest is verified outside the application through Docker runtime inspection. `scripts/observe_container_image.sh <container> <candidate_image>` must succeed and its JSON becomes the `runtime` evidence object.
- `health.observed_commit` is copied from the live external `/health/ready` response and must equal `candidate_commit`; `health.identity_source` must be `artifact`.
- `runtime.observed_image` must equal the exact immutable `candidate_image` and `runtime.inspector` must be `docker`.
- World Room and canary evidence identify the exact `candidate_image` digest.
- controlled canary evidence contains at least 20 requests, error rate <= 1%, and p95 <= 2000 ms.
- rollback redeployed the exact `previous_image` digest in <= 300 seconds on that same staging origin.
- after rollback, `scripts/observe_container_image.sh <container> <previous_image>` must independently verify the running previous digest; copy its `inspector` and `observed_image` values into the rollback evidence object.
- health and World Room checks passed again after rollback.

Do not inject release identity through `ZASI_RELEASE_COMMIT` or `ZASI_RELEASE_IMAGE`. Those caller-controlled values are not accepted as production evidence. The commit identity must come from the built artifact, while both candidate and rollback image digests must be verified independently by the container runtime.

## Required JSON shape

```json
{
  "schema_version": 1,
  "candidate_commit": "<40-hex-sha>",
  "candidate_image": "ghcr.io/cvsz/zasi@sha256:<64-hex-digest>",
  "previous_image": "ghcr.io/cvsz/zasi@sha256:<64-hex-digest>",
  "staging_url": "https://<real-staging-host>",
  "observed_at": "2026-09-13T00:00:00Z",
  "runtime": {
    "status": "passed",
    "inspector": "docker",
    "observed_image": "ghcr.io/cvsz/zasi@sha256:<candidate-64-hex-digest>"
  },
  "health": {
    "status": "passed",
    "ready_url": "https://<real-staging-host>/health/ready",
    "observed_commit": "<commit returned by /health/ready release_identity.commit>",
    "identity_source": "artifact"
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
    "inspector": "docker",
    "observed_image": "ghcr.io/cvsz/zasi@sha256:<previous-64-hex-digest>",
    "health_status": "passed",
    "world_room_status": "passed",
    "duration_seconds": 45
  }
}
```

Do not copy placeholder values into `latest.json`. Evidence must come from an actual deployment/recovery exercise, must match the release candidate being tagged, and must be regenerated when it becomes older than six hours.

## Release behavior

`.github/workflows/release.yml` verifies that the tag commit is contained in `origin/main`, queries live GitHub rulesets, validates `evidence/staging/latest.json`, and uploads the resulting `production-go-decision.json` with the release artifacts. Missing, stale, future-dated, mutable, cross-origin, wrong-identity, failed, or mismatched evidence causes the release to stop with `NO-GO`.
