# ZASI deployment and operations

This guide deploys the governed reference profile. A successful local process,
Docker build, or generated UI is not production deployment evidence.

## Local

```bash
export ZASI_API_KEY='choose-a-local-secret'
npm ci --ignore-scripts
npm run build
python3 -m backend.app
```

Verify both process and dependency state:

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
```

The API key is required at startup and is never committed. The local database
defaults to `data/zasi_control_plane.db`; quarantined artifact files live
outside the web bundle. Use `ControlPlaneStore.backup_to()` for a consistent
SQLite backup and restore it into a clean validation environment before
calling a backup usable.

## Container reference profile

```bash
export ZASI_API_KEY='choose-a-container-secret'
export ZASI_CORS_ORIGINS='http://localhost:8080'
docker compose up -d --build
docker compose ps
```

The image builds the Vite cockpit in a separate Node stage, runs the Python
service as UID 10001, drops Linux capabilities, uses a read-only root
filesystem with an explicit data mount, and checks `/health/ready`. The
compose default is the local/reference profile. Do not expose it publicly
without an independently reviewed ingress, secret, backup, database, and
release evidence bundle.

## Electron

```bash
export ZASI_API_KEY='choose-a-desktop-secret'
npm ci --ignore-scripts
npm run build
npm run electron
```

Electron starts `backend.app` on loopback, polls authenticated-agnostic HTTP
readiness for process/dependency state, restricts navigation to that origin,
disables Node integration, enables context isolation and sandboxing, and
terminates the child process on exit. The renderer still obtains an API
session; process readiness is not user authorization.

## Environment contract

| Variable | Local behavior |
|---|---|
| `ZASI_PROFILE` | `local`; staging/production are rejected by the reference binary without their production backend |
| `ZASI_API_KEY` | Required bootstrap secret; stored only as a digest |
| `ZASI_HOST` / `ZASI_PORT` | Defaults `127.0.0.1` / `8080` |
| `ZASI_CORS_ORIGINS` | Explicit non-wildcard allowlist |
| `ZASI_DATABASE_PATH` | SQLite path; default under `data/` |
| `ZASI_ARTIFACT_DIRECTORY` | Quarantine directory outside `web/dist` |
| `ZASI_MAX_BODY` | Bounded request body, default 1 MiB |
| `ZASI_ENABLE_EXTERNAL_EGRESS` | `no`; enabling requires an allowlist and separate review |
| `ZASI_ENABLE_RESEARCH_EXECUTION` | `no`; enabling requires an explicit sandbox capability |
| `ZASI_ENABLE_PHYSICAL_ACTUATION` | Always rejected by the reference profile |

Staging/production settings additionally require `ZASI_DATABASE_BACKEND=postgresql`,
a PostgreSQL `ZASI_DATABASE_URL`, an external `ZASI_SECRET_PROVIDER`, and a
managed non-local `ZASI_BACKUP_POLICY`. The current app deliberately fails
closed because it does not yet ship the PostgreSQL repository adapter.

## Operational gates

Before a release is called production-ready, record commit SHA, artifact
digests, schema version, dependency lock digest, SBOM, signatures, test and
security results, container identity, profile, observed readiness response, and
rollback reference. Unknown or skipped mandatory evidence is `NO-GO` or
`CONDITIONAL`, never `READY`.
