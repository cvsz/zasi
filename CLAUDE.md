# CLAUDE.md — ZASI Repository for Claude Code

> **Repository:** cvsz/zasi — Zero-Entropy Autonomous Superintelligence Infrastructure
> **URL:** https://github.com/cvsz/zasi

## Repository Context

ZASI is a Python/Vite project with a governed control plane for AI agent execution. 640+ tests, 14 GitHub Actions workflows, ARIN governance with 176 subsystems.

## GitHub Configuration

### Branch Protection
- main protected by production-main ruleset
- 13 required status checks (Test Python 3.11/3.12, Build, Docker, Dependency Review, CodeQL, Security Evidence, DR Evidence, HA/Canary, Immutable Rollback, Production GO)

### Secrets & Variables
**Repository:** ZASI_API_KEY, PYPI_TOKEN, DOCKERHUB_TOKEN, GH_APP_ID, GH_APP_PRIVATE_KEY, WEBHOOK_SECRET
**Variables:** PYTHON_VERSION, NODE_VERSION
**Environments:** release, production, staging with per-environment secrets

### GitHub Apps
Settings -> Installations -> Add GitHub App:
1. Permissions: Contents (read), Metadata (read), Checks (write)
2. Events: push, pull_request, workflow_run
3. Store as GH_APP_ID, GH_APP_PRIVATE_KEY secrets

### Webhooks
Settings -> Webhooks -> Add:
1. HTTPS payload URL, Content type: application/json
2. Secret -> WEBHOOK_SECRET, SSL verification enabled

### Pages
Workflow: .github/workflows/pages.yml
Published: https://cvsz.github.io/zasi
Source: gh-pages branch

### Wiki
URL: https://github.com/cvsz/zasi/wiki

### Discussions
URL: https://github.com/cvsz/zasi/discussions
Templates: .github/DISCUSSION_TEMPLATE/

### Social Preview
Settings -> General -> Social preview
Minimum 640x320px, recommended 1280x640px

## Key Directories
- backend/ — FastAPI control plane
- src/control_plane/ — Core: storage, contracts, orchestration, governance
- src/legacy/ — Retired modules
- web/ — React frontend
- tests/ — 640+ tests
- .github/ — GitHub config
- .agents/ — Agent definitions
- .claude/ — Claude-specific config
- .codex/ — Codex CLI config

## Testing
make check
python3 -m pytest tests/ -x -q

## Architecture Key Points
1. Tenant isolation — all data operations tenant-scoped
2. Versioned contracts — StrictModel (extra=forbid) version=1.0.0
3. ARIN governance — migration ledger tracks integrations
4. No raw actuation — physical actuation disabled
5. No secrets in code — GitHub Secrets only

## Commit Convention
Conventional commits: feat(scope): message, docs(scope): message, fix(scope): message
