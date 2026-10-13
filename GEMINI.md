# ZASI — Gemini CLI Session Context

> **Repository:** cvsz/zasi — Zero-Entropy Autonomous Superintelligence Infrastructure
> **URL:** https://github.com/cvsz/zasi

## Quick Start

cd /home/cvsz/zasi && export ZASI_API_KEY="your-api-key" && python3 -m backend.app

## GitHub Settings

### Branches
- main protected by production-main ruleset (13 required status checks)

### Environments
- release: binary publishing (PYPI_TOKEN, GITHUB_TOKEN)
- production: production deployment (DEPLOY_KEY, DATABASE_URL)
- staging: pre-production (STAGING_DB_URL, STAGING_REDIS_URL)

### Actions Secrets & Variables
- Repository: ZASI_API_KEY, PYPI_TOKEN, DOCKERHUB_TOKEN
- Repository variables: PYTHON_VERSION, NODE_VERSION
- Environment: per-environment secrets and variables

### GitHub Apps
None installed. To add: Settings -> Installations, store as GH_APP_ID and GH_APP_PRIVATE_KEY secrets.

### Webhooks
None configured. To add: Settings -> Webhooks, store secret as WEBHOOK_SECRET.

### Pages
Source: gh-pages branch. Built from web/. Published to https://cvsz.github.io/zasi.

### Wiki
URL: https://github.com/cvsz/zasi/wiki — 10 pages via zasi.wiki.git

### Discussions
URL: https://github.com/cvsz/zasi/discussions
Templates: welcome, Q&A, subsystem-proposal

### Social Preview
Settings -> General -> Social preview. Minimum 640x320px, recommended 1280x640px. See .github/SOCIAL_PREVIEW.md.

## Key Commands

make check
python3 -m pytest tests/test_arin_identity_compatibility.py -v
python3 -m pytest tests/test_arin_session_schema.py -v
python3 -m pytest tests/test_arin_versioned_contracts.py -v
python3 -m backend.app
docker-compose up -d

## Architecture

- backend/app.py — FastAPI control plane
- backend/server.py — Legacy HTTP server (JARVIS routes retired)
- src/control_plane/storage/storage.py — SQLite/PostgreSQL persistence
- src/control_plane/contracts/contracts.py — Versioned API contracts v1.0.0
- src/control_plane/orchestration/ — Agent runtime, planner, tools
- src/control_plane/governance/policy.py — Policy engine
- src/control_plane/identity/identity.py — Token/session identity
- web/static/cockpit.tsx — React cockpit UI
- tests/ — 640+ tests

## ARIN Project Center

ZASI is the curated ARIN Project Center. Migration ledger: docs/arin/project-center/MIGRATION-LEDGER.md. All 19 migration records verified.

## Agent Context Files

| File | Purpose |
|---|---|
| AGENTS.md | Master agent prompt |
| .codex/AGENTS.md | Codex CLI baseline |
| .agents/skills/zasi/SKILL.md | Zasi conventions skill |
| .claude/skills/zasi/SKILL.md | Claude skill |
