# ZASI deployment and operations

This guide deploys the governed reference profile. A successful local process,
Docker build, or generated UI is not production deployment evidence.

## Local

```bash
set -a
. .env
set +a
npm ci --ignore-scripts
npm run build
python3 -m backend.app
```

Verify both process and dependency state:

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
```

The API key is required at startup. The tracked example contains only a
loopback-only generated example credential; shared service credentials are
never committed. The private local configuration may point the direct process at the authenticated shared
PostgreSQL and Redis services; the checked-in example remains portable SQLite.
Quarantined artifact files live outside the web bundle. PostgreSQL profiles use
`PostgresControlPlaneStore.backup_to()` for a custom-format dump; SQLite uses
`ControlPlaneStore.backup_to()`. Restore into a clean validation environment
before calling a backup usable.

## Encrypted backup and restore gate

The repository includes `scripts/backup_control_plane.py` and the installed
`zasi-backup` console command, which wrap a SQLite database or PostgreSQL
custom-format dump in an AES-256-GCM envelope.
The package requires a cryptography release at or above `46.0.7` because older
releases are not an acceptable production baseline.
The key is supplied only through `ZASI_BACKUP_KEY_B64`; a staging or production
secret provider must inject that variable at process start. The key is not
stored in the archive, command output, repository, or deployment manifest.

Generate a one-off local validation key and exercise the shared PostgreSQL
backup path as follows:

```bash
export ZASI_BACKUP_KEY_B64="$(python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())')"
backup_path="./data/backup/control-plane-$(date -u +%Y%m%dT%H%M%SZ).zasi"
mkdir -p "$(dirname "$backup_path")"
python3 scripts/backup_control_plane.py create \
  --backend postgresql \
  --database-url "$ZASI_DATABASE_URL" \
  --destination "$backup_path"
python3 scripts/backup_control_plane.py validate \
  --backend postgresql \
  --backup "$backup_path"
```

The timestamp is generated at runtime and stored in `backup_path`; there is no
filename default. For SQLite, replace the backend and
database URL with `--source ./data/zasi_control_plane.db`. A restore must name
an explicit target; SQLite replacement requires `--replace`, and PostgreSQL
replacement adds `--clean --if-exists`. Validate an archive before any restore.
The local encrypted archive validation is evidence for cryptographic envelope,
integrity, and restore mechanics only; it is not managed object storage,
retention, key rotation, staging restore, or rollback evidence.

## Signed release artifacts

The tag-triggered release workflow fails closed unless a protected GitHub
`release` environment supplies `ZASI_RELEASE_GPG_PRIVATE_KEY` and the exact
public-key fingerprint in `ZASI_RELEASE_GPG_FINGERPRINT`. An optional
`ZASI_RELEASE_GPG_PASSPHRASE` is read only by the signing process. The private
key is imported from the secret at job start and is never committed, printed,
or included in the release. `scripts/sign_release_artifacts.py` creates and
verifies detached ASCII-armored signatures for every wheel, sdist, the
CycloneDX SBOM, and `SHA256SUMS`, then publishes the public key and signatures
with the release assets. Configure the protected environment and key rotation
process before creating a production tag; a local GPG signature is not hosted
release provenance.

## Container reference profile

```bash
set -a
. .env
set +a
docker compose up -d --build
docker compose ps
```

The image builds the Vite cockpit in a separate Node stage, runs the Python
service as UID 10001, drops Linux capabilities, uses a read-only root
filesystem with the named `zasi-control-plane-data` volume, and checks
`/health/ready`. The named volume preserves ownership compatibility with the
non-root service; inspect it with `docker volume inspect
zasi-control-plane-data`. The compose default is the local/reference profile.
Do not expose it publicly without an independently reviewed ingress, secret,
backup, database, and release evidence bundle.

## Durable outbox worker

The outbox worker is a separate supervised process. It does not execute task
instructions or grant external side effects:

```bash
set -a
. .env
set +a
zasi-outbox-worker --once
```

For a deployed process, run `zasi-outbox-worker` under a supervisor with an
explicit stop/restart policy and a configured destination handler. The
reference profile can acknowledge its durable `event_stream` rows; unknown
external destinations retry and eventually dead-letter when no handler is
configured. A worker command returning successfully is not evidence of
production deployment, external delivery, or multi-process correctness.

## Electron

```bash
set -a
. .env
set +a
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
| `ZASI_DATABASE_BACKEND` | `sqlite` for the portable default or `postgresql` for the shared multi-process repository |
| `ZASI_DATABASE_URL` | Authenticated PostgreSQL URL when `ZASI_DATABASE_BACKEND=postgresql` |
| `ZASI_REDIS_URL` | Authenticated Redis URL for shared rate limits and readiness |
| `ZASI_ARTIFACT_DIRECTORY` | Quarantine directory outside `web/dist` |
| `ZASI_MAX_BODY` | Bounded request body, default 1 MiB |
| `ZASI_ENABLE_EXTERNAL_EGRESS` | `no`; enabling requires an allowlist and separate review |
| `ZASI_ENABLE_RESEARCH_EXECUTION` | `no`; enabling requires an explicit sandbox capability |
| `ZASI_ENABLE_PHYSICAL_ACTUATION` | Always rejected by the reference profile |

Staging/production settings additionally require `ZASI_DATABASE_BACKEND=postgresql`,
a PostgreSQL `ZASI_DATABASE_URL`, an authenticated `ZASI_REDIS_URL`, an
external `ZASI_SECRET_PROVIDER`, and a managed non-local `ZASI_BACKUP_POLICY`.
The application fails readiness closed when either shared dependency is
unavailable.

## Operational gates

Before a release is called production-ready, record commit SHA, artifact
digests, schema version, dependency lock digest, SBOM, signatures, test and
security results, container identity, profile, observed readiness response, and
rollback reference. Unknown or skipped mandatory evidence is `NO-GO` or
`CONDITIONAL`, never `READY`.
