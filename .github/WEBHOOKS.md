# GitHub Webhooks — ZASI

> Repository: cvsz/zasi
> URL: https://github.com/cvsz/zasi/settings/hooks

## Current State

No incoming webhooks are currently configured for this repository.

## Configuration Guide

### Adding a Webhook

1. Settings -> Webhooks -> Add webhook
2. Configure:
   - Payload URL: HTTPS endpoint (required)
   - Content type: application/json
   - Secret: Store in Actions secrets as WEBHOOK_SECRET
   - SSL verification: Enabled
   - Events: Select specific events or "Send me everything"

### Recommended Events

| Event | Purpose |
|---|---|
| push | Trigger CI/CD on code changes |
| pull_request | Validate PRs before merge |
| workflow_run | React to workflow completion |
| check_run | React to check status changes |
| deployment | Track deployment status |
| release | Track releases |

### Webhook Verification

All webhooks should be verified using HMAC-SHA256:

import hmac, hashlib
def verify_webhook(payload_body, signature_header, secret):
    expected = hmac.new(secret.encode('utf-8'), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)

### Storing Webhook Secret

gh secret set WEBHOOK_SECRET --body "your-webhook-secret"

### Retry Policy

GitHub retries failed webhook deliveries up to 3 times with exponential backoff:
1. Immediate retry
2. ~10 seconds later
3. ~30 seconds later

### Security Considerations

1. Always use HTTPS endpoints
2. Always verify signatures
3. Keep secrets in GitHub Actions secrets
4. Use specific event subscriptions
5. Monitor delivery logs
6. Use IP allowlisting if supported
