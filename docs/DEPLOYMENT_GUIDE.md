# ZASI deployment and operations

This guide deploys the governed reference profile. A successful local process,
Docker build, or generated UI is not production deployment evidence.

The bundled cockpit requires Node.js `>=22.12.0`. Keep `package-lock.json`
authoritative; `scripts/npm_ci_audit.sh` installs without npm's retired quick
audit fallback, then queries the npm bulk advisory endpoint for production
packages with bounded retries. Missing, malformed, vulnerable, or unavailable
audit results fail closed. The standalone `scripts/npm_audit_retry.sh` remains
available as a compatibility entrypoint for that same explicit online audit.

## Local

```bash
set -a
. .env
set +a
scripts/npm_ci_audit.sh
npm run typecheck
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

## Staging credentials with systemd

The repository supports the `systemd-credential` provider for staging and
production-like services. `systemd-creds` encrypts the credential file with
the host credential key and systemd materializes it into a private
`CREDENTIALS_DIRECTORY` for the service. The application accepts only the
named `ZASI_*` secrets it needs and rejects missing, duplicate, conflicting,
symlinked, or weakly protected credentials. Plaintext values are not stored in
the unit file.

This is a host-local custody mechanism. If `systemd-creds setup` reports that
the host credential key is not on encrypted media, treat that warning as a
staging limitation; it is not equivalent to a managed secret service with
independent key custody, rotation, and recovery controls.

Provision a host-local staging credential from an already authorized secret
source. Do not put these values in the repository or a deployment manifest:

```bash
sudo systemd-creds setup
sudo install -d -o root -g root -m 700 /etc/zasi/staging
printf '%s\n' \
  "ZASI_API_KEY=$ZASI_API_KEY" \
  "ZASI_DATABASE_URL=$ZASI_DATABASE_URL" \
  "ZASI_REDIS_URL=$ZASI_REDIS_URL" \
  "ZASI_BACKUP_KEY_B64=$ZASI_BACKUP_KEY_B64" |
  sudo systemd-creds --with-key=host --name=zasi-secrets encrypt \
    /dev/stdin /etc/zasi/staging/zasi-secrets.cred
sudo chown root:root /etc/zasi/staging/zasi-secrets.cred
sudo chmod 400 /etc/zasi/staging/zasi-secrets.cred
```

Install the application under `/opt/zasi` with a complete virtual environment,
create the dedicated `zasi` service account and `/var/lib/zasi` state path,
then install and start `deploy/systemd/zasi-staging.service`. The checked-in
unit is loopback-only, runs as the non-root `zasi` account, uses strict systemd
filesystem/resource restrictions, and loads the encrypted credential through
`LoadCredentialEncrypted`. A staging service must use an isolated PostgreSQL
database and a Redis key prefix such as `zasi:staging`; it must not reuse
production state for a rehearsal.

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

## Local rollback rehearsal

The `scripts/rollback_drill.py` command performs a bounded local rehearsal of
the restore path. It creates one random database in the
`zasi_rollback_drill_<random>` namespace using an administrator connection,
restores a freshly encrypted PostgreSQL archive into that database, verifies
schema and integrity, observes that the source schema/integrity are unchanged,
and removes the temporary database. The source database is never replaced.
The command requires an explicit `--allow-local-rehearsal` acknowledgement and
rejects `staging` and `production` profiles.

Inject the source URL, a separate administrator URL, and a one-off 32-byte
backup key through the environment; neither URL nor key is printed by the
command. The local-only guard rejects remote database hosts and accepts only
loopback names/addresses or Unix-socket paths:

```bash
set -a
. .env
set +a
export ZASI_ROLLBACK_SOURCE_URL="$ZASI_DATABASE_URL"
export ZASI_ROLLBACK_ADMIN_URL="postgresql:///postgres?host=/var/run/postgresql&port=5433"
export ZASI_BACKUP_KEY_B64="$(python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())')"
python3 scripts/rollback_drill.py \
  --allow-local-rehearsal \
  --expected-schema-version 11
```

For a local peer-authenticated administrator URL, run the command as the
database administrator or provide an equivalent administrator credential. A
passing result is local restore/reversibility evidence only; it does not prove
managed retention, key rotation, staging canary behavior, production traffic
cutover, or rollback observation.

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

## Durable action worker

Action dispatch is a separate durable worker boundary. `ActionBroker.submit`
writes the action payload, idempotency key, timeout, retry policy, and queued
state before a worker can claim it. `zasi-action-worker` claims only code-owned
R0/R1 handlers by default:

```bash
set -a
. .env
set +a
zasi-action-worker --once
```

The reference worker uses a bounded lease and never returns a lease token to
clients. Lease expiry, timeout, cancellation during execution, and uncertain
side effects become `unknown` and require an authenticated
`POST /api/v2/runs/{run_id}/reconcile` decision before retry. R2-R5 actions
remain queued; enabling a higher-risk worker requires an independently governed
worker, sandbox, egress, approval, rollback, and Gate E evidence bundle.
The command is a local/reference smoke surface, not proof of continuously
deployed workers, external side effects, or production safety.

## Electron

```bash
set -a
. .env
set +a
scripts/npm_ci_audit.sh
npm run build
npm run electron
```

Electron starts `backend.app` on loopback, polls authenticated-agnostic HTTP
readiness for process/dependency state, restricts navigation to that origin,
disables Node integration, enables context isolation and sandboxing, and
terminates the child process on exit. The renderer still obtains an API
session; process readiness is not user authorization. This source-checkout
command is not a packaged-runtime proof.

For a packaged desktop build, provide real dependency-complete Python virtual
environments for all declared targets and run `npm run electron-build`:

```text
<runtime-root>/linux/bin/python3         + pyvenv.cfg
<runtime-root>/darwin/bin/python3       + pyvenv.cfg
<runtime-root>/win32/Scripts/python.exe  + pyvenv.cfg
```

Set `ZASI_ELECTRON_RUNTIME_ROOT` to the parent directory. The builder fails
closed without these runtimes and places the backend, source, config, and
frontend resources outside `asar`; no desktop artifact is usable until its
packaged runtime has been launched and readiness-checked.

Packaged startup defaults SQLite state to
`app.getPath('userData')/data/zasi_control_plane.db` and artifact quarantine to
`app.getPath('userData')/artifacts`. Explicit `ZASI_DATABASE_PATH` and
`ZASI_ARTIFACT_DIRECTORY` values must be absolute in packaged mode. The runtime
validator also requires a relative `pyvenv.cfg` `home` that resolves inside the
platform bundle and rejects interpreter/configuration/home symlinks escaping
it. Windows-style relative home separators are normalized while validating
cross-platform runtime inputs.

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
| `ZASI_REDIS_KEY_PREFIX` | `zasi` by default; use a bounded isolated prefix such as `zasi:staging` for staging |
| `ZASI_SECRET_PROVIDER` | `environment` for local only; `systemd-credential` requires a systemd-managed encrypted credential in staging/production |
| `ZASI_SECRET_CREDENTIAL_FILE` | Optional explicit mode-600 credential file for tests; systemd services use `CREDENTIALS_DIRECTORY/zasi-secrets` |
| `ZASI_BACKUP_POLICY` | `local` for local/reference; staging/production require a managed encrypted policy |
| `ZASI_ARTIFACT_DIRECTORY` | Quarantine directory outside `web/dist` |
| `ZASI_MAX_BODY` | Bounded request body, default 1 MiB |
| `ZASI_ENABLE_EXTERNAL_EGRESS` | `no`; enabling requires an allowlist and separate review |
| `ZASI_ENABLE_RESEARCH_EXECUTION` | `no`; enabling requires an explicit sandbox capability |
| `ZASI_ENABLE_PHYSICAL_ACTUATION` | Always rejected by the reference profile |

Staging/production settings additionally require `ZASI_DATABASE_BACKEND=postgresql`,
a PostgreSQL `ZASI_DATABASE_URL`, an authenticated `ZASI_REDIS_URL`, a
supported external `ZASI_SECRET_PROVIDER` such as `systemd-credential`, and a
managed non-local `ZASI_BACKUP_POLICY`.
The application fails readiness closed when either shared dependency is
unavailable.

## Operational gates

Before a release is called production-ready, record commit SHA, artifact
digests, schema version, dependency lock digest, SBOM, signatures, test and
security results, container identity, profile, observed readiness response, and
rollback reference. Unknown or skipped mandatory evidence is `NO-GO` or
`CONDITIONAL`, never `READY`.
