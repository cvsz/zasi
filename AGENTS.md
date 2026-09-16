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
