#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-cvsz/zasi}"
MANIFEST="${2:-.github/rulesets/production-main.json}"
RULESET_NAME="production-main"

command -v gh >/dev/null 2>&1 || { echo "gh CLI is required" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 2; }
[[ -f "$MANIFEST" ]] || { echo "ruleset manifest not found: $MANIFEST" >&2; exit 2; }

gh auth status >/dev/null

existing_id="$(gh api "repos/${REPO}/rulesets" --paginate | jq -r --arg name "$RULESET_NAME" '.[] | select(.name == $name) | .id' | head -n1)"

if [[ -n "$existing_id" ]]; then
  echo "Updating ruleset ${RULESET_NAME} (${existing_id}) on ${REPO}"
  gh api --method PUT "repos/${REPO}/rulesets/${existing_id}" --input "$MANIFEST" >/dev/null
  ruleset_id="$existing_id"
else
  echo "Creating ruleset ${RULESET_NAME} on ${REPO}"
  ruleset_id="$(gh api --method POST "repos/${REPO}/rulesets" --input "$MANIFEST" --jq '.id')"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
gh api "repos/${REPO}/rulesets/${ruleset_id}" > "$tmp"

python scripts/validate_main_ruleset.py "$tmp"
echo "Verified active production-main ruleset ${ruleset_id} on ${REPO}."
