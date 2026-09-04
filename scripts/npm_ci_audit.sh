#!/usr/bin/env bash

# Install from the lockfile without npm's retired quick-audit fallback, then
# query the registry's bulk advisory endpoint with bounded retries. The audit
# is not skipped: missing, malformed, or vulnerable results fail closed.
set -euo pipefail

npm ci --ignore-scripts --no-audit
node scripts/npm_bulk_audit.mjs
