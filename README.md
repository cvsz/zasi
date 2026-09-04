# ⚡ ZASI: Zero-Entropy Autonomous Superintelligence Infrastructure

[![Version](https://img.shields.io/badge/version-v32.0.0-cyan.svg)](https://github.com/cvsz/zasi/releases)
[![PyPI](https://img.shields.io/pypi/v/zasi.svg?logo=pypi&logoColor=white&color=3775A9)](https://pypi.org/project/zasi/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/zasi.svg?color=blue)](https://pypi.org/project/zasi/)
[![npm](https://img.shields.io/npm/v/zasi-cockpit.svg?logo=npm&logoColor=white&color=CB3837)](https://www.npmjs.com/package/zasi-cockpit)
[![Subsystems](https://img.shields.io/badge/subsystems-historical%20catalog-gray.svg)](docs/SUBSYSTEMS_REFERENCE.md)
[![Tests](https://img.shields.io/badge/tests-CI%20verified-brightgreen.svg)](tests/)
[![Python CI](https://img.shields.io/badge/CI%20Python-3.11%20%7C%203.12-blue.svg)](https://github.com/cvsz/zasi/actions/workflows/ci.yml)
[![React](https://img.shields.io/badge/frontend-React%2019%20%2B%20TypeScript%20%2B%20React%20Router%20v7-61dafb.svg)](web/)
[![Discussions](https://img.shields.io/badge/community-Discussions-orange.svg)](https://github.com/cvsz/zasi/discussions)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

> The identity and release badges above are retained for repository continuity.
> The subsystem badge describes the historical prototype snapshot; the test
> badge reflects the latest full local suite. The governed reference profile
> and current verification evidence are documented below. The Python badge
> reflects the versions exercised by CI; package metadata declares `>=3.9`, but
> versions outside the CI matrix are not release-verified here.

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

The reference control plane also ships the **AI Futures Project Superintelligence**
agent platform. An authenticated operator can define and version an agent, run
a sandbox dry run, submit a supervised execution, observe a tenant-scoped
read-only knowledge result, approve or reject an exact simulated ticket update,
and inspect the complete event, audit, and evidence history. The simulator is
the default model; a loopback-only Ollama adapter is available when explicitly
configured.

Brokered actions are durably queued before dispatch. The reference application
may drain bounded R0/R1 observations through the leased `ActionWorker`; timeout,
lease expiry, cancellation during execution, and uncertain outcomes become
explicit `unknown` states that require authenticated reconciliation. R2-R5
actions remain queued and external writes are disabled in the reference profile.

The agent platform adds bounded agent definitions and versions, deterministic
typed plans, and an approval-gated simulated local write. Every agent mutation
is authenticated, tenant-scoped, bounded, idempotent, auditable, and
fail-closed. `knowledge.search` is read-only and tenant-scoped;
`ticket.update` is a deterministic local simulator whose result explicitly
states `simulated=true` and `external_write=false`.

The repository also contains a historical 176-entry prototype catalog. A
catalog entry is not an execution grant, and the catalog is not evidence that
those systems, hardware interfaces, formal proofs, external connectors, or
superintelligence capabilities exist. The reference profile keeps external
writes, research execution, runtime self-modification, and physical actuation
disabled.

Optional local speech adapters are available as an explicit, source-backed
path: `WhisperCppSTTAdapter` runs a pinned local Whisper model and
`FliteTTSAdapter` produces bounded WAV output. They are not enabled by the
reference API by default, do not authenticate speakers, and cannot authorize
actions. Their local evidence procedure and limitations are recorded in the
[implementation specification](docs/ZASI_IMPLEMENTATION_SPECIFICATION.md).

## Run the authoritative application

The bundled cockpit requires Node.js `>=22.12.0` (the Electron dependency
engine requirement). Use the checked-in lockfile and the fail-closed online
bulk-advisory install/audit wrapper when validating a fresh install:

```bash
set -a
. .env
set +a
scripts/npm_ci_audit.sh
npm run typecheck
npm run build
python3 -m backend.app
```

Open `http://127.0.0.1:8080/`. The API fails closed when `ZASI_API_KEY` is
missing. Use `make server` or the `zasi` console script as equivalent launch
commands. `backend.server` and `zasi-legacy` are compatibility/research paths,
not production owners. The `zasi-demo` entrypoint is retained for source
continuity but exits with an explicit simulation-only/disabled disclosure; it
does not run the historical capability-shaped demo.

## AI Futures quickstart

Set `ZASI_API_KEY` and start the control plane:

```bash
python3 -m backend.app
```

Create a session and create an agent:

```bash
TOKEN=$(python3 -c 'import json, os; print(json.dumps({"api_key": os.environ["ZASI_API_KEY"]}))' |
  curl -sS http://127.0.0.1:8080/api/v2/sessions \
    -H 'Content-Type: application/json' \
    --data-binary @- | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -sS http://127.0.0.1:8080/api/v2/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"demo"}'
```

Start a supervised execution, approve the simulated write, and inspect the
audit stream. Run the Python-only acceptance gate:

```bash
make check
```

`make check` runs `tests.test_agent_platform` and the control-plane core
tests without invoking npm, Docker, network access, or a live service port.

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
| `/api/v2/artifacts` + `/api/v2/cad/*` + `/api/v2/vision/*` | Quarantined source-artifact analysis with digest-bound geometry/image evidence |
| `web/dist` | Vite-built cockpit bundle; no production CDN runtime |
| `electron/main.js` | Supervised loopback shell with readiness polling |

Legacy side-effect routes such as `/api/tick`, `/api/mutate`, and
`/api/rsi/upgrade` return a typed retirement response. `/api/status` and
`/api/telemetry` are compatibility disclosures, not live subsystem claims.

## Electron packaging contract

`npm run electron` is the source-checkout shell and uses the configured local
Python interpreter. Packaged Electron builds require a real, dependency-complete
Python virtual environment for every target platform; `electron-builder` fails
closed when the runtime root is absent or incomplete. Set
`ZASI_ELECTRON_RUNTIME_ROOT` to a directory with this layout before building:

```text
<runtime-root>/linux/bin/python3         + pyvenv.cfg
<runtime-root>/darwin/bin/python3       + pyvenv.cfg
<runtime-root>/win32/Scripts/python.exe  + pyvenv.cfg
```

The build copies those runtimes and the backend/frontend resources outside the
Electron `asar` archive. A generated desktop artifact is not considered usable
without a successful packaged-runtime build and launch check.

Packaged startup stores SQLite state and quarantined artifacts under Electron's
writable `app.getPath('userData')` directory when those paths are not supplied.
Any explicit packaged `ZASI_DATABASE_PATH` or `ZASI_ARTIFACT_DIRECTORY` must be
absolute; relative paths are rejected so installed resources cannot become the
state directory. Each runtime's `pyvenv.cfg` must use a relative `home` inside
the bundled platform root, and interpreter/configuration/home symlinks that
resolve outside that root are rejected. Windows-style relative home separators
are normalized during cross-platform packaging validation.

## Verification

```bash
python3 -m unittest discover -s tests -q
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -q
python3 -m unittest tests.test_control_plane_core tests.test_control_plane_broker tests.test_control_plane_api tests.test_security_hardening tests.test_egress_security -q
python3 scripts/run_action_worker.py --once
node tests/test_components.js
npm run typecheck
scripts/npm_ci_audit.sh
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

The staging deployment contract uses `deploy/systemd/zasi-staging.service`.
It requires a systemd encrypted credential named `zasi-secrets`, an external
PostgreSQL database, authenticated Redis, and a managed backup policy. The
service is loopback-bound and keeps external egress, research execution, and
physical actuation disabled.

Tag releases require a protected signing environment; the release workflow
fails closed without the configured GPG private key and fingerprint, and
publishes verified signatures for the package artifacts, SBOM, and checksum
manifest.

The checked-in example contains only a generated loopback-only API credential
and uses SQLite for a portable local baseline; it contains no shared-service
passwords. This checkout's private `.env` is machine-local and uses the
shared authenticated PostgreSQL and Redis services; those credentials are
never committed. Local green tests do not prove staging deployment, managed
operations, external egress, hardware control, formal/cryptographic proof, or
ASI/AGI capability. Those remain explicit release gates.

## Documentation

- [Full architecture](docs/ZASI_FULL_ARCHITECTURE.md)
- [Implementation specification](docs/ZASI_IMPLEMENTATION_SPECIFICATION.md)
- [System architecture and ownership](docs/ARCHITECTURE.md)
- [API reference](docs/API_REFERENCE.md)
- [AI Futures agent platform](docs/AI_FUTURES_AGENT_PLATFORM.md)
- [Deployment and operations](docs/DEPLOYMENT_GUIDE.md)
- [Alignment and safety boundaries](docs/ALIGNMENT_AND_SAFETY.md)
- [Historical catalog with state disclaimers](docs/SUBSYSTEMS_REFERENCE.md)
- [Release evidence policy](RELEASES.md)

MIT License. Copyright © 2026 ZASI Contributors.
