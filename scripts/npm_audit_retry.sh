#!/usr/bin/env bash

# Run the online production-dependency audit with bounded, transparent retry.
# A registry outage may be retried; an audit finding or any other failure is
# returned immediately and can never be converted into a passing result.
set -euo pipefail

attempts="${ZASI_NPM_AUDIT_ATTEMPTS:-3}"
retry_delay_seconds="${ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS:-5}"
if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]] || (( attempts > 5 )); then
  echo "ZASI_NPM_AUDIT_ATTEMPTS must be an integer from 1 through 5" >&2
  exit 2
fi
if [[ ! "$retry_delay_seconds" =~ ^[0-9]+$ ]] || (( retry_delay_seconds > 60 )); then
  echo "ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS must be an integer from 0 through 60" >&2
  exit 2
fi

audit_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
audit_dir="$(mktemp -d "$audit_root/npm-audit.XXXXXX")"
trap 'rm -rf -- "$audit_dir"' EXIT

transient_pattern='npm (warn|error).*audit.*(429|5[0-9][0-9])|audit endpoint returned an error|Service Unavailable|Bad Gateway|Gateway Timeout|ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|ENOTFOUND|fetch failed|network timeout'

for ((attempt = 1; attempt <= attempts; attempt += 1)); do
  log_file="$audit_dir/attempt-${attempt}.log"
  if npm audit \
    --omit=dev \
    --audit-level=moderate \
    --fetch-retries=0 \
    --fetch-timeout=30000 \
    --fetch-retry-mintimeout=1000 \
    --fetch-retry-maxtimeout=5000 >"$log_file" 2>&1; then
    cat "$log_file"
    exit 0
  fi

  cat "$log_file" >&2
  if ! grep -Eiq "$transient_pattern" "$log_file"; then
    echo "npm audit returned a vulnerability or non-transient failure; refusing to retry." >&2
    exit 1
  fi
  if (( attempt < attempts )); then
    echo "npm audit service failure (attempt ${attempt}/${attempts}); retrying." >&2
    if (( retry_delay_seconds > 0 )); then
      sleep "$retry_delay_seconds"
    fi
  fi
done

echo "npm audit did not complete after ${attempts} transient-failure attempts." >&2
exit 2
