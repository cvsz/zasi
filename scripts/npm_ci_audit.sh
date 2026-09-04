#!/usr/bin/env bash

# Install from the lockfile and require npm's online audit metadata from the
# same registry operation. This avoids issuing a second audit request after a
# successful install while still failing closed on vulnerabilities, audit
# transport failures, malformed output, or an absent audit report.
set -euo pipefail

audit_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
audit_dir="$(mktemp -d "$audit_root/npm-ci-audit.XXXXXX")"
trap 'rm -rf -- "$audit_dir"' EXIT

json_file="$audit_dir/install.json"
stderr_file="$audit_dir/install.stderr"
set +e
npm ci --ignore-scripts --audit --json >"$json_file" 2>"$stderr_file"
install_status=$?
set -e

cat "$stderr_file" >&2
cat "$json_file"
if (( install_status != 0 )); then
  echo "npm ci failed; refusing to infer an audit result." >&2
  exit "$install_status"
fi

node - "$json_file" <<'NODE'
const fs = require('node:fs');

const file = process.argv[2];
let report;
try {
  report = JSON.parse(fs.readFileSync(file, 'utf8'));
} catch (error) {
  console.error(`npm ci did not emit valid JSON: ${error.message}`);
  process.exit(1);
}

const vulnerabilities = report?.audit?.vulnerabilities;
if (!vulnerabilities || typeof vulnerabilities !== 'object') {
  console.error('npm ci did not emit audit vulnerability metadata; refusing to pass.');
  process.exit(1);
}

const levels = ['info', 'low', 'moderate', 'high', 'critical'];
const counts = Object.fromEntries(levels.map((level) => [level, Number(vulnerabilities[level] ?? 0)]));
if (Object.values(counts).some((count) => !Number.isInteger(count) || count < 0)) {
  console.error('npm ci emitted invalid audit vulnerability counts; refusing to pass.');
  process.exit(1);
}

const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
if (total !== 0) {
  console.error(`npm ci audit found ${total} vulnerability finding(s): ${JSON.stringify(counts)}`);
  process.exit(1);
}

console.error(`npm ci audit verified 0 vulnerabilities across ${report.audited ?? 0} packages.`);
NODE
