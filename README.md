# ⚡ ZASI: Zero-Entropy Autonomous Superintelligence Infrastructure

[![Version](https://img.shields.io/badge/version-v32.0.0-cyan.svg)](https://github.com/cvsz/zasi/releases)
[![PyPI](https://img.shields.io/pypi/v/zasi.svg?logo=pypi&logoColor=white&color=3775A9)](https://pypi.org/project/zasi/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/zasi.svg?color=blue)](https://pypi.org/project/zasi/)
[![npm](https://img.shields.io/npm/v/zasi-cockpit.svg?logo=npm&logoColor=white&color=CB3837)](https://www.npmjs.com/package/zasi-cockpit)
[![Subsystems](https://img.shields.io/badge/subsystems-historical%20catalog-gray.svg)](docs/SUBSYSTEMS_REFERENCE.md)
[![Tests](https://img.shields.io/badge/tests-299%20passing-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://python.org)
[![React](https://img.shields.io/badge/frontend-React%2019%20%2B%20TypeScript%20%2B%20React%20Router%20v7-61dafb.svg)](web/)
[![Discussions](https://img.shields.io/badge/community-Discussions-orange.svg)](https://github.com/cvsz/zasi/discussions)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

> The identity and release badges above are retained for repository continuity.
> The subsystem badge describes the historical prototype snapshot; the test
> badge reflects the latest full local suite. The governed reference profile
> and current verification evidence are documented below.

# ZASI — governed J.A.R.V.I.S. control-plane reference platform

ZASI is a local-first, authenticated control-plane reference implementation
with a React 19 cockpit. The typed `web/static/app.tsx` entrypoint owns the
runtime mount and `web/static/cockpit.tsx` owns the checked cockpit source;
the historical `app.jsx` path remains only as a compatibility re-export.
Its safe path is:

```text
authenticated session -> scoped observation -> typed intent -> policy
-> immutable plan -> provenance-backed evidence -> durable event
-> explicit approval -> brokered action
```

Brokered actions are durably queued before dispatch. The reference application
may drain bounded R0/R1 observations through the leased `ActionWorker`; timeout,
lease expiry, cancellation during execution, and uncertain outcomes become
explicit `unknown` states that require authenticated reconciliation. R2-R5
actions remain queued and external writes are disabled in the reference profile.

The repository also contains a historical 176-entry prototype catalog. A
catalog entry is not an execution grant, and the catalog is not evidence that
those systems, hardware interfaces, formal proofs, external connectors, or
superintelligence capabilities exist. The reference profile keeps external
writes, research execution, runtime self-modification, and physical actuation
disabled.

## Run the authoritative application

```bash
set -a
. .env
set +a
npm ci --ignore-scripts
npm run build
python3 -m backend.app
```

Open `http://127.0.0.1:8080/`. The API fails closed when `ZASI_API_KEY` is
missing. Use `make server` or the `zasi` console script as equivalent launch
commands. `backend.server` and `zasi-legacy` are compatibility/research paths,
not production owners. The `zasi-demo` entrypoint is retained for source
continuity but exits with an explicit simulation-only/disabled disclosure; it
does not run the historical capability-shaped demo.

Create a session and call the read-only status tool:

```bash
python3 -c 'import json, os; print(json.dumps({"api_key": os.environ["ZASI_API_KEY"]}))' |
curl -sS http://127.0.0.1:8080/api/v2/sessions \
  -H 'Content-Type: application/json' \
  --data-binary @-
```

All authenticated v2 resources require the returned bearer session; the session
bootstrap endpoint is the exception. Mutating or risk-bearing work must use a
typed plan, policy decision, idempotency key, and (where required) an
exact-digest approval.

## Authoritative surfaces

| Surface | Contract |
|---|---|
| `backend.app` | Single ASGI application and lifecycle owner |
| `/health/live` | Process liveness only |
| `/health/ready` | Database/schema/frontend dependency readiness |
| `/api/v2/openapi.json` | Authenticated generated API schema |
| `/api/v2/events` | Authenticated durable SSE replay/resync stream |
| `web/dist` | Vite-built cockpit bundle; no production CDN runtime |
| `electron/main.js` | Supervised loopback shell with readiness polling |

Legacy side-effect routes such as `/api/tick`, `/api/mutate`, and
`/api/rsi/upgrade` return a typed retirement response. `/api/status` and
`/api/telemetry` are compatibility disclosures, not live subsystem claims.

## Verification

```bash
python3 -m unittest discover -s tests -q
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -q
python3 -m unittest tests.test_control_plane_core tests.test_control_plane_broker tests.test_control_plane_api tests.test_security_hardening tests.test_egress_security -q
python3 scripts/run_action_worker.py --once
node tests/test_components.js
npm run typecheck
npm audit --omit=dev
npm run build
python3 -m build
python3 scripts/sign_release_artifacts.py --help
```

Encrypted backup validation is available through
`python3 scripts/backup_control_plane.py` (or the installed `zasi-backup`
console command); it requires a 32-byte `ZASI_BACKUP_KEY_B64` injected at
runtime and never uses a repository default.

`python3 scripts/rollback_drill.py --allow-local-rehearsal` (or the installed
`zasi-rollback-drill` command) can rehearse PostgreSQL restore into a random,
temporary database. It is explicitly local/rehearsal evidence and is not
staging or production rollback approval.

Tag releases require a protected signing environment; the release workflow
fails closed without the configured GPG private key and fingerprint, and
publishes verified signatures for the package artifacts, SBOM, and checksum
manifest.

The checked-in example contains only a generated loopback-only API credential
and uses SQLite for a portable local baseline; it contains no shared-service
passwords. This checkout's private `.env` is machine-generated and uses the
shared authenticated PostgreSQL and Redis services; those credentials are
never committed. Local green tests do not prove staging deployment, managed
operations, external egress, hardware control, formal/cryptographic proof, or
ASI/AGI capability. Those remain explicit release gates.

## Documentation

- [Full architecture](docs/ZASI_FULL_ARCHITECTURE.md)
- [Implementation specification](docs/ZASI_IMPLEMENTATION_SPECIFICATION.md)
- [System architecture and ownership](docs/ARCHITECTURE.md)
- [API reference](docs/API_REFERENCE.md)
- [Deployment and operations](docs/DEPLOYMENT_GUIDE.md)
- [Alignment and safety boundaries](docs/ALIGNMENT_AND_SAFETY.md)
- [Historical catalog with state disclaimers](docs/SUBSYSTEMS_REFERENCE.md)
- [Release evidence policy](RELEASES.md)

MIT License. Copyright © 2026 ZASI Contributors.
