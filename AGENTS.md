# AGENTS.md — ZASI Repository Agent Instructions

> **Repository:** cvsz/zasi — Zero-Entropy Autonomous Superintelligence Infrastructure
> **URL:** https://github.com/cvsz/zasi
> **Primary Language:** Python (backend), TypeScript/React (frontend)
> **Architecture:** Hybrid module organization — backend/, src/control_plane/, src/legacy/, web/, tests/

---

## 1. Repository Governance — GitHub Settings

### 1.1 Branch Protection — production-main Ruleset

The main branch is protected by the production-main ruleset at .github/rulesets/production-main.json.

**Required status checks** (all must pass before merge):
- Test (Python 3.11), Test (Python 3.12)
- Build Distribution, Docker Build Check
- Dependency Review, Python Syntax & React TypeScript Validation
- Analyze (actions), Analyze (javascript-typescript), Analyze (python)
- Build and Security Scan Docker Image
- Build security evidence
- Clean PostgreSQL backup restore rehearsal
- Local two-replica canary and failure rehearsal
- Base to candidate to immutable rollback
- Validate production GO evidence contract

**Key rules:**
- Branch deletion: blocked
- Non-fast-forward push: blocked
- Required review count: 0 (review thread resolution required)
- Strict required status checks: enforced on create

### 1.2 GitHub Environments

| Environment | Purpose | Secrets |
|---|---|---|
| release | Binary package publishing | PYPI_TOKEN, GITHUB_TOKEN |
| production | Production deployment | DEPLOY_KEY, DATABASE_URL |
| staging | Pre-production | STAGING_DB_URL, STAGING_REDIS_URL |

### 1.3 GitHub Actions Secrets & Variables

**Repository secrets:** ZASI_API_KEY, PYPI_TOKEN, DOCKERHUB_TOKEN, GH_APP_ID, GH_APP_PRIVATE_KEY, WEBHOOK_SECRET
**Repository variables:** PYTHON_VERSION, NODE_VERSION
**Environment secrets:** Per-environment secrets in Settings -> Environments

### 1.4 GitHub Apps
No third-party GitHub Apps currently installed. To add: Settings -> Installations, configure permissions (Contents: read, Metadata: read, Checks: write), subscribe to events (push, pull_request, workflow_run), store as GH_APP_ID and GH_APP_PRIVATE_KEY secrets.

### 1.5 Webhooks
No incoming webhooks configured. To add: Settings -> Webhooks, HTTPS payload URL, application/json, secret stored as WEBHOOK_SECRET, SSL verification enabled.

### 1.6 GitHub Pages
Configured via .github/workflows/pages.yml. Source: gh-pages branch. Built from web/ via Vite static export. Published to https://cvsz.github.io/zasi.

### 1.7 Wiki
URL: https://github.com/cvsz/zasi/wiki — 10 pages, managed via zasi.wiki.git.

### 1.8 Discussions
URL: https://github.com/cvsz/zasi/discussions. Templates: welcome, Q&A, subsystem-proposal.

### 1.9 Social Preview Image
Settings -> General -> Social preview. Minimum 640x320px, recommended 1280x640px. See .github/SOCIAL_PREVIEW.md.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11/3.12, FastAPI, Pydantic v2 |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | SQLite (local), PostgreSQL (production) |
| Cache/Queue | Redis (optional) |
| Agent Platform | Agent runtime, planner, sandbox, approvals |
| Testing | unittest, pytest, 640+ tests |
| CI/CD | GitHub Actions (14 workflows) |
| Container | Docker, docker-compose |

## 3. Project Structure

zasi/ with backend/, src/control_plane/, src/legacy/, web/, tests/, docs/, .github/, .agents/, .claude/, .codex/, evidence/, scripts/, Makefile

## 4. ARIN Governance

ZASI is the curated ARIN Project Center. Migration state machine: candidate -> assessed -> approved -> integrating -> verified -> canonical. All 19 migration records verified.

## 5. Testing

make check | python3 -m pytest tests/ -x -q

## 6. Commit Convention

Conventional Commits: feat(scope): message, docs(scope): message, fix(scope): message

## 7. Security & Quality

- CodeQL enabled, Dependency Review enabled
- All workflows use permissions: contents: read
- Physical actuation disabled until safety gates pass
- All secrets via GitHub Secrets
- All data operations tenant-scoped (ScopeViolation on cross-tenant)

## 8. Key Files Reference

| Purpose | File |
|---|---|
| Main entry | main.py |
| FastAPI app | backend/app.py |
| Legacy server | backend/server.py |
| Storage | src/control_plane/storage/storage.py |
| Contracts | src/control_plane/contracts/contracts.py |
| Agent contracts | src/control_plane/orchestration/agent_contracts.py |
| Agent runtime | src/control_plane/orchestration/agent_runtime.py |
| Policy engine | src/control_plane/governance/policy.py |
| Identity | src/control_plane/identity/identity.py |
| Docker compose | docker-compose.yml |
| Agent prompt | AGENTS.md |
| Codex prompt | .codex/AGENTS.md |

---

> Governed by ZASI: Observe / Assist — simulated and unavailable states are disclosed.

---

# AGENTS.md

Instructions, architecture guide, and operational conventions for AI coding agents operating within the **ZASI** repository.

---

## 1. Project Overview & Governed Safety Architecture

**ZASI** (Zero-Entropy Autonomous Superintelligence Infrastructure) is a local-first, authenticated control-plane reference platform featuring an ASGI Python backend and a React 19 J.A.R.V.I.S. Command Cockpit.

### 1.1 Core Principles & Governed Pipeline
Every operation and action in ZASI enforces an explicit, auditable, and fail-closed path:
```text
authenticated session -> scoped observation -> typed intent -> policy
-> immutable plan -> provenance-backed evidence -> durable event
-> explicit approval -> brokered action
```

- **Fail-Closed by Default**: The API rejects requests without `ZASI_API_KEY`.
- **Bounded Leases & Broker**: Actions are durably queued and dispatched via `ActionWorker` with explicit lease timeouts. Timeouts, cancellations, and indeterminate states transition to `unknown` and require operator reconciliation.
- **Simulated Mutation Boundary**: Agent executions operate in simulated mode by default (`simulated=true`, `external_write=false`). Research execution, direct hardware actuation, and runtime self-modification are disabled in the reference profile.
- **Historical Prototype Catalog**: The repository contains a 176-entry prototype catalog (`docs/SUBSYSTEMS_REFERENCE.md`). A catalog entry is a historical reference snapshot, not an execution grant or proof of external capabilities.

---

## 2. Repository Layout

```text
zasi/
├── backend/                  # Authoritative ASGI application (`backend.app`), API routers, agent platform
├── src/
│   ├── control_plane/        # Governed runtime, safety controls, identity/tenant persistence, broker
│   └── legacy/               # Historical compatibility interfaces
├── web/                      # React 19 cockpit frontend (Vite + TypeScript + React Router)
│   ├── index.html            # Web mount entrypoint
│   └── static/               # Cockpit source (`cockpit.tsx`, `app.tsx`, Three.js canvas)
├── tests/                    # Unit, integration, security, and corpus test suites
│   ├── corpus/               # Reference corpus, evidence contracts, harness compatibility
│   └── test_*.py             # Python unittest test cases
├── .agents/
│   ├── agents/               # Specialized subagent definitions (Markdown frontmatter)
│   └── skills/               # Reusable agent skills with instructions and scripts
├── .codex/                   # Codex CLI configuration and supplemental baseline
├── docs/                     # Architecture specifications, threat models, invariant specifications
├── Makefile                  # Project automation targets
└── package.json              # Frontend dependencies and scripts
```

---

## 3. Harness Compatibility & Required Capabilities

As declared in `tests/corpus/harness/compatibility.json`, all agent harnesses targeting this repository (OpenAI Codex, OpenCode, Zed, dmux, Claude Code, Antigravity, etc.) must satisfy:

| Capability | Requirement |
|---|---|
| `agent` | Autonomous task planning and execution |
| `read-repo` | Comprehensive codebase inspection and semantic search |
| `run-tests` | Execution of unit, integration, and security test suites |
| `respect-repo-instructions` | Adherence to `AGENTS.md`, `Makefile`, and architectural constraints |
| `report-evidence` | Provenance-backed validation and deterministic assertion reporting |

---

## 4. Specialized Subagents & Skills

### 4.1 Subagents (`.agents/agents/`)
Specialized agent configurations with tailored tools and domains:
- **`zasi-core-engineer`**: Core subsystems, 148-stage dialectical pipeline, SMT invariant verification.
- **`zasi-devops-engineer`**: CI/CD workflows, Docker packaging, PyPI releases, multi-version matrices.
- **`zasi-frontend-specialist`**: React 19 cockpit, Three.js 176-node hypergraph visualization, glassmorphism UI.
- **`zasi-quantum-specialist`**: Quantum simulation, topological surface codes, QEC architectures.
- **`zasi-researcher`**: Retrieval of external scientific papers, RFC specifications, and standards.
- **`zasi-rsi-director`**: 320x recursive self-improvement governance, Pareto dominance verification, rollback journals.
- **`zasi-security-auditor`**: CodeQL audits, static analysis, secret redaction, cryptographic enclave validation.

### 4.2 Skills (`.agents/skills/`)
- `zasi`: General development conventions and commit styles.
- `zasi-cockpit-frontend`: React 19 cockpit styling, Three.js canvas, and WebSocket streaming.
- `zasi-formal-smt`: SMT solvers (Z3 / CVC5) and First-Order Logic (FOL) invariants.
- `zasi-mcp-protocols`: Model Context Protocol (MCP) JSON-RPC 2.0 tool/resource dispatch.
- `zasi-quantum-qec`: Simulation and calibration of quantum error correction codes.
- `zasi-real-hardware`: Hardware adapters (PCIe FPGA, QPU cloud endpoints, HSM enclaves).
- `zasi-rsi-optimizer`: Pareto evaluation, safe bytecode patching, rollback mechanics.
- `zasi-security-hardening`: Vulnerability mitigation, secret redaction, zero-trust controls.
- `zasi-subsystem-architect`: Subsystem scaffolding, catalog verification, and invariant enforcement.
- `webfetch`: URL fetching and structured data extraction.

---

## 5. Development & Testing Commands

Agents should rely on standard `Makefile` targets and standard test runners:

### 5.1 Testing
- **Full Python Test Suite**:
  ```bash
  python3 -m unittest discover -s tests -q
  # or
  make test
  ```
- **Agent Platform Tests**:
  ```bash
  python3 -m unittest tests.test_agent_platform
  # or
  make test-agent-platform
  ```
- **Control Plane & Security Gate**:
  ```bash
  python3 -m unittest tests.test_control_plane_core tests.test_control_plane_broker tests.test_control_plane_api tests.test_security_hardening tests.test_egress_security
  # or
  make test-control-plane
  ```
- **Acceptance Gate (Fast Python Gate)**:
  ```bash
  make check
  ```
- **Corpus & Harness Evidence Tests**:
  ```bash
  python3 -m unittest tests.test_reference_corpus tests.test_reference_corpus_evidence
  ```
- **Frontend Type Checking & Tests**:
  ```bash
  npm run typecheck
  npm run build
  node tests/test_components.js
  ```

### 5.2 Running the Application
- **Authoritative Server**:
  ```bash
  ZASI_API_KEY="your-secret-key" python3 -m backend.app
  # or
  make server
  ```
  *(Requires `ZASI_API_KEY` in environment; fails closed if missing).*
- **Cross-Platform Desktop Client**:
  ```bash
  ZASI_API_KEY="your-secret-key" npm run electron
  # or
  make client
  ```
  *(Requires `ZASI_API_KEY` in environment; launches the Electron desktop cockpit against the local backend).*
- **Cross-Platform Packaging**:
  ```bash
  ZASI_ELECTRON_RUNTIME_ROOT="/path/to/runtimes" npm run electron-build
  # or
  ZASI_ELECTRON_RUNTIME_ROOT="/path/to/runtimes" make client-build
  ```
  *(Packages Linux AppImage, macOS dmg, and Windows nsis cross-platform binaries; requires per-platform relocatable Python runtime environments).*

---

## 6. Code Style & Engineering Standards

### 6.1 Python Backend
- Target Python 3.11 / 3.12 (package supports `>=3.9`).
- Use typed Python with `from __future__ import annotations`.
- Naming conventions:
  - Files: `snake_case.py`
  - Classes: `PascalCase`
  - Functions / Methods: `snake_case`
  - Constants: `SCREAMING_SNAKE_CASE`
- Security & Privacy:
  - Always sanitize logs and events to redact secrets, tokens, credentials, and PII.
  - Never bypass the broker or write unapproved external state.
  - Fail-closed error handling: public error responses must not leak internal tracebacks.

### 6.2 Frontend (TypeScript & React)
- React 19 + TypeScript + Vite + React Router.
- Source located in `web/static/`; authoritative entry points are `web/static/app.tsx` and `web/static/cockpit.tsx`.
- Use strict TypeScript; run `npm run typecheck` to verify changes.
- Glassmorphism aesthetic and responsive canvas rendering for 3D visualizations.

### 6.3 Commit Messages
Follow Conventional Commits format:
- `feat(scope): add new feature`
- `fix(scope): resolve bug or security vulnerability`
- `docs: update documentation or specifications`
- `chore: maintenance, config updates, dependencies`
- `build: packaging, containerization, or CI automation`
- Use imperative mood, concise subject line (~50–60 characters).
