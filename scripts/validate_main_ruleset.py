#!/usr/bin/env python3
"""Validate the canonical/live production-main ruleset with the Production GO policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from production_go_gate import GateError, validate_governance


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_main_ruleset.py <ruleset.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    try:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(ruleset, dict):
            raise GateError("ruleset must be a JSON object")
        if ruleset.get("name") != "production-main":
            raise GateError("ruleset.name must be 'production-main'")
        result = validate_governance([ruleset])
    except (OSError, json.JSONDecodeError, GateError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
