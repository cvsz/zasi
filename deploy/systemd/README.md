# Staging systemd deployment

The production-readiness staging path is `zasi-staging-container.service`. The older `zasi-staging.service` runs a source checkout and is retained only for host-level integration work; it cannot satisfy the immutable-image Production GO contract.

## Immutable release selection

Create `/etc/zasi/staging/release.env` as root with mode `0600` and exactly one immutable GHCR digest reference:

```text
ZASI_IMAGE=ghcr.io/cvsz/zasi@sha256:<64 lowercase hex characters>
```

Do not use a mutable tag such as `latest`, `main`, or `v1.2.3`. `scripts/run_staging_container.sh` rejects mutable references before contacting Docker.

The image build requires `ZASI_BUILD_COMMIT=<40-character git SHA>` and stores it as `/app/.zasi-release-commit`. `/health/ready` reads that artifact metadata and reports it as `release_identity.commit` with `release_identity.source=artifact`; caller-provided `ZASI_RELEASE_COMMIT` and `ZASI_RELEASE_IMAGE` values are not trusted.

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

Verify the application commit from the externally reachable readiness endpoint, then verify the running image independently through the Docker runtime:

```bash
curl -fsS https://<staging-host>/health/ready
scripts/observe_container_image.sh zasi-staging "$ZASI_IMAGE"
```

The runtime observer compares the running container image ID with the locally resolved immutable digest and emits the `runtime` JSON object required by `evidence/staging/README.md`. Production GO remains `NO-GO` unless this real staging observation, World Room smoke, canary, rollback evidence, and live GitHub governance all pass.
