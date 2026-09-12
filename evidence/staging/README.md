# External staging evidence

`evidence/staging/latest.json` is intentionally **not** committed until a real non-production staging deployment has been exercised. Local Docker/CI rehearsals do not satisfy this contract.

A production release tag is allowed only when `scripts/production_go_gate.py` validates all of the following against the exact release commit:

- `main` is protected by GitHub branch/ruleset governance.
- `candidate_commit` is the exact 40-character release commit SHA.
- `candidate_image` and `previous_image` are immutable `ghcr.io/...@sha256:...` references and are different.
- `staging_url` and `/health/ready` use HTTPS.
- health readiness passed on the candidate.
- World Room smoke/E2E passed on the real staging deployment.
- controlled canary evidence contains at least 20 requests, error rate <= 1%, and p95 <= 2000 ms.
- rollback redeployed the exact `previous_image` digest in <= 300 seconds.
- health and World Room checks passed again after rollback.

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
    "ready_url": "https://<real-staging-host>/health/ready"
  },
  "world_room": {
    "status": "passed",
    "smoke_case": "join room, establish realtime session, exchange audio, receive response"
  },
  "canary": {
    "status": "passed",
    "request_count": 100,
    "error_rate": 0.0,
    "p95_ms": 250
  },
  "rollback": {
    "status": "passed",
    "image": "ghcr.io/cvsz/zasi@sha256:<previous-64-hex-digest>",
    "health_status": "passed",
    "world_room_status": "passed",
    "duration_seconds": 45
  }
}
```

Do not copy placeholder values into `latest.json`. Evidence must come from an actual deployment/recovery exercise and must match the release candidate being tagged.

## Release behavior

`.github/workflows/release.yml` verifies that the tag commit is contained in `origin/main`, queries GitHub for the protection state of `main`, validates `evidence/staging/latest.json`, and uploads the resulting `production-go-decision.json` with the release artifacts. Missing, stale, mutable, failed, or mismatched evidence causes the release to stop with `NO-GO`.
