#!/usr/bin/env bash
set -euo pipefail

: "${ZASI_IMAGE:?ZASI_IMAGE is required}"
: "${ZASI_STAGING_ORIGIN:?ZASI_STAGING_ORIGIN is required}"
: "${CREDENTIALS_DIRECTORY:?systemd credential directory is required}"
: "${ZASI_RUNTIME_DIRECTORY:=/run/zasi-staging}"

if [[ ! "$ZASI_IMAGE" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]]; then
  echo "ZASI_IMAGE must be an immutable GHCR digest reference" >&2
  exit 65
fi

if [[ ! "$ZASI_STAGING_ORIGIN" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$ ]]; then
  echo "ZASI_STAGING_ORIGIN must be a bare https origin without path, query, credentials, or fragment" >&2
  exit 65
fi

source_credential="${CREDENTIALS_DIRECTORY}/zasi-secrets"
runtime_credential="${ZASI_RUNTIME_DIRECTORY}/zasi-secrets"
if [[ ! -f "$source_credential" ]]; then
  echo "systemd credential zasi-secrets is missing" >&2
  exit 66
fi

command -v docker >/dev/null 2>&1 || {
  echo "docker is required" >&2
  exit 69
}

install -d -m 0700 "$ZASI_RUNTIME_DIRECTORY"
install -m 0400 "$source_credential" "$runtime_credential"

docker pull "$ZASI_IMAGE"
docker rm -f zasi-staging >/dev/null 2>&1 || true

exec docker run --rm \
  --name zasi-staging \
  --network host \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 512m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --mount type=volume,src=zasi-staging-data,dst=/app/data \
  --mount type=bind,src="$runtime_credential",dst=/run/credentials/zasi-secrets,readonly \
  -e CREDENTIALS_DIRECTORY=/run/credentials \
  -e ZASI_PROFILE=staging \
  -e ZASI_SECRET_PROVIDER=systemd-credential \
  -e ZASI_BACKUP_POLICY=managed-encrypted \
  -e ZASI_DATABASE_BACKEND=postgresql \
  -e ZASI_REDIS_KEY_PREFIX=zasi:staging \
  -e ZASI_HOST=127.0.0.1 \
  -e ZASI_PORT=8080 \
  -e ZASI_ALLOW_PUBLIC_BIND=no \
  -e ZASI_CORS_ORIGINS="$ZASI_STAGING_ORIGIN" \
  -e ZASI_ARTIFACT_DIRECTORY=/app/data/artifacts \
  -e ZASI_ENABLE_EXTERNAL_EGRESS=no \
  -e ZASI_ENABLE_RESEARCH_EXECUTION=no \
  -e ZASI_ENABLE_PHYSICAL_ACTUATION=no \
  "$ZASI_IMAGE"
