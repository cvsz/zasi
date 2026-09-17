# CODEX.md — ZASI Repository for Codex CLI

> **Repository:** cvsz/zasi — Zero-Entropy Autonomous Superintelligence Infrastructure
> **URL:** https://github.com/cvsz/zasi

## MCP Servers
Codex CLI uses MCP servers in .codex/config.toml:
- GitHub (@modelcontextprotocol/server-github)
- Context7 (documentation lookup)
- Exa (web research)
- Memory (persistent context)
- Playwright (browser automation)
- Sequential Thinking (structured reasoning)

## Repository Overview
Python/Vite project with governed control plane. 640+ tests, 14 GitHub Actions workflows, ARIN governance, 176 subsystems.

## GitHub Settings

### Branches & Rulesets
- main protected by production-main ruleset
- 13 required status checks

### Environments
- release: PYPI_TOKEN, GITHUB_TOKEN — binary publishing
- production: DEPLOY_KEY, DATABASE_URL — production gates
- staging: STAGING_DB_URL, STAGING_REDIS_URL — pre-production

### Actions Secrets & Variables
**Repo:** ZASI_API_KEY, PYPI_TOKEN, DOCKERHUB_TOKEN, GH_APP_ID, GH_APP_PRIVATE_KEY, WEBHOOK_SECRET
**Repo vars:** PYTHON_VERSION, NODE_VERSION

### GitHub Apps
Settings -> Installations -> Add: Contents(read), Metadata(read), Checks(write), events: push/PR/workflow_run, secrets: GH_APP_ID, GH_APP_PRIVATE_KEY

### Webhooks
Settings -> Webhooks -> Add: HTTPS URL, application/json, WEBHOOK_SECRET, SSL enabled

### Pages
Workflow: .github/workflows/pages.yml, URL: https://cvsz.github.io/zasi, Source: gh-pages

### Wiki
https://github.com/cvsz/zasi/wiki — 10 pages via zasi.wiki.git

### Discussions
https://github.com/cvsz/zasi/discussions, Templates in .github/DISCUSSION_TEMPLATE/

### Social Preview
Settings -> General -> Social preview, 640x320px minimum, 1280x640px recommended

## Multi-Agent Support
- Explorer: read-only evidence gathering
- Reviewer: correctness, security, regression review
- Docs researcher: API and release-note verification
- DevOps Engineer: GitHub Actions, Docker, PyPI, Pages deployment

## Key Commands
make check | python3 -m pytest tests/ -x -q | python3 -m backend.app | docker-compose up -d

## ARIN Project Center
Migration ledger: docs/arin/project-center/MIGRATION-LEDGER.md
Implementation plan: docs/arin/project-center/IMPLEMENTATION-PLAN.md
All 19 records verified. 640+ tests passing.
