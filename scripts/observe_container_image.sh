#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <container-name-or-id> <ghcr.io/...@sha256:digest>" >&2
  exit 64
fi

container="$1"
expected="$2"

if [[ ! "$expected" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]]; then
  echo "expected image must be an immutable GHCR digest reference" >&2
  exit 65
fi

command -v docker >/dev/null 2>&1 || {
  echo "docker is required" >&2
  exit 69
}

expected_id="$(docker image inspect --format '{{.Id}}' "$expected")"
running_id="$(docker inspect --type container --format '{{.Image}}' "$container")"
running_state="$(docker inspect --type container --format '{{.State.Running}}' "$container")"

if [[ "$running_state" != "true" ]]; then
  echo "container is not running" >&2
  exit 70
fi

if [[ "$running_id" != "$expected_id" ]]; then
  echo "running container image ID does not match expected immutable digest" >&2
  exit 71
fi

python3 - "$expected" <<'PY'
from datetime import datetime, timezone
import json
import sys

print(json.dumps({
    "status": "passed",
    "inspector": "docker",
    "observed_image": sys.argv[1],
    "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}, sort_keys=True))
PY
