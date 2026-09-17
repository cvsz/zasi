# Agent System Rules

## Language & Communication Guidelines
- **Primary Response Language:** Always communicate, explain, and write documentation/comments in **Thai** (ภาษาไทย).
- **Code & Configuration:** All source code, terminal commands, configuration files (JSON, YAML, ENV, etc.), variable names, and code syntax MUST remain in **English**.
- **Technical Terms:** Keep standard software architecture and programming jargon in English (e.g., *refactor*, *middleware*, *dependency injection*) to maintain accuracy.

## Response Behavior
1. **Explanations:** Provide all explanations, step-by-step guidance, and trade-off analyses in **Thai**.
2. **Code Blocks:** Write clean, executable code entirely in **English**. Do not translate programming keywords, variables, or API routes into Thai.
3. **Inline Comments:** Write comments within code blocks in **Thai** if they explain logic to the developer, but keep the code itself standard English.

## Repository Operating Rules
- Read this root `AGENTS.md`, `README.md`, contribution guidance, and repository-native configuration before making changes.
- If a nested `AGENTS.md` exists, treat the nearest file as the more specific instruction set for that subtree while preserving these root rules unless explicitly overridden.
- Preserve the existing architecture, public interfaces, naming conventions, formatting, and repository style unless the task explicitly requires a change.
- Prefer the smallest safe diff that fully solves the requested problem. Do not rewrite unrelated code or generated/vendor files.
- Never commit credentials, tokens, private keys, production secrets, personal data, or sensitive runtime output. Use documented secret/env mechanisms instead.
- Do not disable tests, security checks, type checks, lint rules, branch protections, or validation gates merely to make CI pass.
- Use repository-native build, test, lint, type-check, security, migration, and packaging commands whenever available.
- Before claiming a task complete, verify the relevant tests/checks and report what actually passed, what was not run, and any remaining blocker.

## Production Readiness
- Do not claim `production-ready`, `enterprise-ready`, `secure`, or `complete` without concrete evidence from the repository and validation results.
- For production-impacting changes, consider security, backward compatibility, observability, rollback, migrations, backup/restore, failure handling, and operational documentation.
- Treat authentication, authorization, payments, secrets, infrastructure, data migration, destructive operations, and externally visible API contracts as high-risk changes requiring extra validation.

## Git & Change Safety
- Do not force-push, rewrite shared history, delete unrelated branches/tags, or perform destructive Git operations unless the user explicitly authorizes that exact action.
- Keep commits focused and descriptive. Avoid mixing unrelated refactors with functional fixes.
- Do not merge failing changes or bypass required checks. If checks are unavailable, say so rather than assuming success.
- Preserve existing user work and project-specific instructions. When requirements conflict, follow the more specific repository rule or explicit user instruction and document the trade-off.

---

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
