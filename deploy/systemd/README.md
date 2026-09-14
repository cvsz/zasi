# Staging systemd deployment

The production-readiness staging path is `zasi-staging-container.service`. The older `zasi-staging.service` runs a source checkout and is retained only for host-level integration work; it cannot satisfy the immutable-image Production GO contract.

## Immutable release selection

Create `/etc/zasi/staging/release.env` as root with mode `0600` and configure both the exact immutable GHCR digest and the externally reachable HTTPS staging origin:

```text
ZASI_IMAGE=ghcr.io/cvsz/zasi@sha256:<64 lowercase hex characters>
ZASI_STAGING_ORIGIN=https://staging.example.com
```

Do not use a mutable image tag such as `latest`, `main`, or `v1.2.3`. `scripts/run_staging_container.sh` rejects mutable references before contacting Docker. `ZASI_STAGING_ORIGIN` must be a bare HTTPS origin and becomes the explicit CORS allowlist for the staging browser surfaces; paths, queries, URL credentials, and fragments are rejected.

The image build requires `ZASI_BUILD_COMMIT=<40-character git SHA>` for published/production-candidate images and stores it as `/app/.zasi-release-commit`. `/health/ready` reads that artifact metadata and reports it as `release_identity.commit` with `release_identity.source=artifact`; caller-provided `ZASI_RELEASE_COMMIT` and `ZASI_RELEASE_IMAGE` values are not trusted.

## Secrets

Provision `/etc/zasi/staging/zasi-secrets.cred` with `systemd-creds` as described in `docs/DEPLOYMENT_GUIDE.md`. The service decrypts that credential into systemd's private credential directory. The launcher copies it with mode `0400` into the unit's `RuntimeDirectory` under `/run` (tmpfs on normal Linux systems) so the Docker daemon can bind-mount it read-only into `/run/credentials/zasi-secrets`. `ExecStopPost` removes the runtime copy. No plaintext secret is written to the repository or persistent release configuration.

## Start and verify

```bash
sudo install -m 0755 scripts/run_staging_container.sh /opt/zasi/scripts/run_staging_container.sh
sudo install -m 0644 deploy/systemd/zasi-staging-container.service /etc/systemd/system/zasi-staging-container.service
sudo systemctl daemon-reload
sudo systemctl enable --now zasi-staging-container.service
sudo systemctl status zasi-staging-container.service
```

Verify the running image first through the Docker runtime, then verify the application commit from the externally reachable readiness endpoint. This order matches the evidence timeline enforced by `scripts/production_go_gate.py`, so the helper-generated `runtime.observed_at` naturally precedes `health.observed_at`.

```bash
bash scripts/observe_container_image.sh zasi-staging "$ZASI_IMAGE"
curl -fsS "$ZASI_STAGING_ORIGIN/health/ready"
```

Record the readiness observation timestamp when the external request succeeds. Continue the same exercise in order with World Room, canary, and rollback observations; do not reorder phase timestamps or refresh only the top-level envelope timestamp.

The runtime observer compares the running container image ID with the locally resolved immutable digest and emits the `runtime` JSON object required by `evidence/staging/README.md`. Production GO remains `NO-GO` unless this real staging observation, World Room smoke, canary, rollback evidence, and live GitHub governance all pass.
