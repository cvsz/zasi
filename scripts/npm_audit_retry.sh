#!/usr/bin/env bash

# Compatibility entrypoint for the bounded online npm bulk advisory audit.
# The implementation deliberately avoids npm's retired quick-audit fallback.
set -euo pipefail

node scripts/npm_bulk_audit.mjs
