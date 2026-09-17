# GitHub Secrets & Variables — ZASI

> Repository: cvsz/zasi
> URL: https://github.com/cvsz/zasi/settings/secrets

## Repository Actions Secrets

| Secret | Description | Used In |
|---|---|---|
| ZASI_API_KEY | Control plane API key | ci.yml, local dev |
| PYPI_TOKEN | PyPI publishing token | npm-publish.yml, release.yml |
| DOCKERHUB_TOKEN | Docker Hub auth | docker-publish.yml |
| GITHUB_TOKEN | Default GH Actions token | All workflows |
| GH_APP_ID | GitHub App ID | CI/CD (if App auth) |
| GH_APP_PRIVATE_KEY | GitHub App private key | CI/CD (if App auth) |
| WEBHOOK_SECRET | Webhook HMAC signature | Webhook verification |

## Environment Secrets & Variables

### release Environment
**Secrets:**
| Secret | Description |
|---|---|
| PYPI_TOKEN | PyPI publishing token |
| GITHUB_TOKEN | GitHub token for release publishing |

### production Environment
**Secrets:**
| Secret | Description |
|---|---|
| DEPLOY_KEY | SSH key for production deployment |
| DATABASE_URL | Production PostgreSQL connection string |

### staging Environment
**Secrets:**
| Secret | Description |
|---|---|
| STAGING_DB_URL | Staging PostgreSQL connection string |
| STAGING_REDIS_URL | Staging Redis connection string |

## How to Add Secrets

### Repository Level
gh secret set ZASI_API_KEY --body "your-key"
gh secret set PYPI_TOKEN --body "pypi-token"
gh secret set DOCKERHUB_TOKEN --body "docker-token"

### Environment Level
gh api repos/cvsz/zasi/environments/release -f name=release
gh secret set PYPI_TOKEN --env release --body "pypi-token"
gh variable set PYTHON_VERSION --env release --body "3.12"

## OIDC (OpenID Connect)

For cloud provider federation, use OIDC instead of static secrets:
1. Configure OIDC provider in Settings -> Actions -> General
2. Create environment with OIDC conditions
3. Reference in workflow: environment: production
4. Cloud provider assumes GitHub OIDC role automatically

## Security Best Practices

1. Principle of least privilege
2. Environment scoping preferred over repo-level
3. Rotate secrets quarterly minimum
4. Review secret access logs regularly
5. Never commit secrets to repository
6. All workflows use permissions: contents: read
