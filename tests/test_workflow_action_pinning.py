from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^#\s]+)", re.MULTILINE)
IMMUTABLE_REF_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class WorkflowActionPinningTests(unittest.TestCase):
    def test_all_external_actions_are_pinned_to_full_commit_sha(self) -> None:
        workflow_files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
        self.assertTrue(workflow_files, "expected at least one GitHub Actions workflow")

        seen_external: list[tuple[Path, str]] = []
        violations: list[str] = []

        for workflow in workflow_files:
            text = workflow.read_text(encoding="utf-8")
            for match in USES_RE.finditer(text):
                action_ref = match.group(1)
                if action_ref.startswith("./"):
                    continue
                seen_external.append((workflow, action_ref))
                if not IMMUTABLE_REF_RE.fullmatch(action_ref):
                    line = text.count("\n", 0, match.start()) + 1
                    violations.append(f"{workflow}:{line}: mutable action ref {action_ref!r}")

        self.assertTrue(seen_external, "pinning test must inspect at least one external action")
        self.assertFalse(violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
